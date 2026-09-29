"""Controlled macOS quit requests; no real applications are closed."""
import subprocess
from unittest.mock import Mock, patch

import pytest

import config
import executor
import main
from actions.apps import close_app
from actions.platforms import DesktopUnavailable, MacOSAdapter
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.brain import AIBrain
from ai.orchestrator import process_natural_language_command
from ai.plan_schema import validate_plan
from ai.errors import AIPlanningError, TaskExecutionError
from ai.task_execution import execute_task


def item(target, **params):
    return {"action": "close", "target": target, "params": params}


@pytest.fixture(autouse=True)
def mac():
    with patch("platform.system", return_value="Darwin"), patch("actions.platforms.subprocess.run") as run:
        yield run


@pytest.mark.parametrize("target,application", list(MacOSAdapter.apps.items()) + list(MacOSAdapter.browsers.items()))
def test_supported_close_through_policy_executor_adapter(target, application, mac):
    actions = ActionPolicy().validate([item(target.upper())])
    assert actions == [item(target)]
    execute_task(actions, executor.execute)
    mac.assert_called_once_with([
        "/usr/bin/osascript", "-e",
        f'if application "{application}" is running then tell application "{application}" to quit',
    ], check=True, timeout=30)


@pytest.mark.parametrize("target", ["youtube", "yt", "chrome", "unknown", "Finder", "SystemUIServer",
    "loginwindow", "kernel_task", "123", "/Applications/Calculator.app", "calculator; quit", 'Calculator"',
    "kill -9", "--args", "osascript", ""])
def test_unsupported_targets_rejected_at_policy_and_adapter(target, mac):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([item(target)])
    with pytest.raises(DesktopUnavailable):
        close_app(target)
    mac.assert_not_called()


@pytest.mark.parametrize("params", [{"pid": "123"}, {"force": "true"}, {"command": "quit"},
                                      {"path": "/tmp/app"}, {"url": "https://youtube.com"}])
def test_parameters_rejected(params, mac):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([item("calculator", **params)])
    with pytest.raises(ValueError):
        executor.execute(item("calculator", **params))
    mac.assert_not_called()


def test_configuration_cannot_introduce_arbitrary_application(mac):
    with patch.dict(config.APPS, {"injected": "Finder"}):
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([item("injected")])
        with pytest.raises(DesktopUnavailable):
            close_app("injected")
    mac.assert_not_called()


def test_natural_language_uses_unchanged_ai_route_and_policy(mac):
    provider = Mock()
    provider.generate_text.return_value = '{"actions":[{"action":"close","target":"Calculator","params":{}}]}'
    brain = AIBrain(provider=provider)
    assert main.route_command("Close Calculator") == ("ai", None)
    with patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy:
        assert process_natural_language_command("Close Calculator", brain=brain) == [item("calculator")]
    policy.assert_called_once()
    mac.assert_called_once()
    assert "close accepts only" in provider.generate_text.call_args.args[0]


def test_entire_plan_validated_before_quit(mac):
    brain = Mock()
    brain.plan.return_value = {"actions": [item("calculator"), item("youtube")]}
    with pytest.raises(ActionPolicyError):
        process_natural_language_command("Close Calculator and YouTube", brain=brain)
    mac.assert_not_called()


@pytest.mark.parametrize("error", [OSError(), subprocess.CalledProcessError(1, "osascript"),
                                   subprocess.TimeoutExpired("osascript", 30)])
def test_quit_failure_stops_remaining_actions(error, mac):
    mac.side_effect = error
    with pytest.raises(TaskExecutionError):
        execute_task(ActionPolicy().validate([item("calculator"), item("brave")]), executor.execute)
    assert mac.call_count == 1


def test_close_remains_unavailable_on_windows(mac):
    with patch("platform.system", return_value="Windows"):
        with pytest.raises(AIPlanningError):
            validate_plan({"actions": [item("calculator")]})
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([item("calculator")])
        with pytest.raises(RuntimeError):
            close_app("calculator")
        assert "close accepts only" not in AIBrain(provider=Mock()).build_prompt("Close Calculator")
    mac.assert_not_called()
