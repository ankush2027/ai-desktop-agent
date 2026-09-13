from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from ai.errors import TaskExecutionError


class StepStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class TaskStep:
    action: Dict[str, Any]
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None


@dataclass
class Task:
    steps: List[TaskStep]
    task_id: str = field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = TaskStatus.PENDING


def execute_task(
    actions: List[Dict[str, Any]],
    executor: Callable[[Dict[str, Any]], None],
) -> Task:
    """Execute an already policy-approved plan sequentially as one task."""
    task = Task(steps=[TaskStep(action=action) for action in actions])
    task.status = TaskStatus.RUNNING

    for index, step in enumerate(task.steps, start=1):
        print(f"[AI] Executing action {index}/{len(task.steps)}")
        try:
            executor(step.action)
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = str(exc)
            task.status = TaskStatus.FAILED
            print(f"[AI] Task failed at step {index}/{len(task.steps)}")
            raise TaskExecutionError(
                f"AI task failed at step {index}."
            ) from exc
        step.status = StepStatus.SUCCEEDED

    task.status = TaskStatus.SUCCEEDED
    print(f"[AI] Task succeeded with {len(task.steps)} step(s)")
    return task
