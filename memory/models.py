import uuid
from datetime import datetime
from typing import Optional


class Memory:
    """Represents a single memory item with a clear structure."""
    
    def __init__(
        self,
        content: str,
        category: str,
        confidence: float = 1.0,
        timestamp: Optional[datetime] = None,
        memory_id: Optional[str] = None,
    ):
        """
        Initialize a Memory object.
        
        Args:
            content: The actual memory content/text
            category: The category or type of memory (e.g., 'user_preference', 'system_config', 'interaction')
            confidence: Confidence level of the memory (0.0 to 1.0), default is 1.0
            timestamp: When the memory was created, defaults to current time
            memory_id: Unique identifier, defaults to UUID if not provided
        """
        self.id = memory_id or str(uuid.uuid4())
        self.content = content
        self.category = category
        self.confidence = max(0.0, min(1.0, confidence))
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self) -> dict:
        """Convert memory to dictionary representation."""
        return {
            'id': self.id,
            'content': self.content,
            'category': self.category,
            'confidence': self.confidence,
            'timestamp': self.timestamp.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Memory':
        """Create a Memory object from a dictionary."""
        return cls(
            content=data['content'],
            category=data['category'],
            confidence=data.get('confidence', 1.0),
            timestamp=datetime.fromisoformat(data['timestamp']) if isinstance(data['timestamp'], str) else data.get('timestamp'),
            memory_id=data.get('id'),
        )
    
    def __repr__(self) -> str:
        return f"Memory(id={self.id}, category={self.category}, content={self.content[:50]}...)"
