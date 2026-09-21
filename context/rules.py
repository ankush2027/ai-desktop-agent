"""Explicit reminder-only rules. No dispatch, model calls, or side effects."""

from context.events import ContextEventType


CONTEXT_EXIT_RULE = {
    "event": ContextEventType.LEAVE,
    "task_status": "pending",
    "task_trigger": "context_exit",
    "effect": "surface_reminder",
}


def context_exit_reminders(event, episode_id, tasks):
    if event.kind != CONTEXT_EXIT_RULE['event']:
        return []
    return [task for task in tasks
            if task.episode_id == episode_id
            and task.status == CONTEXT_EXIT_RULE['task_status']
            and task.trigger == CONTEXT_EXIT_RULE['task_trigger']]
