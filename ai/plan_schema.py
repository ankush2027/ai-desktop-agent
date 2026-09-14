"""The shared, bounded schema for AI action plans."""

from ai.errors import AIPlanningError

ALLOWED_ACTIONS = {"open", "search", "list", "help", "draft_email"}
MAX_ACTIONS = 10
MAX_RESPONSE_CHARS = 32768


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
        if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
            reject()
        if not isinstance(target, str) or not target.strip() or not isinstance(params, dict):
            reject()
        # Every currently supported parameter is plain text. This also rejects
        # deep or cyclic injected structures before any recursive processing.
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in params.items()):
            reject()
        total += len(action) + len(target) + sum(len(key) + len(value) for key, value in params.items())
        if total > MAX_RESPONSE_CHARS:
            reject()
        normalized.append({"action": action, "target": target, "params": dict(params)})
    return {"actions": normalized}
