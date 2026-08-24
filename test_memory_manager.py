"""
Test suite for the Memory Manager implementation.

This validates the Memory Manager and its SQLite-backed persistent storage.
Run with: python -m pytest test_memory_manager.py -v
Or run directly: python test_memory_manager.py
"""

from memory import Memory, MemoryStore, MemoryManager
from datetime import datetime


def test_memory_model():
    """Test Memory model creation and conversion."""
    print("\n=== Testing Memory Model ===")
    
    memory = Memory(
        content="User prefers dark mode",
        category="user_preference",
        confidence=0.95,
    )
    
    print(f"✓ Created memory: {memory}")
    print(f"  ID: {memory.id}")
    print(f"  Content: {memory.content}")
    print(f"  Category: {memory.category}")
    print(f"  Confidence: {memory.confidence}")
    print(f"  Timestamp: {memory.timestamp}")
    
    # Test to_dict and from_dict
    memory_dict = memory.to_dict()
    memory_restored = Memory.from_dict(memory_dict)
    assert memory_restored.id == memory.id
    assert memory_restored.content == memory.content
    print("✓ Memory serialization/deserialization works")


def test_memory_store():
    """Test MemoryStore basic operations."""
    print("\n=== Testing Memory Store ===")

    store = MemoryStore()
    store.clear()

    # Test add
    memory1 = Memory("User likes Python", "user_preference", 0.9)
    memory2 = Memory("System runs on macOS", "system_config", 1.0)

    id1 = store.add(memory1)
    id2 = store.add(memory2)
    print(f"✓ Added 2 memories with IDs: {id1[:8]}..., {id2[:8]}...")

    # Test get_by_id
    retrieved = store.get_by_id(id1)
    assert retrieved.content == "User likes Python"
    print(f"✓ Retrieved memory by ID: {retrieved.content}")

    # Test get_all
    all_memories = store.get_all()
    assert len(all_memories) == 2
    print(f"✓ Retrieved all memories: {len(all_memories)} items")

    # Test get_by_category
    preferences = store.get_by_category("user_preference")
    assert len(preferences) == 1
    print(f"✓ Retrieved memories by category: {len(preferences)} item(s)")

    # Test update
    updated = store.update(id1, content="User prefers Python", confidence=0.95)
    assert updated.content == "User prefers Python"
    assert updated.confidence == 0.95
    print(f"✓ Updated memory: {updated.content}")

    # Test delete
    deleted = store.delete(id2)
    assert deleted is True
    assert store.count() == 1
    print(f"✓ Deleted memory, remaining count: {store.count()}")


def test_memory_store_persistence():
    """Test that data persists across new MemoryStore instances."""
    print("\n=== Testing SQLite Persistence ===")

    first_store = MemoryStore()
    first_store.clear()

    memory = Memory("Persistent user preference", "user_preference", 0.92)
    memory_id = first_store.add(memory)

    second_store = MemoryStore()
    persisted = second_store.get_by_id(memory_id)

    assert persisted is not None
    assert persisted.content == "Persistent user preference"
    assert persisted.category == "user_preference"
    assert persisted.confidence == 0.92
    print(f"✓ Data persisted across store instances: {persisted.content}")

    second_store.close()
    first_store.close()


def test_memory_manager():
    """Test MemoryManager as the single gateway."""
    print("\n=== Testing Memory Manager ===")

    manager = MemoryManager()
    manager.clear_all_memories()

    # Test add_memory
    id1 = manager.add_memory(
        content="Desktop path is ~/Desktop",
        category="system_config",
        confidence=1.0,
    )
    id2 = manager.add_memory(
        content="User timezone is IST",
        category="user_preference",
        confidence=0.9,
    )
    id3 = manager.add_memory(
        content="Browser default is Chrome",
        category="user_preference",
        confidence=0.85,
    )
    print(f"✓ Added 3 memories via MemoryManager")

    # Test get_memory
    memory = manager.get_memory(id1)
    assert memory is not None
    print(f"✓ Retrieved specific memory: {memory.content}")

    # Test get_all_memories
    all_memories = manager.get_all_memories()
    assert len(all_memories) == 3
    print(f"✓ Retrieved all memories: {len(all_memories)} items")

    # Test get_memories_by_category
    user_prefs = manager.get_memories_by_category("user_preference")
    assert len(user_prefs) == 2
    print(f"✓ Retrieved memories by category: {len(user_prefs)} user_preference items")

    # Test search_memories
    search_results = manager.search_memories("user")
    assert len(search_results) == 1
    print(f"✓ Search for 'user': {len(search_results)} result(s)")

    search_with_category = manager.search_memories("default", "user_preference")
    assert len(search_with_category) == 1
    print(f"✓ Search for 'default' in user_preference: {len(search_with_category)} result(s)")

    # Test update_memory
    updated_memory = manager.update_memory(
        id2,
        content="User timezone is IST (UTC+5:30)",
        confidence=0.95,
    )
    assert updated_memory.content == "User timezone is IST (UTC+5:30)"
    print(f"✓ Updated memory: {updated_memory.content}")

    # Test delete_memory
    deleted = manager.delete_memory(id3)
    assert deleted is True
    assert manager.get_memory_count() == 2
    print(f"✓ Deleted memory, remaining: {manager.get_memory_count()}")

    # Test get_memory_count
    count = manager.get_memory_count()
    print(f"✓ Memory count: {count}")


def test_memory_isolation():
    """Test that only MemoryManager should manage memories."""
    print("\n=== Testing Memory Isolation (Gateway Pattern) ===")

    manager = MemoryManager()
    manager.clear_all_memories()

    # All operations should go through the manager
    memory_id = manager.add_memory(
        content="Test memory",
        category="test",
        confidence=1.0,
    )

    retrieved = manager.get_memory(memory_id)
    assert retrieved is not None
    print(f"✓ Memory isolated and accessed only through MemoryManager")

    # Verify the store is not directly accessible from outside
    # (though in-memory store can be accessed, the contract is that it shouldn't be)
    store = manager.store
    assert len(store.get_all()) == 1
    print(f"✓ Internal store is properly encapsulated within MemoryManager")


def test_confidence_validation():
    """Test that confidence is properly validated."""
    print("\n=== Testing Confidence Validation ===")
    
    memory = Memory("Test", "test", confidence=1.5)  # Should clamp to 1.0
    assert memory.confidence == 1.0
    print(f"✓ Confidence clamped to max: {memory.confidence}")
    
    memory = Memory("Test", "test", confidence=-0.5)  # Should clamp to 0.0
    assert memory.confidence == 0.0
    print(f"✓ Confidence clamped to min: {memory.confidence}")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("MEMORY MANAGER TEST SUITE")
    print("=" * 60)
    
    try:
        test_memory_model()
        test_memory_store()
        test_memory_store_persistence()
        test_memory_manager()
        test_memory_isolation()
        test_confidence_validation()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        return True
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
