"""Persisted context state; separate from permanent preference memories."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


class ContextStateError(ValueError):
    """Invalid context operation; messages contain no user payloads."""


def new_id():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def require_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ContextStateError("Context fields must contain 1 to 4000 characters.")
    return value.strip()


@dataclass
class ContextEpisode:
    id: str
    name: str
    started_at: str
    status: str = "active"
    ended_at: Optional[str] = None
    memory_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class ContextTask:
    id: str
    episode_id: str
    description: str
    created_at: str
    kind: str = "task"
    trigger: str = "context_exit"
    status: str = "pending"
    completed_at: Optional[str] = None


@dataclass
class ContextNote:
    id: str
    episode_id: str
    content: str
    category: str  # contextual or temporary; never a permanent preference
    created_at: str
