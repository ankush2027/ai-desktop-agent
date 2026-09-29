"""One fixed macOS workspace; no process discovery or custom launch arguments."""

import json

from ai.action_policy import ActionPolicy, ActionPolicyError
from memory import MemoryManager

CODING_APPS = ("vscode", "brave")


def _workspace_request(action, target, params):
    return ActionPolicy().validate([{
        "action": action, "target": target, "params": {} if params is None else params,
    }])[0]["target"]


def workspace_open_actions(definition):
    # Stored data is untrusted. Never let a path/site/extra parameter become an
    # open target, even though normal open actions support some local documents.
    if (not isinstance(definition, dict) or set(definition) != {"name", "apps"}
            or definition["name"] != "coding" or not isinstance(definition["apps"], list)):
        raise ActionPolicyError("Stored workspace is invalid.")
    if definition["apps"] != list(CODING_APPS):
        raise ActionPolicyError("Workspace applications do not match the supported coding definition.")
    return [{"action": "open", "target": app, "params": {}} for app in definition["apps"]]


def save_workspace(target="", params=None):
    name = _workspace_request("save_workspace", target, params)
    definition = {"name": name, "apps": list(CODING_APPS)}
    ActionPolicy().validate(workspace_open_actions(definition))
    with MemoryManager() as manager:
        manager.save_workspace(name, json.dumps(definition))
    print("Saved coding workspace: VS Code and Brave.")


def load_workspace(target="coding"):
    name = _workspace_request("restore_workspace", target, {})
    with MemoryManager() as manager:
        saved = manager.load_workspace(name)
    if saved is None:
        raise ActionPolicyError("Coding workspace has not been saved yet.")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        if not isinstance(saved, str) or len(saved) > 4096:
            raise ValueError
        definition = json.loads(saved, object_pairs_hook=unique_object)
    except (ValueError, TypeError, RecursionError):
        raise ActionPolicyError("Stored workspace is invalid.") from None
    workspace_open_actions(definition)
    return definition


def restore_workspace(target="", params=None):
    name = _workspace_request("restore_workspace", target, params)
    actions = ActionPolicy().validate(workspace_open_actions(load_workspace(name)))
    # Use the normal task runner and executor after validating the entire list.
    # Local imports avoid an executor/handler import cycle.
    from ai.task_execution import execute_task
    from executor import execute

    execute_task(actions, execute)
    print("Coding workspace launch requests completed; application readiness is not verified.")
