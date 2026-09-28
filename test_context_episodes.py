"""Context episode behavior, migrations and privacy in isolated SQLite stores."""

if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

import pytest
import main
import logger
from context import ContextEngine
from context.events import ContextEvent, ContextEventType, parse_context_event
from context.rules import context_exit_reminders
from memory import MemoryManager, MemoryStore
from memory.episodes import ContextStateError
from memory.errors import MemoryStorageError


@pytest.fixture
def core():
    with MemoryManager() as manager:
        yield ContextEngine(manager)


def arrive(core, name=None):
    return core.handle_event(ContextEvent(ContextEventType.ARRIVE, name=name)).episode


def leave(core):
    return core.handle_event(ContextEvent(ContextEventType.LEAVE))


@pytest.mark.parametrize("command,name", [
    ("I'm here.", "current_place"), ("I am here", "current_place"),
    ("I've arrived.", "current_place"), ("I have arrived now!", "current_place"),
    ("I’m at college.", "college"), ("I'm at My AI Project", "My AI Project"),
])
def test_arrival_variations_create_structured_context(core, command, name):
    result = core.handle_event(parse_context_event(command))
    episode = core.memory_manager.get_active_episode()
    assert episode.id == result.episode.id
    assert episode.name == name and episode.status == "active"
    assert episode.started_at and episode.ended_at is None
    assert episode.metadata == {}  # No inferred location or coordinates.
    assert core.memory_manager.get_all_memories() == []


@pytest.mark.parametrize("command", ["I'm leaving.", "I'm leaving now.", "I'm heading out.", "I am heading out now!"])
def test_leave_variations_close_context(core, command):
    episode = arrive(core)
    result = core.handle_event(parse_context_event(command))
    assert result.episode.id == episode.id
    assert result.episode.status == "closed" and result.episode.ended_at
    assert core.memory_manager.get_active_episode() is None


def test_repeated_arrival_refines_same_episode_and_preserves_tasks(core):
    first = arrive(core)
    task = core.memory_manager.add_context_task("submit assignment")
    refined = arrive(core, "college")
    assert (refined.id, refined.started_at) == (first.id, first.started_at)
    assert arrive(core).name == "college"
    assert core.memory_manager.get_context_tasks(first.id) == [task]


@pytest.mark.parametrize("command", [
    "Remember that I need to submit my assignment before I leave.",
    "Remind me to submit my assignment before I leave.",
    "I need to submit my assignment before I leave.",
    "Remember I have to submit my assignment before I leave!",
])
def test_task_variations_belong_to_episode_not_permanent_memory(core, command):
    episode = arrive(core)
    result = core.handle_event(parse_context_event(command))
    assert result.task.description == "submit my assignment"
    assert result.task.episode_id == episode.id
    assert result.task.trigger == "context_exit" and result.task.status == "pending"
    assert result.task.completed_at is None
    assert core.memory_manager.get_context_tasks(episode.id) == [result.task]
    assert core.memory_manager.get_memory_count() == 0


def test_multiple_pending_tasks_and_completed_tasks_on_exit(core):
    episode = arrive(core)
    manager = core.memory_manager
    done = manager.add_context_task("finish project")
    pending = manager.add_context_task("submit assignment")
    intention = manager.add_context_task("prepare for interview", kind="intention")
    manager.add_context_task("later task", trigger="none")
    completed = manager.complete_context_task(done.id)
    assert completed.status == "completed" and completed.completed_at
    assert manager.complete_context_task(done.id).completed_at == completed.completed_at
    result = leave(core)
    assert result.reminders == [pending, intention]
    assert "submit assignment" in result.message and "prepare for interview" in result.message
    assert "finish project" not in result.message and "later task" not in result.message
    assert manager.get_episode(episode.id).status == "closed"
    assert leave(core).reminders == []


def test_no_active_context_does_not_create_orphan_tasks(core):
    assert leave(core).episode is None
    assert core.handle_event(ContextEvent(ContextEventType.INSPECT)).episode is None
    assert core.continuity_snapshot() is None
    with pytest.raises(ContextStateError, match="No active context"):
        core.memory_manager.add_context_task("assignment")
    with pytest.raises(ContextStateError, match="No active context"):
        core.memory_manager.add_context_note("temporary info", category="temporary")
    with pytest.raises(ContextStateError, match="No active context"):
        core.memory_manager.update_episode(name="college")
    assert core.memory_manager.get_latest_episode() is None


