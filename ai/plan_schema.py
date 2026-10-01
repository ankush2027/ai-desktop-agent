"""The shared, bounded schema for AI action plans."""

import platform

from ai.errors import AIPlanningError

ALLOWED_ACTIONS = {"open", "search", "list", "help", "draft_email"}
WORKSPACE_ACTIONS = {"save_workspace", "restore_workspace", "list_workspaces",
                     "create_workspace", "update_workspace", "delete_workspace"}
MAX_ACTIONS = 10
MAX_RESPONSE_CHARS = 32768


def allowed_actions():
    return ALLOWED_ACTIONS | ({"close"} | WORKSPACE_ACTIONS if platform.system() == "Darwin" else set())


def validate_plan(payload):
    def reject():
        raise AIPlanningError("AI returned an unusable action plan.")

    if not isinstance(payload, dict) or set(payload) != {"actions"}:
        reject()
    actions = payload["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
        reject()
    normalized = []
    total = 0
    for item in actions:
        if not isinstance(item, dict) or set(item) - {"action", "target", "params"}:
            reject()
        action, target, params = item.get("action"), item.get("target"), item.get("params", {})
        if not isinstance(action, str) or action not in allowed_actions():
            reject()
        if not isinstance(target, str) or not target.strip() or not isinstance(params, dict):
            reject()
        copied_params = {}
        for key, value in params.items():
            if not isinstance(key, str):
                reject()
            if action == "create_workspace" and key in {"apps", "urls"}:
                if (not isinstance(value, list) or len(value) > MAX_ACTIONS
                        or any(not isinstance(entry, str) for entry in value)):
                    reject()
                copied_params[key] = list(value)
                total += len(key) + sum(len(entry) for entry in value)
            else:
                if not isinstance(value, str):
                    reject()
                copied_params[key] = value
                total += len(key) + len(value)
        total += len(action) + len(target)
        if total > MAX_RESPONSE_CHARS:
            reject()
        normalized.append({"action": action, "target": target, "params": copied_params})
    return {"actions": normalized}
