"""Input adapters produce typed events; events never contain desktop actions."""

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Optional

from memory.episodes import ContextEpisode, ContextTask
from context.continuity import ContinuityState


class ContextEventType(str, Enum):
    ARRIVE = "arrive"
    LEAVE = "leave"
    INSPECT = "inspect"
    ADD_TASK = "add_task"
    COMPLETE_TASK = "complete_task"
    CONTINUE = "continue"
    WORK_ON = "work_on"
    RECORD_TASK = "record_task"


@dataclass(frozen=True)
class ContextEvent:
    kind: ContextEventType
    name: Optional[str] = None
    description: Optional[str] = None
    task_id: Optional[str] = None
    view: str = "overview"


@dataclass
class ContextResult:
    message: str
    episode: Optional[ContextEpisode] = None
    task: Optional[ContextTask] = None
    reminders: list[ContextTask] = field(default_factory=list)
    continuity: Optional[ContinuityState] = None

    def to_dict(self):
        return asdict(self)


# Deliberately bounded, anchored grammar: recognition is separate from lifecycle
# and rules. New input adapters can construct the same events without this parser.
_ARRIVAL = re.compile(r"(?:i'm here|i am here|i've arrived|i have arrived)(?: now)?", re.I)
_NAMED_ARRIVAL = re.compile(r"(?:i'm|i am) at\s+(.+)", re.I)
_LEAVE = re.compile(r"(?:i'm leaving|i am leaving|i'm heading out|i am heading out)(?: now)?", re.I)
_TASK = re.compile(
    r"(?:remind me to|remember(?: that)?(?: i need to| i have to)?|i need to)\s+"
    r"(.+?)\s+before i leave", re.I,
)
_COMPLETE = re.compile(r"complete context task\s+([a-f0-9-]{36})", re.I)

_WORK_ON = re.compile(r"(?:i'm|i am) (?:currently )?working on\s+(.+)", re.I)
_RECORD_TASK = re.compile(r"remember(?: that)? i (?:need|have) to\s+(.+)", re.I)
_CONTINUITY = {
    "continue what i was doing": "overview", "where did i leave off": "overview",
    "what was i working on": "overview", "where was i": "overview",
    "continue my last task": "overview", "what was i doing": "overview",
    "what was unfinished": "pending", "what should i continue": "pending",
    "what was already completed": "completed",
}


def parse_context_event(command):
    text = command.strip().replace("’", "'").rstrip(".!?").strip()
    if text.lower() in _CONTINUITY:
        return ContextEvent(ContextEventType.CONTINUE, view=_CONTINUITY[text.lower()])
    if _ARRIVAL.fullmatch(text):
        return ContextEvent(ContextEventType.ARRIVE)
    match = _NAMED_ARRIVAL.fullmatch(text)
    if match:
        return ContextEvent(ContextEventType.ARRIVE, name=match.group(1))
    if _LEAVE.fullmatch(text):
        return ContextEvent(ContextEventType.LEAVE)
    if text.lower() in {"what is my current context", "what's my current context", "show current context"}:
        return ContextEvent(ContextEventType.INSPECT)
    match = _TASK.fullmatch(text)
    if match:
        return ContextEvent(ContextEventType.ADD_TASK, description=match.group(1))
    match = _WORK_ON.fullmatch(text)
    if match:
        return ContextEvent(ContextEventType.WORK_ON, description=match.group(1))
    match = _RECORD_TASK.fullmatch(text)
    if match:
        return ContextEvent(ContextEventType.RECORD_TASK, description=match.group(1))
    match = _COMPLETE.fullmatch(text)
    if match:
        return ContextEvent(ContextEventType.COMPLETE_TASK, task_id=match.group(1))
    return None