def test_closed_context_retains_continuity_without_replaying_tasks(core):
    first = arrive(core, "college")
    manager = core.memory_manager
    old_task = manager.add_context_task("old unfinished task")
    leave(core)
    with pytest.raises(ContextStateError):
        manager.add_context_task("cannot attach to closed episode")
    second = arrive(core, "home")
    assert second.id != first.id
    assert manager.get_latest_episode().id == second.id
    assert core.continuity_snapshot("college")["unfinished_tasks"] == [asdict(old_task)]
    assert leave(core).reminders == []
    # Historical completion is possible, without resurrecting the episode.
    manager.complete_context_task(old_task.id)
    assert core.continuity_snapshot("college")["unfinished_tasks"] == []
    assert manager.get_active_episode() is None


def test_context_notes_references_and_metadata_survive_reopening(core):
    manager = core.memory_manager
    permanent_id = manager.add_memory("I prefer Python", "user_preference")
    episode = arrive(core, "college")
    metadata = {"project": "AI project", "progress": ["Gmail workflow completed"]}
    manager.update_episode(memory_ids=[permanent_id, permanent_id], metadata=metadata)
    metadata["progress"].clear()
    manager.add_context_note("working on AI project", category="contextual")
    manager.add_context_note("submission link in notebook", category="temporary")
    manager.add_context_task("finish reliability tests", kind="intention")
    path = manager.store.db_path
    leave(core)
    with MemoryStore(path) as store:
        snapshot = ContextEngine(MemoryManager(store)).continuity_snapshot()
    assert snapshot["episode"]["id"] == episode.id
    assert snapshot["episode"]["memory_ids"] == [permanent_id]
    assert snapshot["episode"]["metadata"]["progress"] == ["Gmail workflow completed"]
    assert {note["category"] for note in snapshot["notes"]} == {"contextual", "temporary"}
    assert snapshot["unfinished_tasks"][0]["kind"] == "intention"
    assert snapshot["relevant_memories"][0]["id"] == permanent_id
    assert manager.get_memory_count() == 1
    json.dumps(snapshot)
    manager.delete_memory(permanent_id)
    assert core.continuity_snapshot()["relevant_memories"] == []


def test_duplicate_pending_task_is_idempotent(core):
    arrive(core)
    first = core.memory_manager.add_context_task("submit assignment")
    assert core.memory_manager.add_context_task("submit assignment").id == first.id
    core.memory_manager.complete_context_task(first.id)
    assert core.memory_manager.add_context_task("submit assignment").id != first.id


def test_rules_only_match_event_episode_status_and_trigger(core):
    episode = arrive(core)
    task = core.memory_manager.add_context_task("assignment")
    event = ContextEvent(ContextEventType.LEAVE)
    assert context_exit_reminders(event, episode.id, [task]) == [task]
    assert context_exit_reminders(event, "other-episode", [task]) == []
    assert context_exit_reminders(ContextEvent(ContextEventType.ARRIVE), episode.id, [task]) == []


