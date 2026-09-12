import re
from typing import Any, Dict, List, Optional

from config import BROWSERS
from memory.manager import MemoryManager
from context.models import MemoryContextEntry, StructuredContext
from context.runtime import RuntimeContext


class ContextEngine:
    """Assemble structured context using runtime info and stored memories."""

    _TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
    _STOP_WORDS = {
        "a", "an", "and", "for", "i", "is", "my", "of", "open",
        "the", "to", "with",
    }

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

    @classmethod
    def _tokens(cls, text: str) -> set:
        """Return simple normalized tokens for deterministic overlap scoring."""
        tokens = set(cls._TOKEN_PATTERN.findall(text.lower()))
        if "preferred" in tokens:
            tokens.add("prefer")
        return tokens - cls._STOP_WORDS

    @staticmethod
    def _is_browser_preference(memory: Any) -> bool:
        """Identify the supported browser preference shape without semantic lookup."""
        browsers = "|".join(re.escape(browser) for browser in BROWSERS["available"])
        return (
            memory.category == "user_preference"
            and re.fullmatch(
                rf"\s*i prefer\s+({browsers})\s*",
                memory.content,
                flags=re.IGNORECASE,
            )
            is not None
        )

    @classmethod
    def _rank_query_memories(cls, query: str, memories: List[Any], specific_ids: set) -> List[Any]:
        """
        Rank query candidates with bounded, explainable signals.

        Literal command matches always dominate preference fallbacks. Token overlap
        and browser-preference cues provide relevance, while confidence and
        recency only make small, predictable adjustments.
        """
        query_tokens = cls._tokens(query)
        preference_query = bool(
            query_tokens & {"prefer", "preference", "preferences", "browser"}
        )
        newest = max((memory.timestamp for memory in memories), default=None)

        def score(memory: Any) -> float:
            specific_match = 100.0 if memory.id in specific_ids else 0.0
            overlap = (
                10.0 * len(query_tokens & cls._tokens(memory.content)) / len(query_tokens)
                if query_tokens
                else 0.0
            )
            browser_context = (
                5.0
                if preference_query and cls._is_browser_preference(memory)
                else 0.0
            )
            confidence = 0.0
            recency = 0.0
            if memory.id not in specific_ids:
                confidence = max(0.0, min(1.0, memory.confidence))
                if newest is not None:
                    age_seconds = max(0.0, (newest - memory.timestamp).total_seconds())
                    recency = 1.0 / (1.0 + age_seconds / 86400.0)
            return specific_match + overlap + browser_context + confidence + recency

        return sorted(memories, key=score, reverse=True)

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
        specific_ids = set()
        if query:
            command_matches = self.memory_manager.search_memories(query)
            specific_ids = {memory.id for memory in command_matches}
            preference_memories = self.memory_manager.get_memories_by_category(
                "user_preference"
            )
            selected_memories = command_matches + preference_memories
        elif categories:
            for category in categories:
                selected_memories.extend(self.memory_manager.get_memories_by_category(category))
        else:
            selected_memories = self.memory_manager.get_all_memories()

        deduped: List[Any] = []
        seen_ids = set()
        seen_content = set()
        for memory in selected_memories:
            content_key = (memory.category, memory.content)
            if memory.id in seen_ids or content_key in seen_content:
                continue
            seen_ids.add(memory.id)
            seen_content.add(content_key)
            deduped.append(memory)

        if query:
            deduped = self._rank_query_memories(query, deduped, specific_ids)

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
