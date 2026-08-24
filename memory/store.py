import sqlite3
from pathlib import Path
from typing import List, Optional

from memory.models import Memory


class MemoryStore:
    """
    SQLite-backed storage for memories.

    This keeps the storage responsibility isolated inside the storage layer,
    while MemoryManager remains the single gateway for memory operations.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the SQLite-backed memory store."""
        project_root = Path(__file__).resolve().parent.parent
        self.db_path = Path(db_path) if db_path else project_root / "memory.db"
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Create the memories table if it does not already exist."""
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT NOT NULL,
                confidence REAL NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        """Convert a sqlite row to a Memory object."""
        return Memory.from_dict({
            "id": row["id"],
            "content": row["content"],
            "category": row["category"],
            "confidence": row["confidence"],
            "timestamp": row["timestamp"],
        })

    def add(self, memory: Memory) -> str:
        """
        Add a memory to the store.

        Args:
            memory: The Memory object to add

        Returns:
            The unique ID of the added memory
        """
        self._connection.execute(
            """
            INSERT INTO memories (id, content, category, confidence, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.content,
                memory.category,
                memory.confidence,
                memory.timestamp.isoformat(),
            ),
        )
        self._connection.commit()
        return memory.id

    def get_by_id(self, memory_id: str) -> Optional[Memory]:
        """
        Retrieve a memory by its ID.

        Args:
            memory_id: The unique identifier of the memory

        Returns:
            The Memory object if found, None otherwise
        """
        row = self._connection.execute(
            "SELECT id, content, category, confidence, timestamp FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()

        if row is None:
            return None
        return self._row_to_memory(row)

    def get_all(self) -> List[Memory]:
        """
        Retrieve all memories.

        Returns:
            A list of all Memory objects
        """
        rows = self._connection.execute(
            "SELECT id, content, category, confidence, timestamp FROM memories ORDER BY timestamp"
        ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def get_by_category(self, category: str) -> List[Memory]:
        """
        Retrieve all memories of a specific category.

        Args:
            category: The category to filter by

        Returns:
            A list of Memory objects matching the category
        """
        rows = self._connection.execute(
            "SELECT id, content, category, confidence, timestamp FROM memories WHERE category = ? ORDER BY timestamp",
            (category,),
        ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def update(self, memory_id: str, **kwargs) -> Optional[Memory]:
        """
        Update a memory with the given attributes.

        Args:
            memory_id: The unique identifier of the memory to update
            **kwargs: Attributes to update (content, category, confidence)

        Returns:
            The updated Memory object if found, None otherwise
        """
        existing = self.get_by_id(memory_id)
        if existing is None:
            return None

        if 'content' in kwargs:
            existing.content = kwargs['content']
        if 'category' in kwargs:
            existing.category = kwargs['category']
        if 'confidence' in kwargs:
            existing.confidence = max(0.0, min(1.0, kwargs['confidence']))

        self._connection.execute(
            """
            UPDATE memories
            SET content = ?, category = ?, confidence = ?, timestamp = ?
            WHERE id = ?
            """,
            (
                existing.content,
                existing.category,
                existing.confidence,
                existing.timestamp.isoformat(),
                memory_id,
            ),
        )
        self._connection.commit()
        return existing

    def delete(self, memory_id: str) -> bool:
        """
        Delete a memory by its ID.

        Args:
            memory_id: The unique identifier of the memory to delete

        Returns:
            True if the memory was deleted, False if it wasn't found
        """
        cursor = self._connection.execute(
            "DELETE FROM memories WHERE id = ?",
            (memory_id,),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """
        Get the total number of memories in the store.

        Returns:
            The count of memories
        """
        row = self._connection.execute("SELECT COUNT(*) as total FROM memories").fetchone()
        return int(row["total"])

    def clear(self) -> None:
        """Clear all memories from the store."""
        self._connection.execute("DELETE FROM memories")
        self._connection.commit()

    def close(self) -> None:
        """Close the SQLite database connection."""
        self._connection.close()