def test_legacy_schema_upgrade_preserves_memory_rows_and_is_idempotent(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT NOT NULL,
            category TEXT NOT NULL, confidence REAL NOT NULL, timestamp TEXT NOT NULL)""")
        connection.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?)",
                           ("sentinel", "I prefer Brave", "user_preference", 0.9, "2026-09-21T10:00:00"))
        before = connection.execute("SELECT * FROM memories").fetchall()
    episode_id = None
    for _ in range(2):
        with MemoryStore(path) as store:
            manager = MemoryManager(store)
            episode = manager.start_episode()
            assert episode_id is None or episode.id == episode_id
            episode_id = episode.id
            assert manager.get_memory("sentinel").content == "I prefer Brave"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM memories").fetchall() == before
        assert connection.execute("SELECT count(*) FROM context_episodes").fetchone() == (1,)


def test_database_enforces_single_active_episode_and_task_foreign_key(core):
    episode = arrive(core)
    with pytest.raises(MemoryStorageError):
        with core.memory_manager.store.transaction():
            core.memory_manager.store._execute("""INSERT INTO context_episodes
                SELECT 'second', name, started_at, status, ended_at, memory_ids, metadata
                FROM context_episodes WHERE id = ?""", (episode.id,))
    task = core.memory_manager.add_context_task("assignment")
    with pytest.raises(MemoryStorageError):
        with core.memory_manager.store.transaction():
            core.memory_manager.store._execute("UPDATE context_tasks SET episode_id = 'missing' WHERE id = ?", (task.id,))


def test_close_failure_rolls_back_and_does_not_announce_success(core, monkeypatch, capsys):
    arrive(core)
    core.memory_manager.add_context_task("private assignment")
    original = core.memory_manager.store.save_episode

    def fail_after_write(episode):
        original(episode)
        raise MemoryStorageError("Storage failed.")

    monkeypatch.setattr(core.memory_manager.store, "save_episode", fail_after_write)
    monkeypatch.setattr(main, "MemoryManager", lambda: MemoryManager(core.memory_manager.store))
    assert main.handle_command("I'm leaving.") == []
    assert core.memory_manager.get_active_episode() is not None
    output = capsys.readouterr().out
    assert "storage is unavailable" in output
    assert "private assignment" not in output and "Context closed" not in output


def test_full_cli_demo_uses_no_ai_dispatch_or_history(monkeypatch, capsys):
    ai = Mock(side_effect=AssertionError("No AI call"))
    dispatch = Mock(side_effect=AssertionError("No action dispatch"))
    monkeypatch.setattr(main, "process_natural_language_command", ai)
    monkeypatch.setattr(main, "execute", dispatch)
    main.handle_command("I'm here.")
    saved = main.handle_command("Remember that I need to submit my assignment before I leave.")
    main.handle_command("I'm leaving.")
    output = capsys.readouterr().out
    assert "Before you leave, still pending: submit my assignment" in output
    assert "Context closed" in output
    with MemoryManager() as manager:
        assert manager.get_active_episode() is None
        assert manager.get_memory_count() == 0
        assert manager.get_latest_episode().id == saved[0]["task"]["episode_id"]
    assert not Path(logger.LOG_FILE).exists()
    ai.assert_not_called()
    dispatch.assert_not_called()


def test_cli_completion_prevents_exit_reminder(capsys):
    main.handle_command("I've arrived.")
    result = main.handle_command("Remind me to finish project before I leave.")
    task_id = result[0]["task"]["id"]
    main.handle_command(f"complete context task {task_id}")
    capsys.readouterr()
    main.handle_command("I'm leaving.")
    assert capsys.readouterr().out == "Context closed.\n"


def test_no_context_reminder_is_not_saved_as_permanent_preference(capsys):
    assert main.handle_command("Remember that I need to submit assignment before I leave.") == []
    assert "No active context" in capsys.readouterr().out
    with MemoryManager() as manager:
        assert manager.get_memory_count() == 0


@pytest.mark.parametrize("command", ["remember that I prefer Python", "open yt", "search I'm here", "please help me", "I'm not leaving", "I've arrived tomorrow"])
def test_unrecognized_context_phrases_leave_existing_routing_intact(command):
    assert parse_context_event(command) is None
    assert main.route_command(command)[0] != "context"


def test_invalid_updates_are_atomic_and_payloads_not_in_errors(core):
    episode = arrive(core)
    manager = core.memory_manager
    for kwargs in ({"memory_ids": ["missing"]}, {"metadata": {"private": object()}}, {"name": " "}):
        with pytest.raises(ContextStateError) as exc:
            manager.update_episode(**kwargs)
        assert "private" not in str(exc.value)
        assert manager.get_active_episode() == episode
    with pytest.raises(ContextStateError):
        manager.complete_context_task("missing")
    with pytest.raises(ContextStateError):
        core.handle_event(ContextEvent("execute_shell"))


def test_corrupt_episode_data_is_controlled(core):
    episode = arrive(core)
    with core.memory_manager.store.transaction():
        core.memory_manager.store._execute("UPDATE context_episodes SET metadata = ? WHERE id = ?",
                                          ('["private"]', episode.id))
    with pytest.raises(MemoryStorageError, match="Stored context data is invalid"):
        core.memory_manager.get_active_episode()


def test_context_resources_are_isolated(core, isolated_resources):
    assert isolated_resources.permits(core.memory_manager.store.db_path)
    assert core.memory_manager.get_active_episode() is None
    assert core.continuity_snapshot() is None


def test_failed_schema_initialization_rolls_back_additions(tmp_path, monkeypatch):
    path = tmp_path / "migration-failure.db"
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT NOT NULL,
            category TEXT NOT NULL, confidence REAL NOT NULL, timestamp TEXT NOT NULL)""")
        connection.execute("INSERT INTO memories VALUES ('sentinel', 'keep', 'test', 1, '2026-09-21T00:00:00')")
    initialize = MemoryStore._initialize_context_schema

    def fail(store):
        initialize(store)
        raise MemoryStorageError("Initialization failed.")

    monkeypatch.setattr(MemoryStore, "_initialize_context_schema", fail)
    with pytest.raises(MemoryStorageError):
        MemoryStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT content FROM memories").fetchall() == [('keep',)]
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('memories',)]
