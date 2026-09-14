"""Keep collection and every test away from application-owned resources."""

import os
from pathlib import Path
import sqlite3
import tempfile
from copy import deepcopy
from unittest.mock import patch

import pytest


class TestResources:
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory(prefix="agent-tests-")
        self.root = Path(self.directory.name).resolve()
        self.default_db = self.root / "collection.db"
        self.allowed_roots = [self.root]
        self.connections = []

    def permits(self, path):
        resolved = Path(path).resolve()
        return any(resolved.is_relative_to(root) for root in self.allowed_roots)

    def close_connections(self):
        for connection in self.connections:
            connection.close()
        self.connections.clear()


def pytest_configure(config):
    # configure runs before collection imports main/executor and their singletons.
    resources = TestResources()
    config._agent_test_resources = resources
    patches = pytest.MonkeyPatch()
    config._agent_test_patches = patches
    config._agent_original_environment = dict(os.environ)
    for name in (
        "GEMINI_API_KEY", "GEMINI_MODEL", "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION",
    ):
        os.environ.pop(name, None)

    connect = sqlite3.connect

    def isolated_connect(database, *args, **kwargs):
        if str(database) != ":memory:" and not resources.permits(database):
            raise AssertionError("Tests may only open SQLite databases in temporary test resources.")
        connection = connect(database, *args, **kwargs)
        resources.connections.append(connection)
        return connection

    patches.setattr(sqlite3, "connect", isolated_connect)

    from memory import MemoryStore

    initialize = MemoryStore.__init__

    def isolated_store(self, db_path=None):
        initialize(self, db_path if db_path is not None else resources.default_db)

    patches.setattr(MemoryStore, "__init__", isolated_store)

    import dotenv

    find_dotenv = dotenv.find_dotenv

    def isolated_find_dotenv(*args, **kwargs):
        candidate = find_dotenv(*args, **kwargs)
        return candidate if candidate and resources.permits(candidate) else ""

    patches.setattr(dotenv, "find_dotenv", isolated_find_dotenv)

    import logger

    patches.setattr(logger, "LOG_FOLDER", str(resources.root / "collection-logs"))
    patches.setattr(logger, "LOG_FILE", str(resources.root / "collection-logs" / "history.log"))


@pytest.fixture(autouse=True)
def isolated_resources(request, tmp_path):
    resources = request.config._agent_test_resources
    resources.close_connections()
    resources.default_db = tmp_path / "default-memory.db"
    resources.allowed_roots = [resources.root, tmp_path.resolve()]

    import config
    import executor
    import logger
    from context import ContextEngine
    from memory import MemoryManager

    # Keep imported configuration aliases pointing at their original objects.
    dictionaries = [(value, deepcopy(value)) for name, value in vars(config).items()
                    if name.isupper() and isinstance(value, dict)]
    dictionaries.append((executor.ACTION_MAP, executor.ACTION_MAP.copy()))
    with patch.dict(os.environ, dict(os.environ), clear=True), pytest.MonkeyPatch.context() as patches:
        patches.chdir(tmp_path)
        patches.setattr(logger, "LOG_FOLDER", str(tmp_path / "logs"))
        patches.setattr(logger, "LOG_FILE", str(tmp_path / "logs" / "history.log"))
        manager = MemoryManager()
        patches.setattr(executor, "memory_manager", manager)
        patches.setattr(executor, "context_engine", ContextEngine(manager))
        try:
            yield resources
        finally:
            resources.close_connections()
            for current, original in dictionaries:
                current.clear()
                current.update(original)


def pytest_unconfigure(config):
    resources = getattr(config, "_agent_test_resources", None)
    if resources is not None:
        try:
            resources.close_connections()
        finally:
            config._agent_test_patches.undo()
            os.environ.clear()
            os.environ.update(config._agent_original_environment)
            resources.directory.cleanup()
