from typing import List, Optional, Dict
from memory.models import Memory


class MemoryStore:
    """
    In-memory storage for memories.
    
    This is the data persistence layer (currently in-memory).
    Future implementations will replace this with database persistence.
    """
    
    def __init__(self):
        """Initialize the in-memory memory store."""
        self._memories: Dict[str, Memory] = {}
    
    def add(self, memory: Memory) -> str:
        """
        Add a memory to the store.
        
        Args:
            memory: The Memory object to add
            
        Returns:
            The unique ID of the added memory
        """
        self._memories[memory.id] = memory
        return memory.id
    
    def get_by_id(self, memory_id: str) -> Optional[Memory]:
        """
        Retrieve a memory by its ID.
        
        Args:
            memory_id: The unique identifier of the memory
            
        Returns:
            The Memory object if found, None otherwise
        """
        return self._memories.get(memory_id)
    
    def get_all(self) -> List[Memory]:
        """
        Retrieve all memories.
        
        Returns:
            A list of all Memory objects
        """
        return list(self._memories.values())
    
    def get_by_category(self, category: str) -> List[Memory]:
        """
        Retrieve all memories of a specific category.
        
        Args:
            category: The category to filter by
            
        Returns:
            A list of Memory objects matching the category
        """
        return [m for m in self._memories.values() if m.category == category]
    
    def update(self, memory_id: str, **kwargs) -> Optional[Memory]:
        """
        Update a memory with the given attributes.
        
        Args:
            memory_id: The unique identifier of the memory to update
            **kwargs: Attributes to update (content, category, confidence)
            
        Returns:
            The updated Memory object if found, None otherwise
        """
        memory = self._memories.get(memory_id)
        if memory is None:
            return None
        
        if 'content' in kwargs:
            memory.content = kwargs['content']
        if 'category' in kwargs:
            memory.category = kwargs['category']
        if 'confidence' in kwargs:
            memory.confidence = max(0.0, min(1.0, kwargs['confidence']))
        
        return memory
    
    def delete(self, memory_id: str) -> bool:
        """
        Delete a memory by its ID.
        
        Args:
            memory_id: The unique identifier of the memory to delete
            
        Returns:
            True if the memory was deleted, False if it wasn't found
        """
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False
    
    def count(self) -> int:
        """
        Get the total number of memories in the store.
        
        Returns:
            The count of memories
        """
        return len(self._memories)
    
    def clear(self) -> None:
        """Clear all memories from the store."""
        self._memories.clear()
