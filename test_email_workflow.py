"""Gmail compose contract, safety, privacy, and execution regression tests."""

import json
import subprocess
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

import executor
import main
from actions.email import compose_url, draft_email, FIELD_LIMITS
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.brain import AIBrain
from ai.errors import AIPlanningError, TaskExecutionError
from ai.orchestrator import process_natural_language_command
from context import ContextEngine
from memory import MemoryManager, MemoryStore


def action(**changes):
    fields = {"to": "professor@example.com", "subject": "Absence tomorrow", "body": "I'll be absent tomorrow."}
    fields.update(changes)
    return {"action": "draft_email", "target": "gmail", "params": fields}


@pytest.mark.parametrize("recipient", ["", "professor@example.com", "name+tag@example.com"])
@pytest.mark.parametrize("body", ["I'll be absent tomorrow.", "日本語 café\n\nA&B; $5 | `text` #1 + 100%?\r\nEnd."])
def test_valid_fields_round_trip(recipient, body):
    item = action(to=recipient, subject="件名: café & notes?", body=body)
    assert ActionPolicy().validate([item]) == [item]
    parsed = urlsplit(compose_url("gmail", item["params"]))
    assert (parsed.scheme, parsed.netloc, parsed.path, parsed.fragment) == ("https", "mail.google.com", "/mail/", "")
    assert parse_qs(parsed.query, keep_blank_values=True) == {
        "view": ["cm"], "fs": ["1"], "to": [recipient],
        "su": [item["params"]["subject"]], "body": [body],
    }


@pytest.mark.parametrize("field", ["to", "subject", "body"])
@pytest.mark.parametrize("value", [None, 1, [], {}, True])
def test_wrong_types(field, value):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([action(**{field: value})])


@pytest.mark.parametrize("field", ["to", "subject", "body"])
def test_missing_fields(field):
    item = action()
    del item["params"][field]
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([item])


@pytest.mark.parametrize("field", ["send", "instruction", "url", "cc", "bcc", "attachment", "browser", "context"])
def test_extra_fields_rejected(field):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([action(**{field: "anything"})])


@pytest.mark.parametrize("recipient", ["professor", "a@", "@example.com", "a..b@example.com", "a@example.com,b@example.com", "Name <a@example.com>", "a@example.com\r\nBcc: b@example.com", " a@example.com", "a@example.com?bcc=b@example.com"])
def test_recipient_rejection(recipient):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([action(to=recipient)])


@pytest.mark.parametrize("field", ["to", "subject", "body"])
def test_field_length_limits(field):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([action(**{field: "a" * (FIELD_LIMITS[field] + 1)})])


@pytest.mark.parametrize("changes", [{"subject": "hello\r\nBcc: x"}, {"body": "x\x00y"}, {"body": "x\x7fy"}, {"subject": "", "body": ""}, {"body": "界" * 1000}])
def test_controls_empty_content_and_encoded_length(changes):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([action(**changes)])


def test_arbitrary_target_rejected():
    item = action()
    item["target"] = "https://evil.example"
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([item])
    with patch("actions.email.SITES", {"gmail": "https://evil.example"}):
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([action()])


