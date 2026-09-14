from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MemoryContextEntry:
    """A structured representation of a memory used in context assembly."""

    id: str
    category: str
    content: str
    confidence: float


@dataclass
class StructuredContext:
    """A lightweight, deterministic context structure."""

    timestamp: str
    runtime: Dict[str, Any] = field(default_factory=dict)
    user_context: Dict[str, Any] = field(default_factory=dict)
    system_context: Dict[str, Any] = field(default_factory=dict)
    relevant_memories: List[MemoryContextEntry] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert the structured context into a serializable dictionary."""
        return {
            "timestamp": self.timestamp,
            "runtime": self.runtime,
            "user_context": self.user_context,
            "system_context": self.system_context,
            "relevant_memories": [
                {
                    "id": memory.id,
                    "category": memory.category,
                    "content": memory.content,
                    "confidence": memory.confidence,
                }
                for memory in self.relevant_memories
            ],
            "summary": self.summary,
        }
