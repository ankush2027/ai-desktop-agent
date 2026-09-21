"""Deterministic continuity derived from one episode's persisted state."""

from dataclasses import asdict, dataclass
from datetime import datetime


NO_CONTINUITY = "I don't have enough recent context to determine what you were working on."


@dataclass
class ContinuityState:
    episode: dict
    active_intentions: list[dict]
    pending_tasks: list[dict]
    completed_tasks: list[dict]
    relevant_notes: list[dict]
    relevant_memories: list[dict]
    last_activity: dict

    def to_dict(self):
        return asdict(self)

    def selection_key(self):
        unfinished = bool(self.active_intentions or self.pending_tasks)
        return (unfinished, unfinished and self.episode['status'] == 'active',
                bool(self.completed_tasks), datetime.fromisoformat(self.last_activity['at']),
                datetime.fromisoformat(self.episode['started_at']), self.episode['id'])

    def summary(self, view="overview"):
        parts = [f"Context: {self.episode['name']} ({self.episode['status']})."]
        if view in {"overview", "pending"}:
            if self.active_intentions:
                parts.append("Recorded intentions: " + "; ".join(
                    item['description'] for item in self.active_intentions) + ".")
            if self.pending_tasks:
                parts.append("Unfinished: " + "; ".join(
                    item['description'] for item in self.pending_tasks) + ".")
            if not self.active_intentions and not self.pending_tasks:
                parts.append("No unfinished tasks or intentions recorded in this context.")
        if view in {"overview", "completed"}:
            if self.completed_tasks:
                parts.append("Already completed: " + "; ".join(
                    item['description'] for item in self.completed_tasks) + ".")
            elif view == "completed":
                parts.append("No completed tasks recorded in this context.")
        if view == "overview":
            if self.relevant_notes:
                parts.append("Context notes: " + "; ".join(item['content'] for item in self.relevant_notes) + ".")
            if self.relevant_memories:
                parts.append("Linked memories: " + "; ".join(item['content'] for item in self.relevant_memories) + ".")
        return " ".join(parts)


def from_snapshot(snapshot):
    tasks = snapshot['tasks']
    notes = snapshot['notes']
    memories = snapshot['relevant_memories']
    episode = snapshot['episode']
    if not (tasks or notes or memories or episode['metadata']):
        return None
    activities = [{"kind": "task_created", "at": task['created_at'], "item_id": task['id']} for task in tasks]
    activities += [{"kind": "task_completed", "at": task['completed_at'], "item_id": task['id']}
                   for task in tasks if task['status'] == 'completed']
    activities += [{"kind": "note_added", "at": note['created_at'], "item_id": note['id']} for note in notes]
    last_activity = max(activities, key=lambda item: datetime.fromisoformat(item['at'])) if activities else {
        "kind": "episode_closed" if episode['ended_at'] else "episode_started",
        "at": episode['ended_at'] or episode['started_at'], "item_id": episode['id'],
    }
    return ContinuityState(
        episode=episode,
        active_intentions=[item for item in tasks if item['status'] == 'pending' and item['kind'] == 'intention'],
        pending_tasks=[item for item in tasks if item['status'] == 'pending' and item['kind'] == 'task'],
        completed_tasks=[item for item in tasks if item['status'] == 'completed'],
        relevant_notes=notes, relevant_memories=memories, last_activity=last_activity,
    )
