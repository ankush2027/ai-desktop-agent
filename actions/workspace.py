"""Mac workspace management; all launches are ordinary policy-checked actions."""

import json

from ai.action_policy import ActionPolicy, ActionPolicyError
from actions.workspace_definition import (CODING_APPS, workspace_name, validate_workspace,
                                          workspace_open_actions as _open_actions)
from memory import MemoryManager


def _workspace_request(action, target, params):
    return ActionPolicy().validate([{
        "action": action, "target": target, "params": {} if params is None else params,
    }])[0]


def workspace_open_actions(definition):
    try:
        return _open_actions(definition)
    except (ValueError, RuntimeError) as exc:
        raise ActionPolicyError(str(exc)) from None


def _decode_workspace(saved, name):
    if saved is None:
        raise ActionPolicyError("Workspace has not been saved yet.")

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
        definition = validate_workspace(json.loads(saved, object_pairs_hook=unique_object))
        if definition["name"] != name:
            raise ValueError
    except (ValueError, RuntimeError, TypeError, RecursionError):
        raise ActionPolicyError("Stored workspace is invalid.") from None
    return definition


def _save_validated(manager, definition):
    ActionPolicy().validate(workspace_open_actions(definition))
    encoded = json.dumps(definition)
    if len(encoded) > 4096:
        raise ActionPolicyError("Workspace definition is too large.")
    manager.save_workspace(definition["name"], encoded)


def save_workspace(target="", params=None):
    name = _workspace_request("save_workspace", target, params)["target"]
    definition = {"name": name, "apps": list(CODING_APPS)}
    # Keep the original coding shortcut and its exact legacy data shape.
    ActionPolicy().validate(workspace_open_actions(definition))
    with MemoryManager() as manager:
        manager.save_workspace(name, json.dumps(definition))
    print("Saved coding workspace: VS Code and Brave.")


def load_workspace(target="coding"):
    name = _workspace_request("restore_workspace", target, {})["target"]
    with MemoryManager() as manager:
        return _decode_workspace(manager.load_workspace(name), name)


def restore_workspace(target="", params=None):
    name = _workspace_request("restore_workspace", target, params)["target"]
    actions = ActionPolicy().validate(workspace_open_actions(load_workspace(name)))
    from ai.task_execution import execute_task
    from executor import execute

    execute_task(actions, execute)
    print(f"Workspace {name} launch requests completed; application readiness is not verified.")


def list_workspaces(target="workspaces", params=None):
    _workspace_request("list_workspaces", target, params)
    with MemoryManager() as manager:
        names = manager.list_workspaces()
    try:
        if any(workspace_name(name) != name for name in names):
            raise ValueError
    except ValueError:
        raise ActionPolicyError("Stored workspace name is invalid.") from None
    print("Saved workspaces: " + (", ".join(names) if names else "none"))
    return names


def create_workspace(target="", params=None):
    item = _workspace_request("create_workspace", target, params)
    definition = {"name": item["target"], **item["params"]}
    with MemoryManager() as manager, manager.workspace_transaction():
        if manager.load_workspace(item["target"]) is not None:
            raise ActionPolicyError("Workspace already exists; use update_workspace.")
        _save_validated(manager, definition)
    print(f"Created workspace {item['target']}.")


def update_workspace(target="", params=None):
    item = _workspace_request("update_workspace", target, params)
    name = item["target"]
    kind = "folder" if "folder" in item["params"] else "app"
    value = item["params"][kind]
    with MemoryManager() as manager, manager.workspace_transaction():
        definition = _decode_workspace(manager.load_workspace(name), name)
        definition.setdefault("urls", [])
        entries = definition.setdefault("folders", []) if kind == "folder" else definition["apps"]
        if item["params"]["operation"] == "add":
            if value in entries:
                raise ActionPolicyError("Workspace item is already present.")
            entries.append(value)
        else:
            if value not in entries:
                raise ActionPolicyError("Workspace item is not present.")
            entries.remove(value)
        _save_validated(manager, definition)
    print(f"Updated workspace {name}.")


def delete_workspace(target="", params=None):
    name = _workspace_request("delete_workspace", target, params)["target"]
    with MemoryManager() as manager:
        if not manager.delete_workspace(name):
            raise ActionPolicyError("Workspace has not been saved yet.")
    print(f"Deleted saved workspace {name}.")
