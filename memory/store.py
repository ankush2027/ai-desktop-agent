import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from memory.models import Memory
from memory.errors import MemoryStorageError


class MemoryStore:
    """SQLite store. Callers own the connection and close it explicitly."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else Path(__file__).resolve().parent.parent / "memory.db"
        self._connection = None
        self._depth = 0
        try:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            with self.transaction():
                self._execute("""CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, content TEXT NOT NULL, category TEXT NOT NULL,
                    confidence REAL NOT NULL, timestamp TEXT NOT NULL)""")
        except (sqlite3.Error, OSError, MemoryStorageError):
            self.close()
            raise MemoryStorageError("Memory storage is unavailable.") from None

    def _execute(self, sql, params=(), *, rows=False):
        try:
            with closing(self._connection.execute(sql, params)) as cursor:
                return cursor.fetchall() if rows else cursor.rowcount
        except sqlite3.Error:
            raise MemoryStorageError("Memory storage operation failed.") from None

    @contextmanager
    def transaction(self):
        """Atomic writes, including nested manager/store operations."""
        depth = self._depth
        savepoint = f"memory_write_{depth}"
        self._execute("BEGIN IMMEDIATE" if depth == 0 else f"SAVEPOINT {savepoint}")
        self._depth += 1
        try:
            yield
            self._execute("COMMIT" if depth == 0 else f"RELEASE SAVEPOINT {savepoint}")
        except BaseException:
            try:
                self._execute("ROLLBACK" if depth == 0 else f"ROLLBACK TO SAVEPOINT {savepoint}")
                if depth:
                    self._execute(f"RELEASE SAVEPOINT {savepoint}")
            except MemoryStorageError:
                pass  # Preserve the original failure, never report a successful write.
            raise
        finally:
            self._depth -= 1

    @staticmethod
    def _row_to_memory(row):
        try:
            data = dict(row)
            if any(not isinstance(data[key], str) for key in ("id", "content", "category", "timestamp")):
                raise ValueError("Invalid stored field type")
            return Memory.from_dict(data)
        except (ValueError, TypeError, KeyError):
            raise MemoryStorageError("Stored memory data is invalid.") from None

    def add(self, memory):
        with self.transaction():
            self._execute("INSERT INTO memories (id, content, category, confidence, timestamp) VALUES (?, ?, ?, ?, ?)",
                          (memory.id, memory.content, memory.category, memory.confidence, memory.timestamp.isoformat()))
        return memory.id

    def get_by_id(self, memory_id):
        rows = self._execute("SELECT * FROM memories WHERE id = ?", (memory_id,), rows=True)
        return self._row_to_memory(rows[0]) if rows else None

    def get_all(self):
        return [self._row_to_memory(row) for row in self._execute("SELECT * FROM memories ORDER BY timestamp", rows=True)]

    def get_by_category(self, category):
        return [self._row_to_memory(row) for row in self._execute(
            "SELECT * FROM memories WHERE category = ? ORDER BY timestamp", (category,), rows=True)]

    def update(self, memory_id, **kwargs):
        with self.transaction():
            memory = self.get_by_id(memory_id)
            if memory is None:
                return None
            for key in ("content", "category", "timestamp"):
                if key in kwargs:
                    setattr(memory, key, kwargs[key])
            if "confidence" in kwargs:
                memory.confidence = max(0.0, min(1.0, kwargs["confidence"]))
            self._execute("UPDATE memories SET content = ?, category = ?, confidence = ?, timestamp = ? WHERE id = ?",
                          (memory.content, memory.category, memory.confidence, memory.timestamp.isoformat(), memory_id))
        return memory

    def delete(self, memory_id):
        with self.transaction():
            return self._execute("DELETE FROM memories WHERE id = ?", (memory_id,)) > 0

    def count(self):
        return int(self._execute("SELECT COUNT(*) AS total FROM memories", rows=True)[0]["total"])

    def clear(self):
        with self.transaction():
            self._execute("DELETE FROM memories")

    def close(self):
        if self._connection is not None:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
