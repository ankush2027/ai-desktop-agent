import re
from dataclasses import asdict
from context.events import ContextEvent, ContextEventType, ContextResult
from context.rules import context_exit_reminders
from context.continuity import from_snapshot, NO_CONTINUITY
from memory.episodes import ContextStateError
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
        return MemoryManager._browser_preference(memory.content, memory.category) is not None

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

        # Resolve preferences before truncation so execution is independent of
        # the query's memory ranking and prompt size limit.
        browsers = dict(BROWSERS)
        for memory in sorted(selected_memories, key=lambda item: item.timestamp, reverse=True):
            browser = self.memory_manager._browser_preference(memory.content, memory.category)
            if browser:
                browsers["preferred"] = browser
                break
        system_context["browsers"] = browsers

        return StructuredContext(
            timestamp=runtime["current_datetime"],
            runtime=runtime,
            user_context=user_context,
            system_context=system_context,
            relevant_memories=relevant_memories,
            summary=summary,
        )

    def handle_event(self, event):
        """Shared context entry point for text and future voice/UI adapters.

        Persist the whole event before returning a response. Context responses
        never enter desktop dispatch or grant additional AI action capabilities.
        """
        if not isinstance(event, ContextEvent) or not isinstance(event.kind, ContextEventType):
            raise ContextStateError("Unsupported context event.")
        if event.kind == ContextEventType.CONTINUE:
            if event.view not in {"overview", "pending", "completed"}:
                raise ContextStateError("Unsupported continuity view.")
            state = self.get_continuity(event.name)
            return ContextResult(state.summary(event.view) if state else NO_CONTINUITY,
                                 continuity=state)
        manager = self.memory_manager
        with manager.context_transaction():
            if event.kind == ContextEventType.ARRIVE:
                episode = manager.start_episode(event.name)
                return ContextResult(f"Current context: {episode.name}.", episode)
            if event.kind == ContextEventType.INSPECT:
                episode = manager.get_active_episode()
                message = f"Current context: {episode.name}." if episode else "No active context."
                return ContextResult(message, episode)
            if event.kind in {ContextEventType.ADD_TASK, ContextEventType.RECORD_TASK, ContextEventType.WORK_ON}:
                task = manager.add_context_task(
                    event.description,
                    kind="intention" if event.kind == ContextEventType.WORK_ON else "task",
                    trigger="context_exit" if event.kind == ContextEventType.ADD_TASK else "none",
                )
                return ContextResult(
                    f"Contextual task saved: {task.description}. Task ID: {task.id}",
                    manager.get_active_episode(), task,
                )
            if event.kind == ContextEventType.COMPLETE_TASK:
                task = manager.complete_context_task(event.task_id)
                return ContextResult("Contextual task completed.", manager.get_episode(task.episode_id), task)
            episode = manager.get_active_episode()
            if episode is None:
                return ContextResult("No active context to close.")
            reminders = context_exit_reminders(
                event, episode.id, manager.get_context_tasks(episode.id, pending_only=True))
            closed = manager.close_episode()
            message = "Context closed."
            if reminders:
                message = "Before you leave, still pending: " + "; ".join(
                    task.description for task in reminders) + ". Context closed."
            return ContextResult(message, closed, reminders=reminders)

    def continuity_snapshot(self, name=None):
        """Explicit retrieval only: no LLM summary, action replay, or reopening.

        Historical notes are retained for continuity, not promoted into permanent
        preferences or injected into unrelated AI prompts. Deleted memory refs
        are omitted from the resolved memories.
        """
        manager = self.memory_manager
        with manager.context_transaction():
            episode = manager.get_latest_episode(name)
            if episode is None:
                return None
            return self._episode_snapshot(episode)

    def _episode_snapshot(self, episode):
        manager = self.memory_manager
        tasks = manager.get_context_tasks(episode.id)
        return {
            "episode": episode.to_dict(),
            "tasks": [asdict(task) for task in tasks],
            "unfinished_tasks": [asdict(task) for task in tasks if task.status == "pending"],
            "notes": [asdict(note) for note in manager.get_context_notes(episode.id)],
            "relevant_memories": [memory.to_dict() for memory_id in episode.memory_ids
                                  if (memory := manager.get_memory(memory_id)) is not None],
        }

    def get_continuity(self, name=None):
        """Select one useful episode; return structured state without side effects.

        Rank unfinished work first, active unfinished work next, then completed
        work, recorded activity time and episode start/ID for stable tie breaking.
        Empty arrivals and dangling memory references are not useful continuity.
        """
        manager = self.memory_manager
        with manager.context_transaction():
            states = [state for episode in manager.get_episodes(name)
                      if (state := from_snapshot(self._episode_snapshot(episode))) is not None]
            return max(states, key=lambda state: state.selection_key(), default=None)
