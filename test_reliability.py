"""HP10-D regression tests, using only B1 temporary resources."""

if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

import httpx
import pytest

import executor
import logger
import main
from actions.email import extract_email_fields, validate_email_provenance
from ai.brain import AIBrain
from ai.gemini import GeminiProvider, GeminiProviderError
from ai.orchestrator import AIOrchestrator, process_natural_language_command
from ai.errors import AIPlanningError, AIProviderError, TaskExecutionError
from ai.task_execution import execute_task
from memory import MemoryManager, MemoryStore, Memory
from memory.errors import MemoryStorageError


def test_task_and_handler_copies_preserve_nested_plan_and_sibling_steps():
    shared = {"nested": {"values": [1]}}
    plan = [{"action": "help", "target": "help", "params": shared} for _ in range(2)]
    original = deepcopy(plan)
    seen = []
    def mutate(action):
        seen.append(deepcopy(action))
        action["params"]["nested"]["values"].append(2)
    task = execute_task(plan, mutate)
    assert plan == original and seen == original
    assert task.steps[0].action["params"] is not task.steps[1].action["params"]
    assert [step.action for step in task.steps] == original
    json.dumps(asdict(task))


def test_executor_context_has_no_circular_references_and_does_not_mutate_plan():
    command = {"action": "draft_email", "target": "gmail", "params": {"to": "", "subject": "", "body": "Test"}}
    before = deepcopy(command)
    captured = []
    with patch.dict(executor.ACTION_MAP, {"draft_email": lambda target, params: captured.append(params)}):
        task = execute_task([command], executor.execute)
    assert command == before and task.steps[0].action == before
    assert "context" not in command["params"]
    json.dumps(captured)
    captured[0]["context"]["system_context"]["browsers"]["preferred"] = "changed"
    assert command == before


def test_failure_does_not_mutate_plan_or_execute_later_steps():
    plan = [{"action": "help", "target": "help", "params": {}} for _ in range(2)]
    original = deepcopy(plan)
    calls = []
    def fail(action):
        calls.append(action)
        action["params"]["private"] = "do not persist"
        raise OSError("private detail")
    with pytest.raises(TaskExecutionError):
        execute_task(plan, fail)
    assert len(calls) == 1 and plan == original


def test_imports_do_not_open_a_database():
    script = "import sqlite3; sqlite3.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError('unexpected database')); import executor, main"
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=Path(__file__).resolve().parent,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_owned_and_borrowed_store_lifetimes():
    with MemoryManager() as owned:
        owned.add_memory("fixture", "test")
        connection = owned.store._connection
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    store = MemoryStore()
    with MemoryManager(store) as borrowed:
        assert borrowed.store is store
    assert store.count() == 1  # A borrowing manager must not close its caller's store.
    store.close()


@pytest.mark.parametrize("failure", ["readonly", "locked"])
def test_write_failure_does_not_report_remembered(failure, tmp_path, capsys):
    store = MemoryStore(tmp_path / "failure.db")
    other = None
    if failure == "readonly":
        store._connection.execute("PRAGMA query_only = ON").close()
    else:
        store._connection.execute("PRAGMA busy_timeout = 1").close()
        other = sqlite3.connect(store.db_path)
        other.execute("BEGIN IMMEDIATE").close()
    try:
        with patch.object(main, "MemoryManager", return_value=MemoryManager(store)):
            assert main.handle_command("Remember that private fixture") == []
        assert store.count() == 0
        output = capsys.readouterr().out
        assert "storage is unavailable" in output and "Preference remembered" not in output
        assert "private fixture" not in output
    finally:
        if other is not None:
            other.rollback()
            other.close()
        store.close()


