"""Tests for the Context Engine."""

from memory import MemoryManager
from context import ContextEngine


def test_runtime_information_included():
    """Runtime information should be included in the structured output."""
    manager = MemoryManager()
    engine = ContextEngine(manager)

    context = engine.build_context(
        user_context={"active_application": "VS Code"},
        system_context={"default_browser": "Chrome"},
    )

    assert "current_datetime" in context.runtime
    assert context.timestamp == context.runtime["current_datetime"]
    assert context.user_context["active_application"] == "VS Code"
    assert context.system_context["default_browser"] == "Chrome"


def test_browser_configuration_is_exposed_in_system_context():
    manager = MemoryManager()
    engine = ContextEngine(manager)

    context = engine.build_context()

    assert context.system_context["browsers"] == {
        "available": ["safari", "brave"],
        "preferred": "brave",
    }


def test_memories_are_included_via_memory_manager():
    """ContextEngine should use MemoryManager to retrieve memories."""
    manager = MemoryManager()
    manager.clear_all_memories()

    manager.add_memory("User prefers dark mode", "user_preference", 0.95)
    manager.add_memory("Default browser is Chrome", "system_config", 1.0)

    engine = ContextEngine(manager)
    context = engine.build_context(categories=["user_preference", "system_config"])

    assert len(context.relevant_memories) == 2
    assert any(memory.content == "User prefers dark mode" for memory in context.relevant_memories)
    assert any(memory.content == "Default browser is Chrome" for memory in context.relevant_memories)


def test_context_engine_uses_memory_manager_not_store_directly():
    """The engine must not require direct MemoryStore access."""
    manager = MemoryManager()
    manager.clear_all_memories()
    manager.add_memory("User likes Python", "user_preference", 0.9)

    engine = ContextEngine(manager)
    context = engine.build_context(query="python")

    assert context.relevant_memories[0].content == "User likes Python"
    assert context.summary.startswith("Current time:")


def test_structured_context_output():
    """Structured output should be simple and deterministic."""
    manager = MemoryManager()
    manager.clear_all_memories()
    manager.add_memory("User prefers dark mode", "user_preference", 0.95)

    engine = ContextEngine(manager)
    context = engine.build_context(
        user_context={"active_application": "VS Code"},
        system_context={"default_browser": "Chrome"},
        query="dark mode",
    )

    result = context.to_dict()

    assert "timestamp" in result
    assert "runtime" in result
    assert "user_context" in result
    assert "system_context" in result
    assert "relevant_memories" in result
    assert "summary" in result
    assert result["relevant_memories"][0]["content"] == "User prefers dark mode"


if __name__ == "__main__":
    test_runtime_information_included()
    test_memories_are_included_via_memory_manager()
    test_context_engine_uses_memory_manager_not_store_directly()
    test_structured_context_output()
    print("Context Engine tests passed.")
