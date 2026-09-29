"""Controlled workspace persistence and restore; OS launches are always mocked."""
import json
from unittest.mock import Mock, patch

import pytest

import executor
import main
from actions.workspace import load_workspace, restore_workspace, save_workspace, workspace_open_actions
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.brain import AIBrain
from ai.errors import AIPlanningError, TaskExecutionError
from ai.orchestrator import process_natural_language_command
from ai.plan_schema import validate_plan
from memory import MemoryManager
from memory.errors import MemoryStorageError

DEFINITION = {"name": "coding", "apps": ["vscode", "brave"]}
OPEN_ACTIONS = [{"action": "open", "target": app, "params": {}} for app in DEFINITION["apps"]]


def action(verb, target="coding", **params):
    return {"action": verb, "target": target, "params": params}


@pytest.fixture(autouse=True)
def mac_desktop():
    with patch("platform.system", return_value="Darwin"), \
         patch("actions.platforms.subprocess.run") as launch, \
         patch("subprocess.Popen") as popen, patch("os.system") as shell, \
         patch("webbrowser.open") as web:
        yield launch
        popen.assert_not_called()
        shell.assert_not_called()
        web.assert_not_called()


def test_save_load_and_idempotence_across_connections(mac_desktop):
    with MemoryManager() as manager:
        original = manager.add_memory("Keep existing preference", "user_preference")
    save_workspace("coding")
    save_workspace("coding")
    assert load_workspace() == DEFINITION
    with MemoryManager() as manager:
        assert json.loads(manager.load_workspace("coding")) == DEFINITION
        assert len(manager.store._execute("SELECT * FROM workspaces", rows=True)) == 1
        assert manager.get_memory(original).content == "Keep existing preference"
        assert manager.get_memory_count() == 1
    mac_desktop.assert_not_called()


def test_workspace_generates_only_normal_open_actions():
    assert workspace_open_actions(DEFINITION) == OPEN_ACTIONS


def test_restore_policy_validates_all_apps_before_existing_executor(mac_desktop):
    save_workspace("coding")
    with patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy, \
         patch.object(executor, "execute", wraps=executor.execute) as execute:
        def launched(*args, **kwargs):
            assert any(call.args[1] == OPEN_ACTIONS for call in policy.call_args_list)
        mac_desktop.side_effect = launched
        restore_workspace("coding")
        assert [call.args[0] for call in execute.call_args_list] == OPEN_ACTIONS
    assert [call.args[0] for call in mac_desktop.call_args_list] == [
        ["/usr/bin/open", "-a", "/Applications/VS CODE.app"], ["/usr/bin/open", "-a", "Brave Browser"],
    ]
    assert all(call.kwargs == {"check": True} for call in mac_desktop.call_args_list)


@pytest.mark.parametrize("verb,command", [
    ("save_workspace", "Save my coding workspace"),
    ("restore_workspace", "Restore my coding workspace"),
])
def test_natural_language_uses_existing_route_planner_policy_executor(verb, command, mac_desktop):
    if verb == "restore_workspace":
        save_workspace("coding")
    provider = Mock()
    provider.generate_text.return_value = json.dumps({"actions": [action(verb)]})
    assert main.route_command(command) == ("ai", None)
    with patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy:
        result = process_natural_language_command(command, brain=AIBrain(provider=provider))
    assert result == [action(verb)]
    assert any(call.args[1] == [action(verb)] for call in policy.call_args_list)
    prompt = provider.generate_text.call_args.args[0]
    assert "one save_workspace action with target coding and empty params" in prompt
    assert "one restore_workspace action with target coding and empty params" in prompt
    assert mac_desktop.call_count == (2 if verb == "restore_workspace" else 0)


@pytest.mark.parametrize("verb", ["save_workspace", "restore_workspace"])
@pytest.mark.parametrize("target", ["other", "", "../coding", "/tmp/coding", "coding; whoami", "123"])
def test_policy_and_direct_handlers_reject_unknown_names(verb, target, mac_desktop):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([action(verb, target)])
    handler = save_workspace if verb == "save_workspace" else restore_workspace
    with pytest.raises(ActionPolicyError):
        handler(target)
    mac_desktop.assert_not_called()


@pytest.mark.parametrize("params", [{"apps": "Terminal"}, {"path": "/tmp/evil"}, {"pid": "12"},
    {"command": "anything"}, {"force": "true"}, {"apps": ["vscode", "brave"]}])
@pytest.mark.parametrize("verb", ["save_workspace", "restore_workspace"])
def test_workspace_accepts_no_ai_parameters(verb, params, mac_desktop):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([action(verb, **params)])
    with pytest.raises(TaskExecutionError):
        from ai.task_execution import execute_task
        execute_task([action(verb, **params)], executor.execute)
    mac_desktop.assert_not_called()


