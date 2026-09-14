# Direct script runs must enter pytest before importing application singletons.
if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


from ai.task_execution import StepStatus, TaskStatus, execute_task
from ai.errors import TaskExecutionError


def test_single_action_task_succeeds():
    calls = []
    task = execute_task(
        [{"action": "open", "target": "brave", "params": {}}],
        calls.append,
    )

    assert task.status == TaskStatus.SUCCEEDED
    assert task.steps[0].status == StepStatus.SUCCEEDED
    assert calls == [{"action": "open", "target": "brave", "params": {}}]


def test_multiple_actions_execute_in_order():
    calls = []
    actions = [
        {"action": "open", "target": "youtube", "params": {}},
        {"action": "search", "target": "Python DSA", "params": {}},
        {"action": "open", "target": "gmail", "params": {}},
    ]

    task = execute_task(actions, calls.append)

    assert task.status == TaskStatus.SUCCEEDED
    assert [step.status for step in task.steps] == [
        StepStatus.SUCCEEDED,
        StepStatus.SUCCEEDED,
        StepStatus.SUCCEEDED,
    ]
    assert calls == actions


def test_step_failure_stops_task_and_records_failed_step():
    calls = []

    def failing_executor(action):
        calls.append(action)
        if action["target"] == "Python":
            raise RuntimeError("search failed")

    actions = [
        {"action": "open", "target": "youtube", "params": {}},
        {"action": "search", "target": "Python", "params": {}},
        {"action": "open", "target": "gmail", "params": {}},
    ]

    try:
        execute_task(actions, failing_executor)
        assert False, "Expected TaskExecutionError"
    except TaskExecutionError:
        pass

    assert len(calls) == 2
