"""Regression checks for test collection, persistent data, and repeatability."""

# Direct script runs must enter pytest before importing application singletons.
if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

import executor
import logger
from memory import MemoryManager, MemoryStore


def test_collection_and_default_stores_are_isolated(isolated_resources):
    manager = MemoryManager()
    assert manager.store.db_path == isolated_resources.default_db
    assert executor.memory_manager.store.db_path == isolated_resources.default_db
    assert executor.context_engine.memory_manager is executor.memory_manager
    assert manager.get_memory_count() == 0
    assert isolated_resources.permits(logger.LOG_FILE)


def test_project_database_connections_are_blocked():
    project_db = Path(__file__).resolve().parent / "memory.db"
    with pytest.raises(AssertionError, match="temporary test resources"):
        MemoryStore(project_db)
    with pytest.raises(AssertionError, match="temporary test resources"):
        sqlite3.connect(project_db)


def test_default_database_does_not_clear_an_explicit_sentinel(tmp_path):
    sentinel = MemoryManager(MemoryStore(tmp_path / "sentinel.db"))
    memory_id = sentinel.add_memory("Keep this sentinel", "test")
    MemoryManager().clear_all_memories()
    assert sentinel.get_memory(memory_id).content == "Keep this sentinel"


def test_suite_repeats_without_touching_project_data_or_environment(tmp_path):
    # An independent source copy models a checkout that already has user data.
    # Exclude this module in child runs to avoid recursive subprocess suites.
    source = Path(__file__).resolve().parent
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for path in source.glob("*.py"):
        shutil.copyfile(path, checkout / path.name)
    for package in ("actions", "ai", "context", "memory"):
        shutil.copytree(source / package, checkout / package, ignore=shutil.ignore_patterns("__pycache__"))

    store = MemoryStore(checkout / "memory.db")
    manager = MemoryManager(store)
    memory_id = manager.add_memory("User sentinel must survive both runs", "user_preference")
    store.close()
    (checkout / "logs").mkdir()
    (checkout / "logs" / "history.log").write_bytes(b"existing user history\n")
    (checkout / ".env").write_bytes(b"GEMINI_API_KEY=sentinel-file-key\nGEMINI_MODEL=sentinel-model\n")
    protected = [checkout / "memory.db", checkout / "logs" / "history.log", checkout / ".env"]
    before = {path: path.read_bytes() for path in protected}

    script = '''
import os
import pytest
before = dict(os.environ)
class Results:
    def __init__(self): self.outcomes = []
    def pytest_runtest_logreport(self, report):
        if report.when == "call" or report.failed:
            self.outcomes.append((report.nodeid, report.when, report.outcome))
results = Results()
code = pytest.main(["-q", "-p", "no:cacheprovider", "--ignore=test_test_isolation.py"], plugins=[results])
assert dict(os.environ) == before, "pytest changed the caller environment"
assert code == 0, "child suite failed"
print("ISOLATION_OUTCOMES", repr(results.outcomes))
'''
    environment = dict(os.environ, GEMINI_API_KEY="pre-existing-test-key", GEMINI_MODEL="pre-existing-test-model",
                       AGENT_SENTINEL="Exact value with Spaces", PYTHONDONTWRITEBYTECODE="1")
    outcomes = []
    for _ in range(2):
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=checkout,
                                env=environment, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        outcomes.append(next(line for line in result.stdout.splitlines() if line.startswith("ISOLATION_OUTCOMES")))
        assert {path: path.read_bytes() for path in protected} == before
    assert outcomes[0] == outcomes[1]
    # Documented direct-script entry points must not bypass collection isolation.
    direct = subprocess.run(
        [sys.executable, "-B", "test_memory_manager.py", "-q", "-p", "no:cacheprovider"],
        cwd=checkout, env=environment, capture_output=True, text=True, timeout=60,
    )
    assert direct.returncode == 0, direct.stdout + direct.stderr
    assert {path: path.read_bytes() for path in protected} == before
    with sqlite3.connect(checkout / "memory.db") as connection:
        assert connection.execute("SELECT content FROM memories WHERE id = ?", (memory_id,)).fetchone() == (
            "User sentinel must survive both runs",
        )
