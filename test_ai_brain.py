import json

from ai import AIBrain


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload

    def generate_text(self, prompt):
        return self.payload


def test_valid_action_plan_is_accepted():
    brain = AIBrain(FakeProvider(json.dumps({
        "actions": [
            {"action": "open", "target": "chrome", "params": {}},
            {"action": "search", "target": "Python FastAPI", "params": {}},
        ]
    })))

    plan = brain.plan("open Chrome and search Python FastAPI")

    assert plan["actions"][0]["action"] == "open"
    assert plan["actions"][0]["target"] == "chrome"
    assert plan["actions"][1]["action"] == "search"
    assert plan["actions"][1]["target"] == "Python FastAPI"


def test_malformed_action_plan_is_rejected():
    brain = AIBrain(FakeProvider('{"actions": "not-a-list"}'))

    try:
        brain.plan("open Chrome")
        assert False, "Expected ValueError for malformed action plan"
    except ValueError:
        pass


def test_unsupported_action_is_rejected():
    brain = AIBrain(FakeProvider(json.dumps({
        "actions": [
            {"action": "execute", "target": "rm -rf /", "params": {}}
        ]
    })))

    try:
        brain.plan("execute dangerous command")
        assert False, "Expected ValueError for unsupported action"
    except ValueError:
        pass


def test_missing_target_is_rejected():
    brain = AIBrain(FakeProvider(json.dumps({
        "actions": [
            {"action": "open", "params": {}}
        ]
    })))

    try:
        brain.plan("open Chrome")
        assert False, "Expected ValueError for missing target"
    except ValueError:
        pass


def test_invalid_json_is_rejected():
    brain = AIBrain(FakeProvider("this is not valid json"))

    try:
        brain.plan("open Chrome")
        assert False, "Expected ValueError for invalid JSON"
    except ValueError:
        pass


if __name__ == "__main__":
    test_valid_action_plan_is_accepted()
    test_malformed_action_plan_is_rejected()
    test_unsupported_action_is_rejected()
    test_missing_target_is_rejected()
    test_invalid_json_is_rejected()
    print("AI brain tests passed.")
