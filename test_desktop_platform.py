"""Cross-platform contracts: processes/browser are fakes; files are temporary."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import config
import executor
import main
from actions.apps import open_app
from actions.browser import open_browser, open_site
from actions.local_paths import open_local_target
from actions.platforms import DesktopUnavailable, MacOSAdapter, WindowsAdapter, get_platform
from actions.search import search_google
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.errors import TaskExecutionError
from ai.orchestrator import process_natural_language_command
from ai.task_execution import execute_task


@pytest.fixture(autouse=True)
def desktop_fakes():
    with patch("actions.platforms.subprocess.Popen") as popen, \
         patch("actions.platforms.subprocess.run") as run, \
         patch("actions.platforms.webbrowser.open", return_value=True) as browser:
        yield popen, run, browser


def item(target, action="open", **params):
    return {"action": action, "target": target, "params": params}


@pytest.mark.parametrize("system,adapter", [("Windows", WindowsAdapter), ("Darwin", MacOSAdapter)])
def test_adapter_selection(system, adapter):
    with patch("platform.system", return_value=system):
        assert isinstance(get_platform(), adapter)


@pytest.mark.parametrize("system", ["Linux", "FreeBSD", ""])
@pytest.mark.parametrize("operation", [lambda: open_app("vscode"), lambda: open_browser("brave"),
                                      lambda: open_site("google"), lambda: search_google("python"),
                                      lambda: open_local_target("file notes.txt")])
def test_unknown_os_never_launches(system, operation, desktop_fakes):
    with patch("platform.system", return_value=system), pytest.raises(DesktopUnavailable, match="Supported platforms"):
        operation()
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("name,app", [("calculator", "Calculator"), ("vscode", "Visual Studio Code"),
                                    ("whatsapp", "WhatsApp"), ("telegram", "Telegram")])
def test_macos_app_mapping(name, app, desktop_fakes):
    with patch("platform.system", return_value="Darwin"):
        actions = ActionPolicy().validate([item(name.upper())])
        execute_task(actions, executor.execute)
    desktop_fakes[1].assert_called_once_with(["/usr/bin/open", "-a", app], check=True)
    desktop_fakes[0].assert_not_called()


@pytest.mark.parametrize("name,variable,parts", [
    ("calculator", "SystemRoot", ("System32", "calc.exe")),
    ("vscode", "LOCALAPPDATA", ("Programs", "Microsoft VS Code", "Code.exe")),
    ("vscode", "PROGRAMFILES", ("Microsoft VS Code", "Code.exe")),
    ("vscode", "PROGRAMFILES(X86)", ("Microsoft VS Code", "Code.exe")),
    ("whatsapp", "LOCALAPPDATA", ("WhatsApp", "WhatsApp.exe")),
    ("telegram", "APPDATA", ("Telegram Desktop", "Telegram.exe")),
    ("telegram", "PROGRAMFILES", ("Telegram Desktop", "Telegram.exe")),
])
def test_windows_app_locations(name, variable, parts, tmp_path, desktop_fakes):
    executable = str(tmp_path.joinpath(*parts))
    with patch("platform.system", return_value="Windows"), \
         patch.dict(os.environ, {variable: str(tmp_path)}, clear=True), \
         patch("actions.platforms.os.path.isfile", side_effect=lambda p: p == executable):
        assert main.route_command(f"open {name}")[0] == "v1"
        execute_task(ActionPolicy().validate([item(name.upper())]), executor.execute)
    desktop_fakes[0].assert_called_once_with([executable])
    desktop_fakes[0].return_value.wait.assert_not_called()
    desktop_fakes[1].assert_not_called()


@pytest.mark.parametrize("name", ["calculator", "vscode", "whatsapp", "telegram"])
@pytest.mark.parametrize("root", ["", "relative-install"])
def test_windows_missing_or_relative_install_has_no_fallback(name, root, desktop_fakes):
    with patch("platform.system", return_value="Windows"), \
         patch.dict(os.environ, {key: root for key in ("SystemRoot", "LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")}, clear=True), \
         pytest.raises(DesktopUnavailable, match="not installed"):
        open_app(name)
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
@pytest.mark.parametrize("target", ["powershell", "cmd.exe", "osascript", "/tmp/evil", "vscode --shell", "--args"])
def test_adapter_rejects_commands_and_arbitrary_paths(system, target, desktop_fakes):
    with patch("platform.system", return_value=system), pytest.raises(DesktopUnavailable):
        get_platform().open_app(target)
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_config_values_cannot_supply_executables(system, desktop_fakes):
    with patch.dict(config.APPS, {"injected": "/tmp/evil"}), patch("platform.system", return_value=system):
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([item("injected")])
        with pytest.raises(DesktopUnavailable):
            open_app("injected")
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
@pytest.mark.parametrize("url", ["file:///tmp/run.sh", "javascript:alert(1)", "--args", "https://user:pass@example.com",
                               "https://example.com\n--arg", "https://example.com:bad", ""])
def test_browser_adapter_rejects_non_navigation_arguments(system, url, desktop_fakes):
    with patch("platform.system", return_value=system), pytest.raises(ValueError):
        get_platform().open_browser("brave", url)
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("name,reader", [("notes.txt", "notepad"), ("image.png", "brave"),
                                      ("report.pdf", "brave"), ("folder", "explorer")])
def test_windows_local_fixed_readers(name, reader, tmp_path, desktop_fakes):
    path = tmp_path / name
    path.mkdir() if name == "folder" else path.write_text("fixture")
    with patch("platform.system", return_value="Windows"), patch.object(Path, "home", return_value=tmp_path), \
         patch.dict(os.environ, {"SystemRoot": str(tmp_path), "LOCALAPPDATA": str(tmp_path)}), \
         patch("actions.platforms.os.path.isfile", return_value=True):
        execute_task(ActionPolicy().validate([item(str(path))]), executor.execute)
    executable = {"notepad": tmp_path / "System32" / "notepad.exe", "explorer": tmp_path / "explorer.exe",
                  "brave": tmp_path / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"}[reader]
    desktop_fakes[0].assert_called_once_with([str(executable), path.as_uri() if reader == "brave" else str(path)])


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
@pytest.mark.parametrize("unsafe", ["run.exe", "run.lnk", "run.url", "run.command", "run.scpt", "run.html"])
def test_unsafe_local_types_rejected(system, unsafe, tmp_path, desktop_fakes):
    path = tmp_path / unsafe
    path.write_text("fixture")
    with patch("platform.system", return_value=system), patch.object(Path, "home", return_value=tmp_path):
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([item(str(path))])
        with pytest.raises(ValueError):
            open_local_target(str(path))
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("linked_part", ["leaf", "parent"])
def test_windows_junction_replacement_rechecked(linked_part, tmp_path, desktop_fakes):
    path = tmp_path / "notes.txt"
    path.write_text("fixture")
    with patch("platform.system", return_value="Windows"), patch.object(Path, "home", return_value=tmp_path):
        actions = ActionPolicy().validate([item(str(path))])
        junction = path if linked_part == "leaf" else path.parent
        with patch.object(Path, "is_junction", lambda p: p == junction), pytest.raises(TaskExecutionError):
            execute_task(actions, executor.execute)
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_ai_policy_runs_before_any_adapter(system, desktop_fakes):
    brain = Mock()
    brain.plan.return_value = {"actions": [item("vscode"), item("brave", url="https://unconfigured.example/")]}
    with patch("platform.system", return_value=system), \
         patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy, \
         pytest.raises(ActionPolicyError):
        process_natural_language_command("please open VS Code", brain=brain)
    policy.assert_called_once()
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
@pytest.mark.parametrize("action", ["create", "rename", "copy", "move", "delete", "execute"])
def test_ai_mutations_and_execution_remain_rejected(system, action, desktop_fakes):
    with patch("platform.system", return_value=system), pytest.raises(ActionPolicyError):
        ActionPolicy().validate([item("vscode"), item("notes.txt", action)])
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_ai_app_plan_reaches_adapter_after_policy(system, desktop_fakes):
    brain = Mock()
    brain.plan.return_value = {"actions": [item("vscode")]}
    with patch("platform.system", return_value=system), \
         patch("actions.platforms._installed", return_value="fixed-install.exe"), \
         patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy:
        assert process_natural_language_command("please open VS Code", brain=brain) == [item("vscode")]
    policy.assert_called_once()
    if system == "Windows":
        desktop_fakes[0].assert_called_once_with(["fixed-install.exe"])
    else:
        desktop_fakes[1].assert_called_once_with(["/usr/bin/open", "-a", "Visual Studio Code"], check=True)


def test_windows_alternate_data_stream_rejected(tmp_path, desktop_fakes):
    with patch("platform.system", return_value="Windows"), patch.object(Path, "home", return_value=tmp_path):
        with pytest.raises(ActionPolicyError, match="alternate data streams"):
            ActionPolicy().validate([item(str(tmp_path / "notes.txt:stream.txt"))])
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_local_outside_home_rejected_on_both_platforms(system, tmp_path, desktop_fakes):
    path = tmp_path / "notes.txt"
    path.write_text("fixture")
    with patch("platform.system", return_value=system), patch.object(Path, "home", return_value=tmp_path / "home"):
        with pytest.raises(ActionPolicyError, match="outside the allowed path"):
            ActionPolicy().validate([item(str(path))])
    for launch in desktop_fakes:
        launch.assert_not_called()


def test_missing_windows_install_is_useful_cli_result(capsys, desktop_fakes):
    with patch("platform.system", return_value="Windows"), patch("actions.platforms.os.path.isfile", return_value=False):
        assert main.handle_command("open vscode") == []
    assert "not installed in a supported Windows location" in capsys.readouterr().out


def test_shared_file_lifecycle_uses_only_temporary_files(tmp_path, desktop_fakes):
    for command in ('create file "a.txt"', 'rename file "a.txt" "b.txt"',
                    'copy file "b.txt" "c.txt"', 'move file "c.txt" "d.txt"',
                    'delete file "b.txt"', 'delete file "d.txt"',
                    'create folder "first"', 'rename folder "first" "second"', 'delete folder "second"'):
        assert main.handle_command(command)
    assert not any((tmp_path / name).exists() for name in ("a.txt", "b.txt", "c.txt", "d.txt", "first", "second"))
    for launch in desktop_fakes:
        launch.assert_not_called()


@pytest.mark.parametrize("command", [
    'create file existing.txt', 'create folder occupied', 'delete file missing.txt',
    'delete folder occupied', 'rename file missing.txt renamed.txt',
    'rename folder missing renamed', 'copy file occupied copied', 'move file occupied moved',
    'rename file occupied renamed', 'rename folder existing.txt renamed',
])
def test_file_failures_stop_later_steps_without_touching_contents(command, tmp_path, capsys):
    (tmp_path / "existing.txt").write_text("keep")
    (tmp_path / "occupied").mkdir()
    (tmp_path / "occupied" / "keep.txt").write_text("keep child")
    assert main.handle_command(command + ' and create file later.txt') == []
    assert not (tmp_path / "later.txt").exists()
    assert (tmp_path / "existing.txt").read_text() == "keep"
    assert (tmp_path / "occupied" / "keep.txt").read_text() == "keep child"
    assert "Command execution failed" in capsys.readouterr().out
