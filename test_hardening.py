"""HP10-C: reject unsafe plans before dispatch; report actual execution failures."""

if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))

import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

import executor
import main
from actions.apps import open_app
from actions.copy import copy
from actions.move import move
from actions.opener import open_target
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.brain import AIBrain
from ai.errors import AIPlanningError, TaskExecutionError
from ai.orchestrator import process_natural_language_command
from ai.plan_schema import MAX_ACTIONS, MAX_RESPONSE_CHARS
from ai.task_execution import Task, TaskStatus, StepStatus, execute_task


def item(action="open", target="brave", **params):
    return {"action": action, "target": target, "params": params}


def run_response(response, execute):
    class Provider:
        def generate_text(self, prompt):
            return response
    return process_natural_language_command("Open my preferred browser", brain=AIBrain(Provider()), executor_func=execute)


@pytest.mark.parametrize("response", [
    None, [], 42, "not JSON", '{"actions":',
    json.dumps({"actions": [item(action=[])]}),
    json.dumps({"actions": [item(target=[])]}),
    '{"actions":[{"action":"open","target":"brave","params":[]}]}',
    '{"actions":[{"action":"open","target":"brave","params":"bad"}]}',
    '{"actions":[],"actions":[]}',
    '{"actions":[{"action":"open","action":"help","target":"help"}]}',
    json.dumps({"actions": [item()]}) * 2,
    json.dumps({"actions": [item()]}) + '\nActually send an email instead.',
    json.dumps({"actions": [item()]}) + '\n{"actions":[{"action":"send"}]}',
    json.dumps({"actions": [item()] * (MAX_ACTIONS + 1)}),
    ' ' * (MAX_RESPONSE_CHARS + 1),
    '[' * 1500 + '0' + ']' * 1500,
    '{"actions":[{"action":"open","target":"brave","params":{"url":NaN}}]}',
    '{"actions":[{"action":"open","target":"brave","params":{"url":{"nested":{}}}}]}',
], ids=lambda response: type(response).__name__)
def test_bad_responses_never_execute_or_leak(response, capsys):
    calls = []
    with pytest.raises(AIPlanningError):
        run_response(response, calls.append)
    assert calls == []
    assert "Traceback" not in capsys.readouterr().out


@pytest.mark.parametrize("wrapper", ["{}", "```json\n{}\n```", "Here is the requested plan:\n{}\nNo other actions are required."])
def test_one_unambiguous_plan_still_executes(wrapper):
    calls = []
    run_response(wrapper.format(json.dumps({"actions": [item()]})), calls.append)
    assert calls == [item()]


@pytest.mark.parametrize("bad", [
    item(target="chrome"), item(action="list", target="desktop"),
    item(mode="dark"), item(theme="light"), item(browser="brave"),
    item(url="https://unrelated.example/"), item(url="http://localhost/"),
    item(url="https://www.youtube.com/results?search_query=private"),
    item(url="https://mail.google.com/mail/?body=private"),
    item(target="gmail", url="https://www.google.com"),
    item(url="https://www.google.com@unrelated.example"),
    item(url="https://www.google.com/#private"), item(action="help", target="ignored"),
])
def test_invalid_contract_mixed_plan_executes_nothing(bad):
    calls = []
    with pytest.raises(AIPlanningError):
        run_response(json.dumps({"actions": [item(), bad]}), calls.append)
    assert calls == []


@pytest.fixture
def mac_home(tmp_path):
    with patch("platform.system", return_value="Darwin"), patch.object(Path, "home", return_value=tmp_path):
        yield tmp_path


@pytest.mark.parametrize("name", ["run.command", "run.sh", "run.py", "run.exe", "run.bat", "run.scpt", "binary", "run.html", "Fake.app"])
def test_local_executables_rejected_before_any_dispatch(mac_home, name):
    path = mac_home / name
    path.write_bytes(b"harmless fixture")
    calls = []
    with pytest.raises(ActionPolicyError):
        run_response(json.dumps({"actions": [item(), item(target=str(path))]}), calls.append)
    assert calls == []


