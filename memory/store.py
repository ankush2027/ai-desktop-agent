import sqlite3
import json
from datetime import datetime

from memory.episodes import ContextEpisode, ContextTask, ContextNote
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
            self._execute("PRAGMA foreign_keys = ON")
            with self.transaction():
                self._execute("""CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, content TEXT NOT NULL, category TEXT NOT NULL,
                    confidence REAL NOT NULL, timestamp TEXT NOT NULL)""")
                self._initialize_context_schema()
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

    def _initialize_context_schema(self):
        # Additive and transactional: existing memories are neither rewritten nor
        # reclassified. Reopening an old or new database is safe and idempotent.
        self._execute("""CREATE TABLE IF NOT EXISTS context_episodes (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, started_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active', 'closed')),
            ended_at TEXT, memory_ids TEXT NOT NULL, metadata TEXT NOT NULL,
            CHECK((status = 'active' AND ended_at IS NULL) OR
                  (status = 'closed' AND ended_at IS NOT NULL)))""")
        self._execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_active_context
            ON context_episodes(status) WHERE status = 'active'""")
        self._execute("""CREATE TABLE IF NOT EXISTS context_tasks (
            id TEXT PRIMARY KEY, episode_id TEXT NOT NULL REFERENCES context_episodes(id),
            description TEXT NOT NULL, created_at TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('task', 'intention')),
            trigger TEXT NOT NULL CHECK(trigger IN ('context_exit', 'none')),
            status TEXT NOT NULL CHECK(status IN ('pending', 'completed')),
            completed_at TEXT,
            CHECK((status = 'pending' AND completed_at IS NULL) OR
                  (status = 'completed' AND completed_at IS NOT NULL)))""")
        self._execute("""CREATE INDEX IF NOT EXISTS context_tasks_episode
            ON context_tasks(episode_id, status)""")
        self._execute("""CREATE TABLE IF NOT EXISTS context_notes (
            id TEXT PRIMARY KEY, episode_id TEXT NOT NULL REFERENCES context_episodes(id),
            content TEXT NOT NULL, category TEXT NOT NULL
                CHECK(category IN ('contextual', 'temporary')), created_at TEXT NOT NULL)""")

    @staticmethod
    def _context_row(row, model):
        try:
            data = dict(row)
            for key, value in data.items():
                if key not in {"ended_at", "completed_at"} and not isinstance(value, str):
                    raise ValueError
            for key in ("started_at", "ended_at", "created_at", "completed_at"):
                if key in data and data[key] is not None:
                    datetime.fromisoformat(data[key])
            if model is ContextEpisode:
                data['memory_ids'] = json.loads(data['memory_ids'])
                data['metadata'] = json.loads(data['metadata'])
                if (not isinstance(data['metadata'], dict)
                        or not isinstance(data['memory_ids'], list)
                        or any(not isinstance(item, str) for item in data['memory_ids'])):
                    raise ValueError
            return model(**data)
        except (ValueError, TypeError, KeyError):
            raise MemoryStorageError("Stored context data is invalid.") from None

    def get_episode(self, episode_id):
        rows = self._execute("SELECT * FROM context_episodes WHERE id = ?", (episode_id,), rows=True)
        return self._context_row(rows[0], ContextEpisode) if rows else None

    def get_active_episode(self):
        rows = self._execute("SELECT * FROM context_episodes WHERE status = 'active'", rows=True)
        return self._context_row(rows[0], ContextEpisode) if rows else None

    def get_latest_episode(self, name=None):
        sql = "SELECT * FROM context_episodes"
        params = ()
        if name is not None:
            sql += " WHERE name = ?"
            params = (name,)
        rows = self._execute(sql + " ORDER BY started_at DESC, rowid DESC LIMIT 1", params, rows=True)
        return self._context_row(rows[0], ContextEpisode) if rows else None

    def save_episode(self, episode):
        with self.transaction():
            self._execute("""INSERT INTO context_episodes
                (id, name, started_at, status, ended_at, memory_ids, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                status=excluded.status, ended_at=excluded.ended_at,
                memory_ids=excluded.memory_ids, metadata=excluded.metadata""",
                (episode.id, episode.name, episode.started_at, episode.status, episode.ended_at,
                 json.dumps(episode.memory_ids), json.dumps(episode.metadata, allow_nan=False)))
        return episode

    def add_context_task(self, task):
        with self.transaction():
            self._execute("""INSERT INTO context_tasks
                (id, episode_id, description, created_at, kind, trigger, status, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (task.id, task.episode_id, task.description, task.created_at,
                 task.kind, task.trigger, task.status, task.completed_at))
        return task

    def get_context_tasks(self, episode_id, pending_only=False):
        sql = "SELECT * FROM context_tasks WHERE episode_id = ?"
        if pending_only:
            sql += " AND status = 'pending'"
        return [self._context_row(row, ContextTask) for row in self._execute(
            sql + " ORDER BY created_at, rowid", (episode_id,), rows=True)]

    def complete_context_task(self, task_id, completed_at):
        with self.transaction():
            self._execute("""UPDATE context_tasks SET status = 'completed', completed_at = ?
                WHERE id = ? AND status = 'pending'""", (completed_at, task_id))
            rows = self._execute("SELECT * FROM context_tasks WHERE id = ?", (task_id,), rows=True)
        return self._context_row(rows[0], ContextTask) if rows else None

    def add_context_note(self, note):
        with self.transaction():
            self._execute("""INSERT INTO context_notes
                (id, episode_id, content, category, created_at) VALUES (?, ?, ?, ?, ?)""",
                (note.id, note.episode_id, note.content, note.category, note.created_at))
        return note

    def get_context_notes(self, episode_id):
        return [self._context_row(row, ContextNote) for row in self._execute(
            "SELECT * FROM context_notes WHERE episode_id = ? ORDER BY created_at, rowid",
            (episode_id,), rows=True)]

    def get_episodes(self, name=None):
        sql = "SELECT * FROM context_episodes"
        params = ()
        if name is not None:
            sql += " WHERE name = ?"
            params = (name,)
        return [self._context_row(row, ContextEpisode) for row in self._execute(
            sql + " ORDER BY started_at DESC, rowid DESC", params, rows=True)]
