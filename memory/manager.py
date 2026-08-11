from typing import List, Optional
from datetime import datetime
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
    
    It communicates with the Memory Store for persistence (currently in-memory).
    Other modules must not directly manipulate memories; they must use this manager.
    """
    
    def __init__(self, store: Optional[MemoryStore] = None):
        """
        Initialize the Memory Manager.
        
        Args:
            store: The MemoryStore instance to use. Creates a new one if not provided.
        """
        self.store = store or MemoryStore()
    
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
        memory = Memory(
            content=content,
            category=category,
            confidence=confidence,
            timestamp=timestamp,
        )
        return self.store.add(memory)
    
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
