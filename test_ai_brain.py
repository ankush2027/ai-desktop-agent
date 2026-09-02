import json

from ai import AIBrain
from context import ContextEngine
from memory import MemoryManager


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload

    def generate_text(self, prompt):
        return self.payload


class CaptureProvider:
    def __init__(self):
        self.prompt = None

    def generate_text(self, prompt):
        self.prompt = prompt
        return json.dumps({
            "actions": [
                {"action": "open", "target": "youtube", "params": {}},
                {"action": "search", "target": "Python", "params": {}},
            ]
        })


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


def test_real_natural_language_prompt_is_sized_and_structured_without_api_call():
    command = "Open YouTube and search for Python"
    context = ContextEngine(MemoryManager()).build_context(
        user_context={"raw_command": command},
        system_context={"mode": "ai"},
        query=command,
    )
    provider = CaptureProvider()
    brain = AIBrain(provider)

    plan = brain.plan(command, context)
    prompt = provider.prompt
    context_text = brain._format_context(context)

    assert plan["actions"][0]["action"] == "open"
    assert len(prompt) < 5000
    assert len(context_text) < 2000
    assert "Return only valid JSON." in prompt
    assert '{"actions":[{"action":"open","target":"example-target","params":{}}]}' in prompt
    assert "'available': ['safari', 'brave']" in prompt
    assert "'preferred': 'brave'" in prompt
    assert "target\":\"chrome\"" not in prompt
    assert "The user command is: Open YouTube and search for Python." in prompt
    assert "Context:" in prompt
    assert "Return only the JSON object" in prompt


if __name__ == "__main__":
    test_valid_action_plan_is_accepted()
    test_malformed_action_plan_is_rejected()
    test_unsupported_action_is_rejected()
    test_missing_target_is_rejected()
    test_invalid_json_is_rejected()
    test_real_natural_language_prompt_is_sized_and_structured_without_api_call()
    print("AI brain tests passed.")
