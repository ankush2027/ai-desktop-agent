from typing import Any, Dict, List, Optional

from config import BROWSERS
from memory.manager import MemoryManager
from context.models import MemoryContextEntry, StructuredContext
from context.runtime import RuntimeContext


class ContextEngine:
    """Assemble structured context using runtime info and stored memories."""

    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager

    def _normalize_memories(self, memories: List[Any]) -> List[MemoryContextEntry]:
        """Convert memory objects into minimal context entries."""
        return [
            MemoryContextEntry(
                id=memory.id,
                category=memory.category,
                content=memory.content,
                confidence=memory.confidence,
            )
            for memory in memories
        ]

    def _build_summary(self, runtime: Dict[str, Any], memories: List[MemoryContextEntry]) -> str:
        """Create a simple deterministic summary string."""
        current_time = runtime.get("current_datetime", "unknown")
        if not memories:
            return f"No relevant memories found at {current_time}."

        memory_lines = "; ".join(memory.content for memory in memories[:3])
        return f"Current time: {current_time}. Relevant memories: {memory_lines}."

    def build_context(
        self,
        user_context: Optional[Dict[str, Any]] = None,
        system_context: Optional[Dict[str, Any]] = None,
        categories: Optional[List[str]] = None,
        query: Optional[str] = None,
        max_memories: int = 5,
    ) -> StructuredContext:
        """
        Build a structured context object from runtime state and relevant memories.

        The ContextEngine uses MemoryManager exclusively; it never accesses MemoryStore
        or SQLite directly.
        """
        runtime = RuntimeContext.collect()
        user_context = user_context or {}
        system_context = {
            "browsers": BROWSERS,
            **(system_context or {}),
        }

        selected_memories = []
        if query:
            selected_memories = self.memory_manager.search_memories(query)
        elif categories:
            for category in categories:
                selected_memories.extend(self.memory_manager.get_memories_by_category(category))
        else:
            selected_memories = self.memory_manager.get_all_memories()

        deduped: List[Any] = []
        seen_ids = set()
        for memory in selected_memories:
            if memory.id not in seen_ids:
                seen_ids.add(memory.id)
                deduped.append(memory)

        relevant_memories = self._normalize_memories(deduped[:max_memories])
        summary = self._build_summary(runtime, relevant_memories)

        return StructuredContext(
            timestamp=runtime["current_datetime"],
            runtime=runtime,
            user_context=user_context,
            system_context=system_context,
            relevant_memories=relevant_memories,
            summary=summary,
        )
