import re
import json
from memory.episodes import (ContextEpisode, ContextTask, ContextNote,
                             ContextStateError, require_text, new_id, now)
from typing import List, Optional
from datetime import datetime
from config import BROWSERS
from memory.models import Memory
from memory.store import MemoryStore


class MemoryManager:
    """
    Single gateway for all memory operations.
    
    The Memory Manager is responsible for:
    - Adding memories
    - Retrieving memories
    - Updating memories
    - Deleting memories
    
    It communicates with the Memory Store for persistence in SQLite.
    Other modules must not directly manipulate memories; they must use this manager.
    """
    
    def __init__(self, store: Optional[MemoryStore] = None):
        """
        Initialize the Memory Manager.
        
        Args:
            store: The MemoryStore instance to use. Creates a new one if not provided.
        """
        self._owns_store = store is None
        self.store = store if store is not None else MemoryStore()

    def close(self):
        if self._owns_store:
            self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
    
    def add_memory(
        self,
        content: str,
        category: str,
        confidence: float = 1.0,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """
        Add a new memory.
        
        Args:
            content: The memory content/text
            category: The category or type of memory
            confidence: Confidence level (0.0 to 1.0)
            timestamp: When the memory was created (defaults to now)
            
        Returns:
            The unique ID of the added memory
        """
        with self.store.transaction():
            return self._add_memory(content, category, confidence, timestamp)

    def _add_memory(self, content, category, confidence, timestamp):
        existing_memories = self.search_memories(content, category=category)
        for existing in existing_memories:
            if existing.content == content:
                return existing.id

        browser = self._browser_preference(content, category)
        if browser:
            browser_memories = [
                memory
                for memory in self.get_memories_by_category("user_preference")
                if self._browser_preference(memory.content, memory.category)
            ]
            if browser_memories:
                current = browser_memories[0]
                self.update_memory(
                    current.id,
                    content=content,
                    confidence=confidence,
                    timestamp=timestamp or datetime.now(),
                )
                for stale in browser_memories[1:]:
                    self.delete_memory(stale.id)
                return current.id

        memory = Memory(
            content=content,
            category=category,
            confidence=confidence,
            timestamp=timestamp,
        )
        return self.store.add(memory)

    @staticmethod
    def _browser_preference(content: str, category: str) -> Optional[str]:
        """Return the normalized browser value for a supported preference."""
        if category != "user_preference":
            return None

        browsers = "|".join(re.escape(browser) for browser in BROWSERS["available"])
        match = re.fullmatch(rf"\s*I prefer\s+({browsers})\s*", content, re.IGNORECASE)
        return match.group(1).lower() if match else None
    
    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """
        Retrieve a specific memory by its ID.
        
        Args:
            memory_id: The unique identifier of the memory
            
        Returns:
            The Memory object if found, None otherwise
        """
        return self.store.get_by_id(memory_id)
    
    def get_all_memories(self) -> List[Memory]:
        """
        Retrieve all memories.
        
        Returns:
            A list of all Memory objects
        """
        return self.store.get_all()
    
    def get_memories_by_category(self, category: str) -> List[Memory]:
        """
        Retrieve all memories of a specific category.
        
        Args:
            category: The category to filter by
            
        Returns:
            A list of Memory objects matching the category
        """
        return self.store.get_by_category(category)
    
    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        category: Optional[str] = None,
        confidence: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Memory]:
        """
        Update a memory with new values.
        
        Args:
            memory_id: The unique identifier of the memory to update
            content: New content (optional)
            category: New category (optional)
            confidence: New confidence level (optional)
            
        Returns:
            The updated Memory object if found, None otherwise
        """
        update_data = {}
        if content is not None:
            update_data['content'] = content
        if category is not None:
            update_data['category'] = category
        if confidence is not None:
            update_data['confidence'] = confidence
        if timestamp is not None:
            update_data['timestamp'] = timestamp
        
        if not update_data:
            return self.get_memory(memory_id)
        
        return self.store.update(memory_id, **update_data)
    
    def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory by its ID.
        
        Args:
            memory_id: The unique identifier of the memory to delete
            
        Returns:
            True if the memory was deleted, False if it wasn't found
        """
        return self.store.delete(memory_id)
    
    def get_memory_count(self) -> int:
        """
        Get the total number of memories.
        
        Returns:
            The count of memories
        """
        return self.store.count()
    
    def clear_all_memories(self) -> None:
        """Clear all memories from the store."""
        self.store.clear()
    
    def search_memories(self, query: str, category: Optional[str] = None) -> List[Memory]:
        """
        Search for memories by content (case-insensitive).
        
        Args:
            query: The search query string
            category: Optional category filter
            
        Returns:
            A list of Memory objects matching the search criteria
        """
        query_lower = query.lower()
        results = []
        
        for memory in self.store.get_all():
            if query_lower in memory.content.lower():
                if category is None or memory.category == category:
                    results.append(memory)
        
        return results

    def context_transaction(self):
        """Keep a context event atomic without exposing SQLite to ContextEngine."""
        return self.store.transaction()

    def get_active_episode(self):
        return self.store.get_active_episode()

    def get_episode(self, episode_id):
        return self.store.get_episode(episode_id)

    def get_latest_episode(self, name=None):
        return self.store.get_latest_episode(name)

    def start_episode(self, name=None):
        """Arrival is idempotent; an explicit name refines the active episode."""
        if name is not None:
            name = require_text(name)
        with self.context_transaction():
            episode = self.get_active_episode()
            if episode is None:
                episode = ContextEpisode(new_id(), name or "current_place", now())
            elif name is not None:
                episode.name = name
            return self.store.save_episode(episode)

    def _require_active_episode(self):
        episode = self.get_active_episode()
        if episode is None:
            raise ContextStateError("No active context. Establish a context first.")
        return episode

    def update_episode(self, *, name=None, memory_ids=None, metadata=None):
        """Update only explicitly supplied context; metadata is a JSON object."""
        with self.context_transaction():
            episode = self._require_active_episode()
            if name is not None:
                episode.name = require_text(name)
            if memory_ids is not None:
                if (not isinstance(memory_ids, list)
                        or any(not isinstance(item, str) or self.get_memory(item) is None
                               for item in memory_ids)):
                    raise ContextStateError("Context memory references must identify existing memories.")
                episode.memory_ids = list(dict.fromkeys(memory_ids))
            if metadata is not None:
                if not isinstance(metadata, dict):
                    raise ContextStateError("Context metadata must be a JSON object.")
                try:
                    episode.metadata = json.loads(json.dumps(metadata, allow_nan=False))
                except (ValueError, TypeError, RecursionError):
                    raise ContextStateError("Context metadata must be a JSON object.") from None
            return self.store.save_episode(episode)

    def close_episode(self):
        with self.context_transaction():
            episode = self.get_active_episode()
            if episode is None:
                return None
            episode.status = "closed"
            episode.ended_at = now()
            return self.store.save_episode(episode)

    def add_context_task(self, description, *, kind="task", trigger="context_exit"):
        description = require_text(description)
        if kind not in {"task", "intention"} or trigger not in {"context_exit", "none"}:
            raise ContextStateError("Unsupported contextual task kind or trigger.")
        with self.context_transaction():
            episode = self._require_active_episode()
            for task in self.get_context_tasks(episode.id, pending_only=True):
                if (task.description, task.kind, task.trigger) == (description, kind, trigger):
                    return task
            return self.store.add_context_task(ContextTask(
                new_id(), episode.id, description, now(), kind=kind, trigger=trigger))

    def get_context_tasks(self, episode_id, *, pending_only=False):
        return self.store.get_context_tasks(episode_id, pending_only)

    def complete_context_task(self, task_id):
        # Completing historical tasks is allowed, but never reopens an episode.
        task = self.store.complete_context_task(require_text(task_id), now())
        if task is None:
            raise ContextStateError("Contextual task not found.")
        return task

    def add_context_note(self, content, *, category="contextual"):
        content = require_text(content)
        if category not in {"contextual", "temporary"}:
            raise ContextStateError("Unsupported context note category.")
        with self.context_transaction():
            episode = self._require_active_episode()
            return self.store.add_context_note(ContextNote(
                new_id(), episode.id, content, category, now()))

    def get_context_notes(self, episode_id):
        return self.store.get_context_notes(episode_id)

    def get_episodes(self, name=None):
        """Candidate episodes for deterministic continuity selection."""
        return self.store.get_episodes(name)

    def save_workspace(self, name, definition):
        self.store.save_workspace(name, definition)

    def load_workspace(self, name):
        return self.store.load_workspace(name)