@pytest.mark.parametrize("failure", ["corrupt", "unavailable"])
def test_unusable_database_is_controlled_and_connection_closed(failure, tmp_path):
    path = tmp_path / "bad.db"
    if failure == "corrupt":
        path.write_bytes(b"not a sqlite database")
    else:
        path = tmp_path / "missing" / "bad.db"
    with pytest.raises(MemoryStorageError):
        MemoryStore(path)
    with patch.object(main, "MemoryManager", side_effect=MemoryStorageError("storage unavailable")):
        assert main.handle_command("Remember that fixture") == []


def test_initialization_failure_closes_the_new_connection(tmp_path):
    connection = sqlite3.connect(tmp_path / "init.db")
    connection.execute("PRAGMA query_only = ON").close()
    with patch("memory.store.sqlite3.connect", return_value=connection):
        with pytest.raises(MemoryStorageError):
            MemoryStore(tmp_path / "init.db")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_corrupt_memory_row_is_a_controlled_storage_error(tmp_path):
    with MemoryStore(tmp_path / "row.db") as store:
        memory_id = store.add(Memory("fixture", "test"))
        store._connection.execute("UPDATE memories SET content = ? WHERE id = ?", (b"invalid binary content", memory_id)).close()
        store._connection.commit()
        with pytest.raises(MemoryStorageError):
            store.get_all()


def test_preference_replacement_failure_rolls_back_every_change(tmp_path):
    store = MemoryStore(tmp_path / "atomic.db")
    manager = MemoryManager(store)
    store.add(Memory("I prefer Brave", "user_preference"))
    store.add(Memory("I prefer Brave", "user_preference"))
    before = [memory.to_dict() for memory in manager.get_all_memories()]
    with patch.object(manager, "delete_memory", side_effect=MemoryStorageError("failed delete")):
        with pytest.raises(MemoryStorageError):
            manager.add_memory("I prefer Safari", "user_preference")
    assert [memory.to_dict() for memory in manager.get_all_memories()] == before
    manager.add_memory("I prefer Safari", "user_preference")
    assert [memory.content for memory in manager.get_all_memories()] == ["I prefer Safari"]


def test_non_memory_execution_never_opens_storage(tmp_path):
    with patch.object(executor, "context_engine", None), \
         patch.object(executor, "MemoryManager", side_effect=MemoryStorageError("unavailable")):
        assert main.handle_command("help")
        assert main.handle_command("create file Test.txt")
    assert (tmp_path / "Test.txt").exists()


def test_injected_context_does_not_create_owned_storage_and_storage_failure_stops_ai():
    class Context:
        def build_context(self, **kwargs):
            return {}
    class Brain:
        def plan(self, *args):
            return {"actions": [{"action": "help", "target": "help", "params": {}}]}
    calls = []
    with patch("ai.orchestrator.MemoryManager", side_effect=MemoryStorageError("private database path")):
        process_natural_language_command("Help me", brain=Brain(), context_engine=Context(), executor_func=calls.append)
        assert len(calls) == 1
        calls.clear()
        with pytest.raises(AIPlanningError):
            process_natural_language_command("Help me", brain=Brain(), executor_func=calls.append)
        assert calls == []


@pytest.mark.parametrize("command,expected", [
    ("Draft an email to professor@example.com. Subject Hello, professor! Body I am not absent.",
     {"to": "professor@example.com", "subject": "Hello, professor!", "body": "I am not absent."}),
    ("Draft an email saying I'll be absent tomorrow.", {"to": "", "subject": "", "body": "I'll be absent tomorrow."}),
    ('Prepare an email with subject "Hello, world!"', {"to": "", "subject": "Hello, world!", "body": ""}),
    ('Compose an email to a@example.com with subject "body: notes" and body "Line 1\n\n日本語; & notes!"',
     {"to": "a@example.com", "subject": "body: notes", "body": "Line 1\n\n日本語; & notes!"}),
    ('Draft an email to my professor saying "  Keep spaces.  "', {"to": "", "subject": "", "body": "  Keep spaces.  "}),
    ("Draft an email subject:I'll be away body:I'm not absent.", {"to": "", "subject": "I'll be away", "body": "I'm not absent."}),
    ('Draft an email subject "" body "Hello!"', {"to": "", "subject": "", "body": "Hello!"}),
])
def test_complete_email_fields_preserve_punctuation_and_partial_fields(command, expected):
    assert extract_email_fields(command) == expected
    validate_email_provenance(command, expected)