@pytest.mark.parametrize("apps", [
    ["vscode", "unknown"], ["vscode", "Terminal"], ["vscode", "chrome"],
    ["vscode", "/Applications/Brave Browser.app"], ["vscode", "Finder"],
    ["vscode", "123"], ["vscode", "kill -9"], ["vscode", "brave; command"],
    ["vscode", "https://youtube.com"], ["vscode", "desktop"], ["vscode", "calculator"],
    ["vscode", {"action": "delete", "target": "notes.txt"}],
    ["vscode", "vscode"], ["vscode"], [],
])
def test_saved_application_tampering_launches_nothing(apps, mac_desktop):
    with MemoryManager() as manager:
        manager.save_workspace("coding", json.dumps({"name": "coding", "apps": apps}))
    with pytest.raises(ActionPolicyError):
        restore_workspace("coding")
    mac_desktop.assert_not_called()


@pytest.mark.parametrize("saved", [
    "not json", "null", "[]", "{}", '{"name":"other","apps":["vscode","brave"]}',
    '{"name":"coding","apps":"vscode"}',
    '{"name":"coding","apps":["vscode","brave"],"command":"anything"}',
    '{"name":"other","name":"coding","apps":["vscode","brave"]}',
    '[' * 1500 + '0' + ']' * 1500, ' ' * 4097, b'invalid bytes',
])
def test_malformed_storage_rejected(saved, mac_desktop):
    with MemoryManager() as manager:
        manager.save_workspace("coding", saved)
    with pytest.raises(ActionPolicyError):
        restore_workspace("coding")
    mac_desktop.assert_not_called()


def test_current_app_allowlist_is_rechecked_before_any_launch(mac_desktop):
    save_workspace("coding")
    from actions.platforms import MacOSAdapter
    with patch.dict(MacOSAdapter.browsers, {"safari": "Safari"}, clear=True):
        with pytest.raises(ActionPolicyError):
            restore_workspace("coding")
    mac_desktop.assert_not_called()


def test_save_rejects_unavailable_mapping_without_persisting(mac_desktop):
    from actions.platforms import MacOSAdapter
    with patch.dict(MacOSAdapter.apps, {}, clear=True):
        with pytest.raises(ActionPolicyError):
            save_workspace("coding")
    with MemoryManager() as manager:
        assert manager.load_workspace("coding") is None
    mac_desktop.assert_not_called()


def test_missing_workspace_fails_safely(mac_desktop):
    with pytest.raises(ActionPolicyError, match="has not been saved"):
        restore_workspace("coding")
    mac_desktop.assert_not_called()


def test_policy_rejection_blocks_entire_restore(mac_desktop):
    save_workspace("coding")
    original = ActionPolicy.validate
    def validate(self, actions, **kwargs):
        if actions == OPEN_ACTIONS:
            raise ActionPolicyError("Open actions rejected.")
        return original(self, actions, **kwargs)
    with patch.object(ActionPolicy, "validate", validate), pytest.raises(ActionPolicyError):
        restore_workspace("coding")
    mac_desktop.assert_not_called()


def test_launch_failure_stops_remaining_apps(mac_desktop):
    save_workspace("coding")
    mac_desktop.side_effect = OSError("App unavailable")
    with pytest.raises(TaskExecutionError):
        restore_workspace("coding")
    assert mac_desktop.call_count == 1
    assert load_workspace() == DEFINITION


@pytest.mark.parametrize("operation", ["save_workspace", "load_workspace"])
def test_storage_failure_does_not_launch_apps(operation, mac_desktop):
    with patch.object(MemoryManager, operation, side_effect=MemoryStorageError("Storage unavailable")):
        with pytest.raises(MemoryStorageError):
            (save_workspace if operation == "save_workspace" else restore_workspace)("coding")
    mac_desktop.assert_not_called()


@pytest.mark.parametrize("system", ["Windows", "Linux"])
@pytest.mark.parametrize("verb", ["save_workspace", "restore_workspace"])
def test_workspaces_are_mac_only_and_table_is_lazy(system, verb, mac_desktop):
    with patch("platform.system", return_value=system):
        with pytest.raises(AIPlanningError):
            validate_plan({"actions": [action(verb)]})
        with pytest.raises(ActionPolicyError):
            (save_workspace if verb == "save_workspace" else restore_workspace)("coding")
        assert "one save_workspace action" not in AIBrain(provider=Mock()).build_prompt("Save workspace")
        with MemoryManager() as manager:
            assert manager.store._execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workspaces'", rows=True) == []
    mac_desktop.assert_not_called()
