import io
import sqlite3
from contextlib import redirect_stdout

import main
from main import handle_command, parse_memory_query, parse_remember_command, route_command
from memory import Memory, MemoryManager


def test_explicit_remember_command_creates_persistent_memory():
    manager = MemoryManager()
    manager.clear_all_memories()

    parsed = parse_remember_command("Remember that I prefer Brave.")
    assert parsed == {
        "action": "remember",
        "target": "I prefer Brave",
        "params": {},
    }

    handle_command("Remember that I prefer Brave.")

    stored = manager.search_memories("Brave", category="user_preference")
    assert len(stored) == 1
    assert stored[0].content == "I prefer Brave"
    assert stored[0].confidence == 1.0

    with sqlite3.connect(manager.store.db_path) as connection:
        row = connection.execute(
            "SELECT content, category, confidence FROM memories WHERE id = ?",
            (stored[0].id,),
        ).fetchone()

    assert row == ("I prefer Brave", "user_preference", 1.0)

    new_manager = MemoryManager()
    persisted = new_manager.get_memory(stored[0].id)
    assert persisted is not None
    assert persisted.content == "I prefer Brave"


def test_remember_command_forms_are_supported():
    assert parse_remember_command("remember I prefer Brave")["target"] == "I prefer Brave"
    assert (
        parse_remember_command("remember that my preferred browser is Brave")["target"]
        == "my preferred browser is Brave"
    )


def test_remember_commands_do_not_use_ai_routing():
    route, parsed = route_command("remember I prefer Brave")
    assert route == "memory"
    assert parsed[0]["action"] == "remember"


def test_existing_command_routing_still_works():
    route, parsed = route_command("open file notes.txt")
    assert route == "v1"
    assert parsed == [{"action": "open", "target": "file notes.txt", "params": {}}]


def test_memory_queries_retrieve_persisted_memories_without_ai_or_execution():
    manager = MemoryManager()
    manager.clear_all_memories()
    manager.add_memory("I prefer Brave", "user_preference", 1.0)
    manager.add_memory("User timezone is IST", "user_preference", 1.0)

    original_process = main.process_natural_language_command
    original_execute = main.execute
    try:
        main.process_natural_language_command = lambda command: (_ for _ in ()).throw(
            AssertionError("memory query must not call Gemini")
        )
        main.execute = lambda command: (_ for _ in ()).throw(
            AssertionError("memory query must not execute actions")
        )

        output = io.StringIO()
        with redirect_stdout(output):
            handle_command("What do you remember about Brave?")
        assert output.getvalue().splitlines() == ["I remember: I prefer Brave."]

        output = io.StringIO()
        with redirect_stdout(output):
            handle_command("Do you remember that I prefer Brave?")
        assert output.getvalue().splitlines() == ["I remember: I prefer Brave."]

        output = io.StringIO()
        with redirect_stdout(output):
            handle_command("What do you remember?")
        assert output.getvalue().splitlines() == [
            "I remember: I prefer Brave.",
            "I remember: User timezone is IST.",
        ]

        output = io.StringIO()
        with redirect_stdout(output):
            handle_command("What are my preferences?")
        assert output.getvalue().splitlines() == [
            "I remember: I prefer Brave.",
            "I remember: User timezone is IST.",
        ]
    finally:
        main.process_natural_language_command = original_process
        main.execute = original_execute


def test_memory_query_detection_extracts_search_text():
    assert parse_memory_query("What do you remember about Brave?") == {
        "action": "retrieve",
        "query": "Brave",
        "category": None,
    }
    assert parse_memory_query("Do you remember that I prefer Brave?") == {
        "action": "retrieve",
        "query": "I prefer Brave",
        "category": None,
    }
    assert parse_memory_query("What do you remember about me?") == {
        "action": "retrieve",
        "query": None,
        "category": None,
    }
    assert parse_memory_query("What are my preferences?") == {
        "action": "retrieve",
        "query": None,
        "category": "user_preference",
    }


def test_memory_query_routes_before_ai():
    route, parsed = route_command("What do you remember about Brave?")
    assert route == "memory_retrieval"
    assert parsed[0]["query"] == "Brave"


def test_repeated_remember_command_does_not_store_duplicate():
    manager = MemoryManager()
    manager.clear_all_memories()

    handle_command("Remember that I prefer Brave.")
    handle_command("Remember that I prefer Brave.")

    stored = manager.search_memories("Brave", category="user_preference")
    assert len(stored) == 1


def test_retrieval_deduplicates_existing_equivalent_rows():
    manager = MemoryManager()
    manager.clear_all_memories()
    manager.store.add(Memory("I prefer Brave", "user_preference", 1.0))
    manager.store.add(Memory("I prefer Brave", "user_preference", 1.0))

    output = io.StringIO()
    with redirect_stdout(output):
        handle_command("What do you remember about Brave?")

    assert output.getvalue().splitlines() == ["I remember: I prefer Brave."]


def test_remembering_new_browser_preference_replaces_old_retrieval():
    manager = MemoryManager()
    manager.clear_all_memories()

    handle_command("Remember that I prefer Brave.")
    handle_command("Remember that I prefer Safari.")

    output = io.StringIO()
    with redirect_stdout(output):
        handle_command("What are my preferences?")

    assert output.getvalue().splitlines() == ["I remember: I prefer Safari."]
