import io
from contextlib import redirect_stdout

import main
from ai.errors import AIProviderError
from ai.action_policy import ActionPolicyError
from ai.orchestrator import process_natural_language_command
from context import ContextEngine
from main import route_command
from memory import MemoryManager
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

    for command in ("open yt", "open google", "open gmail", "open github",
                    "open vscode", "open calculator", "open brave", "open safari"):
        route, parsed = route_command(command)
        assert route == "v1"
        assert parsed is not None

    route, parsed = route_command("Open my preferred browser.")
    assert route == "ai"
    assert parsed is None


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


def test_ai_logging_reports_plan_and_execution_progress():
    plan = {
        "actions": [
            {"action": "open", "target": "youtube", "params": {}},
            {
                "action": "search",
                "target": "Python",
                "params": {"engine": "google", "query": "Python"},
            },
        ]
    }

    output_buffer = io.StringIO()
    with redirect_stdout(output_buffer):
        process_natural_language_command(
            "Open YouTube and search for Python",
            executor_func=lambda command: None,
            brain=FakeBrain(plan),
            context_engine=FakeContextEngine(),
        )

    output = output_buffer.getvalue()
    assert "[AI] Received natural-language command:" in output
    assert "[AI] Building context" in output
    assert "[AI] Calling AIBrain" in output
    assert "[AI] Received validated action plan with 2 action(s)" in output
    assert "[AI] Action 1: action=open, target=youtube, params={}" in output
    assert (
        "[AI] Action 2: action=search, target=Python, "
        "params={'engine': 'google', 'query': 'Python'}"
    ) in output
    assert "[AI] Executing action 1/2" in output
    assert "[AI] Executing action 2/2" in output


def test_browser_preference_plan_passes_policy():
    plan = {
        "actions": [
            {
                "action": "open",
                "target": "brave",
                "params": {"browser": "brave"},
            }
        ]
    }
    executed = []

    actions = process_natural_language_command(
        "Open my preferred browser",
        executor_func=executed.append,
        brain=FakeBrain(plan),
        context_engine=FakeContextEngine(),
    )

    assert actions == plan["actions"]
    assert executed == plan["actions"]


def test_preferred_browser_mode_plan_passes_policy_and_executes():
    plan = {
        "actions": [
            {
                "action": "open",
                "target": "brave",
                "params": {"mode": "dark"},
            }
        ]
    }
    executed = []

    actions = process_natural_language_command(
        "Open my preferred browser",
        executor_func=executed.append,
        brain=FakeBrain(plan),
        context_engine=FakeContextEngine(),
    )

    assert actions == plan["actions"]
    assert executed == plan["actions"]


def test_realistic_youtube_search_plan_passes_policy_and_executes():
    plan = {
        "actions": [
            {
                "action": "open",
                "target": "brave",
                "params": {
                    "theme": "dark",
                    "url": "https://www.youtube.com/results?search_query=Python",
                },
            }
        ]
    }
    executed = []

    actions = process_natural_language_command(
        "Open YouTube and search for Python",
        executor_func=executed.append,
        brain=FakeBrain(plan),
        context_engine=FakeContextEngine(),
    )

    assert actions == plan["actions"]
    assert executed == plan["actions"]


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


def test_ai_failure_does_not_execute_actions():
    calls = []

    def failing_process(command):
        raise AIProviderError("AI service unavailable.")

    original_process = main.process_natural_language_command
    original_execute = main.execute
    try:
        main.process_natural_language_command = failing_process
        main.execute = calls.append
        result = main.handle_command("Open my preferred browser.")
    finally:
        main.process_natural_language_command = original_process
        main.execute = original_execute

    assert result == []
    assert calls == []


def test_policy_failure_executes_zero_actions():
    calls = []
    plan = {
        "actions": [
            {"action": "open", "target": "brave", "params": {}},
            {"action": "delete", "target": "notes.txt", "params": {"type": "file"}},
        ]
    }

    try:
        process_natural_language_command(
            "open brave and delete notes.txt",
            executor_func=calls.append,
            brain=FakeBrain(plan),
            context_engine=FakeContextEngine(),
        )
        assert False, "Expected ActionPolicyError"
    except ActionPolicyError:
        pass

    assert calls == []


def test_deterministic_command_does_not_require_ai():
    executed = []
    original_process = main.process_natural_language_command
    original_execute = main.execute
    try:
        main.process_natural_language_command = lambda command: (_ for _ in ()).throw(
            AssertionError("deterministic command must not call AI")
        )
        main.execute = executed.append
        result = main.handle_command("open yt")
    finally:
        main.process_natural_language_command = original_process
        main.execute = original_execute

    assert result == [{"action": "open", "target": "yt", "params": {}}]
    assert executed == result


def test_existing_v1_execution_still_works():
    parsed = parse_command("open file notes.txt")

    assert parsed == [{"action": "open", "target": "file notes.txt", "params": {}}]


def test_context_dependent_open_reaches_ai_with_preference_context():
    manager = MemoryManager()
    manager.clear_all_memories()
    manager.add_memory("I prefer Brave", "user_preference", 1.0)
    captured = {}

    class CapturingBrain:
        def plan(self, command, context=None):
            captured["command"] = command
            captured["context"] = context.to_dict()
            return {"actions": [{"action": "open", "target": "brave", "params": {}}]}

    executed = []
    actions = process_natural_language_command(
        "Open my preferred browser.",
        executor_func=executed.append,
        brain=CapturingBrain(),
        context_engine=ContextEngine(manager),
    )

    assert actions == [{"action": "open", "target": "brave", "params": {}}]
    assert executed == actions
    assert any(
        memory["content"] == "I prefer Brave"
        and memory["category"] == "user_preference"
        for memory in captured["context"]["relevant_memories"]
    )


def test_handle_command_routes_context_dependent_open_to_ai():
    calls = []
    original_process = main.process_natural_language_command
    original_execute = main.execute

    def fake_process(command):
        calls.append(command)
        return [{"action": "open", "target": "brave", "params": {}}]

    try:
        main.process_natural_language_command = fake_process
        main.execute = lambda command: (_ for _ in ()).throw(
            AssertionError("context-dependent open must not use V1 execution")
        )

        result = main.handle_command("Open my preferred browser.")
    finally:
        main.process_natural_language_command = original_process
        main.execute = original_execute

    assert calls == ["Open my preferred browser."]
    assert result == [{"action": "open", "target": "brave", "params": {}}]


if __name__ == "__main__":
    test_route_command_distinguishes_v1_from_ai_paths()
    test_ai_plan_generation_is_passed_to_execution()
    test_multiple_actions_are_dispatched_in_order()
    test_malformed_ai_plan_is_rejected_safely()
    test_existing_v1_execution_still_works()
    print("AI integration tests passed.")
