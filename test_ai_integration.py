from ai.orchestrator import process_natural_language_command
from main import route_command
from parser import parse_command


class FakeBrain:
    def __init__(self, plan):
        self.plan_data = plan

    def plan(self, command, context=None):
        return self.plan_data


class FakeContextEngine:
    def build_context(self, **kwargs):
        return type("FakeContext", (), {"to_dict": lambda self: {"summary": "fake"}})()


def test_route_command_distinguishes_v1_from_ai_paths():
    route, parsed = route_command("open file notes.txt")
    assert route == "v1"
    assert parsed == [{"action": "open", "target": "file notes.txt", "params": {}}]

    route, parsed = route_command("open Chrome and search Python FastAPI")
    assert route == "ai"
    assert parsed is None

    route, parsed = route_command("create file notes.txt and delete file old.txt")
    assert route == "v1"
    assert parsed is not None


def test_ai_plan_generation_is_passed_to_execution():
    calls = []

    def fake_execute(command):
        calls.append(command)

    plan = {
        "actions": [
            {"action": "open", "target": "chrome", "params": {}},
            {"action": "search", "target": "Python FastAPI", "params": {}},
        ]
    }

    actions = process_natural_language_command(
        "open Chrome and search Python FastAPI",
        executor_func=fake_execute,
        brain=FakeBrain(plan),
        context_engine=FakeContextEngine(),
    )

    assert actions == plan["actions"]
    assert calls == plan["actions"]


def test_multiple_actions_are_dispatched_in_order():
    calls = []

    def fake_execute(command):
        calls.append(command["action"])

    plan = {
        "actions": [
            {"action": "open", "target": "chrome", "params": {}},
            {"action": "search", "target": "Python", "params": {}},
            {"action": "list", "target": "desktop", "params": {}},
        ]
    }

    process_natural_language_command(
        "open chrome then search python then list desktop",
        executor_func=fake_execute,
        brain=FakeBrain(plan),
        context_engine=FakeContextEngine(),
    )

    assert calls == ["open", "search", "list"]


def test_malformed_ai_plan_is_rejected_safely():
    calls = []

    def fake_execute(command):
        calls.append(command)

    try:
        process_natural_language_command(
            "open chrome",
            executor_func=fake_execute,
            brain=FakeBrain({"actions": "bad"}),
            context_engine=FakeContextEngine(),
        )
        assert False, "Expected ValueError for malformed AI plan"
    except ValueError:
        pass

    assert calls == []


def test_existing_v1_execution_still_works():
    parsed = parse_command("open file notes.txt")

    assert parsed == [{"action": "open", "target": "file notes.txt", "params": {}}]


if __name__ == "__main__":
    test_route_command_distinguishes_v1_from_ai_paths()
    test_ai_plan_generation_is_passed_to_execution()
    test_multiple_actions_are_dispatched_in_order()
    test_malformed_ai_plan_is_rejected_safely()
    test_existing_v1_execution_still_works()
    print("AI integration tests passed.")
