"""
Usage Example: Memory Manager Integration

This example demonstrates how the Memory Manager can be used
in conjunction with the existing Personal AI OS v1 system.

Example uses:
1. Recording user preferences
2. Storing system configurations
3. Tracking interactions
4. Retrieving memories on demand

Note: This is a demonstration. The actual integration into
the main system flow is not implemented in this milestone.
"""

from memory import MemoryManager, Memory


def demonstrate_memory_manager():
    """Demonstrate the Memory Manager functionality."""
    
    print("\n" + "=" * 70)
    print("MEMORY MANAGER - USAGE EXAMPLE")
    print("=" * 70)
    
    # Initialize the Memory Manager (acts as the single gateway)
    memory_manager = MemoryManager()
    
    print("\n1. ADDING MEMORIES")
    print("-" * 70)
    
    # Add some example memories
    preferences_id = memory_manager.add_memory(
        content="User prefers dark mode for desktop applications",
        category="user_preference",
        confidence=0.95,
    )
    print(f"✓ Added user preference memory (ID: {preferences_id[:12]}...)")
    
    config_id = memory_manager.add_memory(
        content="Default browser is Google Chrome",
        category="system_config",
        confidence=1.0,
    )
    print(f"✓ Added system config memory (ID: {config_id[:12]}...)")
    
    interaction_id = memory_manager.add_memory(
        content="User opened VS Code to edit Python file",
        category="interaction",
        confidence=0.88,
    )
    print(f"✓ Added interaction memory (ID: {interaction_id[:12]}...)")
    
    # Add more memories
    memory_manager.add_memory(
        content="User timezone is IST (UTC+5:30)",
        category="user_preference",
        confidence=0.9,
    )
    memory_manager.add_memory(
        content="Home directory is /Users/Ankush",
        category="system_config",
        confidence=1.0,
    )
    
    print(f"\nTotal memories stored: {memory_manager.get_memory_count()}")
    
    print("\n2. RETRIEVING MEMORIES")
    print("-" * 70)
    
    # Retrieve a specific memory
    memory = memory_manager.get_memory(preferences_id)
    print(f"✓ Retrieved memory:")
    print(f"  Content: {memory.content}")
    print(f"  Category: {memory.category}")
    print(f"  Confidence: {memory.confidence}")
    print(f"  Timestamp: {memory.timestamp}")
    
    print("\n3. FILTERING BY CATEGORY")
    print("-" * 70)
    
    # Get all user preferences
    preferences = memory_manager.get_memories_by_category("user_preference")
    print(f"✓ User preferences ({len(preferences)} items):")
    for mem in preferences:
        print(f"  - {mem.content} (confidence: {mem.confidence})")
    
    # Get all system configs
    configs = memory_manager.get_memories_by_category("system_config")
    print(f"\n✓ System configs ({len(configs)} items):")
    for mem in configs:
        print(f"  - {mem.content} (confidence: {mem.confidence})")
    
    print("\n4. SEARCHING MEMORIES")
    print("-" * 70)
    
    # Search for memories containing "user"
    results = memory_manager.search_memories("user")
    print(f"✓ Search results for 'user' ({len(results)} items):")
    for mem in results:
        print(f"  - [{mem.category}] {mem.content}")
    
    # Search within a category
    chrome_results = memory_manager.search_memories("chrome")
    print(f"\n✓ Search results for 'chrome' ({len(chrome_results)} items):")
    for mem in chrome_results:
        print(f"  - [{mem.category}] {mem.content}")
    
    print("\n5. UPDATING MEMORIES")
    print("-" * 70)
    
    # Update a memory
    updated = memory_manager.update_memory(
        preferences_id,
        content="User prefers dark mode for desktop applications and terminal",
        confidence=0.97,
    )
    print(f"✓ Updated memory:")
    print(f"  New content: {updated.content}")
    print(f"  New confidence: {updated.confidence}")
    
    print("\n6. DELETING MEMORIES")
    print("-" * 70)
    
    # Delete a memory
    deleted = memory_manager.delete_memory(interaction_id)
    print(f"✓ Deleted interaction memory")
    print(f"  Remaining memories: {memory_manager.get_memory_count()}")
    
    print("\n7. MEMORY OVERVIEW")
    print("-" * 70)
    
    # Get all memories
    all_memories = memory_manager.get_all_memories()
    print(f"✓ All stored memories ({len(all_memories)} total):")
    for mem in all_memories:
        print(f"  - [{mem.category}] {mem.content}")
        print(f"    └─ ID: {mem.id[:12]}... | Confidence: {mem.confidence}")
    
    print("\n" + "=" * 70)
    print("MEMORY MANAGER DEMONSTRATION COMPLETE")
    print("=" * 70)
    print("\nKey Points:")
    print("✓ Single gateway pattern: All memory operations through MemoryManager")
    print("✓ Clear data structure: Memories have content, category, confidence, timestamp, ID")
    print("✓ In-memory storage: No database persistence in this milestone")
    print("✓ CRUD operations: Add, retrieve, update, delete memories")
    print("✓ Search & filter: Find memories by content or category")
    print("\n")


if __name__ == "__main__":
    demonstrate_memory_manager()