@pytest.fixture
def engine(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.db"))
    manager = MemoryManager(store)
    try:
        yield ContextEngine(manager)
    finally:
        store.close()


def run_plan(items, engine, command, dispatcher=None):
    class Provider:
        def generate_text(self, prompt):
            assert "draft_email" in prompt
            return json.dumps({"actions": items})
    return process_natural_language_command(command, brain=AIBrain(Provider()), context_engine=engine, executor_func=dispatcher)


@pytest.mark.parametrize("system,browser", [("Darwin", "Brave"), ("Darwin", "Safari"), ("Windows", "Brave")])
@pytest.mark.parametrize("recipient", ["", "professor@example.com"])
def test_real_pipeline_launch_and_private_logs(system, browser, recipient, engine, capsys, tmp_path):
    engine.memory_manager.add_memory(f"I prefer {browser}", "user_preference")
    item = action(to=recipient)
    command = f"Draft an email to {recipient} with subject Absence tomorrow and body I'll be absent tomorrow."
    def process(raw):
        return run_plan([item], engine, raw)
    with patch.object(main, "process_natural_language_command", side_effect=process), \
         patch.object(executor, "context_engine", engine), \
         patch("logger.LOG_FOLDER", str(tmp_path)), patch("logger.LOG_FILE", str(tmp_path / "history.log")), \
         patch("actions.browser.platform.system", return_value=system), \
         patch("actions.browser._windows_brave_executable", return_value="mock-brave.exe"), \
         patch("actions.browser.subprocess.run") as run, patch("actions.browser.subprocess.Popen") as popen:
        result = main.handle_command(command)
    assert result[0]["action"] == "draft_email"
    launched = run if system == "Darwin" else popen
    launched.assert_called_once()
    assert parse_qs(urlsplit(launched.call_args.args[0][-1]).query)["body"] == ["I'll be absent tomorrow."]
    if system == "Darwin":
        assert launched.call_args.args[0][2] == ("Safari" if browser == "Safari" else "Brave Browser")
    output = capsys.readouterr().out + (tmp_path / "history.log").read_text()
    assert "compose preparation launch requested" in output
    for secret in ["professor@example.com", "Absence tomorrow", "I'll be absent tomorrow."]:
        assert secret not in output
    for forbidden in ["saved", "sent", "delivered"]:
        assert forbidden not in output.lower()


@pytest.mark.parametrize("send_action", ["send", "send_email"])
def test_send_and_mixed_plans_execute_nothing(send_action, engine):
    for items in [[{"action": send_action, "target": "gmail", "params": {}}], [action(), {"action": send_action, "target": "gmail", "params": {}}]]:
        calls = []
        with pytest.raises(AIPlanningError):
            run_plan(items, engine, "Draft an email", calls.append)
        assert calls == []


@pytest.mark.parametrize("field", ["to", "subject", "body"])
def test_invented_content_rejected(field, engine):
    item = action(**{field: "invented@example.com" if field == "to" else "Invented text"})
    calls = []
    with pytest.raises(ActionPolicyError, match="must come from"):
        run_plan([item], engine, "Draft an email to professor@example.com subject Absence tomorrow body I'll be absent tomorrow.", calls.append)
    assert calls == []


@pytest.mark.parametrize("command_prefix", ["Send an email", "Please send an email", "Can you send an email", "Draft an email and please send it"])
def test_send_instruction_cannot_be_silently_converted_to_draft(engine, command_prefix):
    with pytest.raises(ActionPolicyError):
        run_plan([action()], engine, command_prefix + " to professor@example.com subject Absence tomorrow body I'll be absent tomorrow.", lambda _: pytest.fail("executed"))


def test_recipient_substring_is_not_a_supplied_address(engine):
    with pytest.raises(ActionPolicyError, match="recipient must match"):
        run_plan([action()], engine, "Draft an email to otherprofessor@example.com subject Absence tomorrow body I'll be absent tomorrow.", lambda _: pytest.fail("executed"))


def test_unspecified_subject_and_recipient_can_remain_empty(engine):
    calls = []
    run_plan([action(to="", subject="")], engine, "Draft an email saying I'll be absent tomorrow.", calls.append)
    assert calls[0]["params"]["subject"] == ""
    assert calls[0]["params"]["to"] == ""


def test_launch_failure_becomes_task_failure_without_payload(engine, capsys):
    item = action()
    with patch.object(executor, "context_engine", engine), patch.object(executor, "log_action"), \
         patch("actions.email.open_browser", side_effect=subprocess.CalledProcessError(1, ["private URL"])):
        with pytest.raises(TaskExecutionError) as error:
            run_plan([item], engine, "Draft an email to professor@example.com subject Absence tomorrow body I'll be absent tomorrow.")
    assert str(error.value.__cause__) == "Gmail compose launch failed."
    output = capsys.readouterr().out
    assert "Task succeeded" not in output
    assert "professor@example.com" not in output


def test_top_level_send_flag_rejected(engine):
    item = action()
    item["send"] = True
    with pytest.raises(AIPlanningError):
        run_plan([item], engine, "Draft an email", lambda _: pytest.fail("executed"))