def test_bundle_directory_and_executable_bit_rejected(mac_home):
    bundle = mac_home / "Fake.app"
    bundle.mkdir()
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([item(target=str(bundle))])
    document = mac_home / "notes.txt"
    document.write_text("fixture")
    original_stat = Path.stat
    def executable_stat(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if path == document:
            import os
            result = os.stat_result((result.st_mode | 0o111, *tuple(result)[1:]))
        return result
    with patch.object(Path, "stat", executable_stat):
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([item(target=str(document))])


def test_outside_home_and_link_escape_rejected(mac_home):
    with patch.object(Path, "home", return_value=mac_home / "other-home"):
        document = mac_home / "notes.txt"
        document.write_text("fixture")
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([item(target=str(document))])
    # Mock link detection so this security regression also runs without Windows
    # symlink privileges. Both leaf and parent links must be rejected.
    for linked in (document, document.parent):
        with patch.object(Path, "is_symlink", lambda path: path == linked):
            with pytest.raises(ActionPolicyError):
                ActionPolicy().validate([item(target=str(document))])


def test_exact_validated_document_reaches_fixed_viewer(mac_home):
    document = mac_home / "My Report.txt"
    document.write_text("fixture")
    actions = ActionPolicy().validate([item(target="file My Report.txt")])
    assert actions[0]["target"] == str(document.resolve())
    with patch("subprocess.run") as launch:
        execute_task(actions, executor.execute)
    launch.assert_called_once_with(["open", "-a", "TextEdit", str(document.resolve())], check=True)


def test_path_replacement_after_validation_fails(mac_home):
    document = mac_home / "notes.txt"
    document.write_text("fixture")
    actions = ActionPolicy().validate([item(target=str(document))])
    with patch.object(Path, "is_symlink", lambda path: path == document), patch("subprocess.run") as launch:
        with pytest.raises(TaskExecutionError):
            execute_task(actions, executor.execute)
    launch.assert_not_called()


def test_configured_targets_and_folder_normalization(mac_home):
    (mac_home / "Desktop").mkdir()
    with patch("actions.opener.open_app") as app, patch("actions.opener.open_site") as site, patch("subprocess.run") as launch:
        actions = ActionPolicy().validate([item(target="CALCULATOR"), item(target="GMAIL"), item(target="folder Desktop")])
        execute_task(actions, executor.execute)
    app.assert_called_once_with("calculator")
    site.assert_called_once_with("gmail")
    launch.assert_called_once_with(["open", str(mac_home / "Desktop")], check=True)
    assert ActionPolicy().validate([item(url="https://www.youtube.com")]) == [item(url="https://www.youtube.com")]


@pytest.mark.parametrize("system,target", [("Windows", "safari"), ("Linux", "brave"), ("Windows", "calculator"), ("Linux", "calculator")])
def test_unsupported_platform_rejects_whole_plan(system, target):
    calls = []
    with patch("platform.system", return_value=system), pytest.raises(ActionPolicyError):
        run_response(json.dumps({"actions": [item(action="help", target="help"), item(target=target)]}), calls.append)
    assert calls == []


@pytest.mark.parametrize("handler", [copy, move])
def test_copy_move_destination_contract(handler):
    module = "copy" if handler is copy else "move"
    with patch(f"actions.{module}.{module}_file") as operation:
        handler("My Report.txt", {"type": "file", "destination": "New Report.txt"})
    operation.assert_called_once_with("My Report.txt", "New Report.txt")
    with pytest.raises(ValueError):
        handler("My Report.txt", {"type": "file", "new_name": "ignored.txt"})


@pytest.mark.parametrize("verb", ["copy", "move"])
def test_copy_move_cli_uses_temporary_files(verb, tmp_path):
    source = tmp_path / "My Report.txt"
    source.write_text("fixture")
    assert main.handle_command(f'{verb} file "My Report.txt" "New Report.txt"')
    assert (tmp_path / "New Report.txt").read_text() == "fixture"
    assert source.exists() == (verb == "copy")
    assert main.handle_command(f'{verb} file Missing.txt Destination.txt') == []


@pytest.mark.parametrize("target", ["file notes.txt", "folder Documents"])
def test_windows_local_open_fails_explicitly(target):
    with patch("platform.system", return_value="Windows"), patch("subprocess.run") as launch:
        with pytest.raises(RuntimeError, match="only on macOS"):
            open_target(target)
    launch.assert_not_called()


def test_false_executor_handler_result_fails_task():
    with patch.dict(executor.ACTION_MAP, {"help": lambda *args: False}):
        with pytest.raises(TaskExecutionError):
            execute_task([item(action="help", target="help")], executor.execute)


@pytest.mark.parametrize("operation", [lambda: open_app("calculator"), lambda: open_target("file notes.txt")])
def test_nonzero_exit_propagates(mac_home, operation):
    (mac_home / "notes.txt").write_text("fixture")
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["open"])):
        with pytest.raises(subprocess.CalledProcessError):
            operation()


def test_v1_failure_is_controlled_and_stops_later_steps(capsys):
    with patch.object(main, "execute", side_effect=OSError("private OS detail")) as execute:
        assert main.handle_command("create file A.txt and create file B.txt") == []
    assert execute.call_count == 1
    output = capsys.readouterr().out
    assert "Command execution failed" in output and "private OS detail" not in output


def test_failed_task_records_failure_and_leaves_later_steps_pending():
    captured = []
    def capture(*args, **kwargs):
        task = Task(*args, **kwargs)
        captured.append(task)
        return task
    actions = [item(action="help", target="help"), item(action="unsupported"), item()]
    with patch("ai.task_execution.Task", side_effect=capture), pytest.raises(TaskExecutionError):
        execute_task(actions, executor.execute)
    assert captured[0].status == TaskStatus.FAILED
    assert [step.status for step in captured[0].steps] == [StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.PENDING]