@pytest.mark.parametrize("field,value", [("to", ""), ("subject", ""), ("body", ""), ("body", "absent"), ("body", "I am"), ("subject", "Hello")])
def test_email_omission_and_substrings_execute_nothing(field, value):
    command = "Draft an email to a@example.com subject Hello, world! body I am not absent"
    fields = {"to": "a@example.com", "subject": "Hello, world!", "body": "I am not absent"}
    fields[field] = value
    class Provider:
        def generate_text(self, prompt):
            return json.dumps({"actions": [{"action": "draft_email", "target": "gmail", "params": fields}]})
    calls = []
    with pytest.raises(AIPlanningError):
        process_natural_language_command(command, brain=AIBrain(Provider()), executor_func=calls.append)
    assert calls == []


@pytest.mark.parametrize("command", [
    "Draft an email body Hello subject Hi",
    "Draft an email saying Hello to a@example.com",
    "Draft an email body One body Two",
])
def test_ambiguous_reordered_fields_are_rejected(command):
    with pytest.raises(ValueError, match="ambiguous"):
        extract_email_fields(command)


def test_quoted_body_may_contain_literal_field_labels():
    fields = extract_email_fields('Draft an email body "The subject is literal; send this to a@example.com."')
    assert fields == {"to": "", "subject": "", "body": "The subject is literal; send this to a@example.com."}


def test_provider_and_task_diagnostics_do_not_echo_errors(capsys):
    class Client:
        class interactions:
            @staticmethod
            def create(**kwargs):
                raise httpx.ConnectError("private@example.com https://private.example/?body=secret")
    with patch("ai.gemini.genai.Client", return_value=Client()):
        with pytest.raises(GeminiProviderError):
            GeminiProvider(api_key="test-key").generate_text("private prompt")
    output = capsys.readouterr().out
    assert "category=network" in output
    assert "private" not in output and "secret" not in output


@pytest.mark.parametrize("action,target", [("search", "private query"), ("open", "https://private.example/?secret=value"), ("draft_email", "private@example.com"), ("delete", "PrivatePath.txt")])
def test_history_redacts_payload_and_uses_utf8(action, target, capsys):
    with patch("logger.open", wraps=open) as writer:
        logger.log_action(action, target, "failed", error=OSError("private error"))
    assert writer.call_args.kwargs["encoding"] == "utf-8"
    output = capsys.readouterr().out + Path(logger.LOG_FILE).read_text(encoding="utf-8")
    assert target not in output and "private error" not in output
    assert f"action={action}" in output and "status=failed" in output


def test_log_write_failure_is_nonfatal_and_paths_are_not_printed(tmp_path, capsys):
    with patch("logger.open", side_effect=PermissionError("private path")):
        assert main.handle_command("create file PrivateName.txt")
    assert (tmp_path / "PrivateName.txt").exists()
    output = capsys.readouterr().out
    assert "History unavailable" in output
    assert "PrivateName" not in output and "private path" not in output


def test_remember_confirmation_does_not_echo_content_but_explicit_retrieval_does(capsys):
    assert main.handle_command("Remember that I prefer Brave.")
    assert "I prefer Brave" not in capsys.readouterr().out
    main.handle_command("What are my preferences?")
    assert "I prefer Brave" in capsys.readouterr().out


@pytest.mark.parametrize("error", [AIPlanningError, AIProviderError, TaskExecutionError])
def test_cli_never_echoes_arbitrary_exception_payloads(error, capsys):
    with patch.object(main, "process_natural_language_command", side_effect=error("private@example.com secret")):
        assert main.handle_command("Please help") == []
    output = capsys.readouterr().out
    assert "private" not in output and "secret" not in output
