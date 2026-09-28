# Memory Manager - Version 2 Milestone 1

## Overview

The Memory Manager is the first milestone of Personal AI OS v2. It implements the Memory Foundation architecture, serving as the single gateway for all memory operations.

**Architecture Flow:**
```
User / future AI Brain
         ↓
Memory Manager (Gateway)
         ↓
Memory Store (In-Memory)
         ↓
Persistent Storage (Future)
```

## Features

✅ **CRUD Operations**: Add, retrieve, update, and delete memories  
✅ **Single Gateway Pattern**: All memory operations through MemoryManager  
✅ **Clear Data Structure**: Each memory has content, category, confidence, timestamp, and ID  
✅ **Category Filtering**: Filter memories by type/category  
✅ **Search Functionality**: Full-text search within memories  
✅ **Confidence Scoring**: Track certainty level of each memory (0.0 to 1.0)  
✅ **In-Memory Storage**: No database persistence (yet - future milestone)  
✅ **Type Safety**: Proper data model with validation  

## Module Structure

```
memory/
├── __init__.py       # Module exports
├── models.py         # Memory data model
├── store.py          # In-memory storage layer
└── manager.py        # Single gateway for all operations
```

## Core Components

### 1. Memory Model (`memory/models.py`)

Represents a single memory item with a clear, structured format.

**Memory Attributes:**
- `id` (str): Unique identifier (auto-generated UUID)
- `content` (str): The actual memory content/text
- `category` (str): Type/category of memory (e.g., 'user_preference', 'system_config', 'interaction')
- `confidence` (float): Certainty level (0.0 to 1.0, default 1.0)
- `timestamp` (datetime): When the memory was created (defaults to current time)

**Example:**
```python
from memory import Memory

memory = Memory(
    content="User prefers dark mode",
    category="user_preference",
    confidence=0.95
)
```

### 2. Memory Store (`memory/store.py`)

The in-memory persistence layer. Currently stores memories in-memory; will be replaced with database in future milestones.

**Key Operations:**
- `add(memory)`: Add a memory to the store
- `get_by_id(memory_id)`: Retrieve a specific memory
- `get_all()`: Get all memories
- `get_by_category(category)`: Filter memories by category
- `update(memory_id, **kwargs)`: Update memory attributes
- `delete(memory_id)`: Remove a memory
- `count()`: Get total number of memories
- `clear()`: Clear all memories

**Note**: Direct access to MemoryStore should be avoided. Use MemoryManager instead.

### 3. Memory Manager (`memory/manager.py`)

**The single gateway for all memory operations.**

Other modules should NOT directly access MemoryStore. All memory operations must go through the MemoryManager.

**Public API:**

**Adding Memories:**
```python
memory_manager = MemoryManager()

memory_id = memory_manager.add_memory(
    content="User likes Python programming",
    category="user_preference",
    confidence=0.9
)
```

**Retrieving Memories:**
```python
# Get specific memory
memory = memory_manager.get_memory(memory_id)

# Get all memories
all_memories = memory_manager.get_all_memories()

# Get memories by category
preferences = memory_manager.get_memories_by_category("user_preference")

# Search memories
results = memory_manager.search_memories("python", category="user_preference")
```

**Updating Memories:**
```python
updated = memory_manager.update_memory(
    memory_id,
    content="User likes Python and Go",
    confidence=0.95
)
```

**Deleting Memories:**
```python
deleted = memory_manager.delete_memory(memory_id)  # Returns True if deleted
```

**Other Operations:**
```python
count = memory_manager.get_memory_count()
memory_manager.clear_all_memories()
```

## Usage Examples

### Basic Usage

```python
from memory import MemoryManager

# Initialize the manager
manager = MemoryManager()

# Add a memory
user_pref_id = manager.add_memory(
    content="User prefers dark mode",
    category="user_preference",
    confidence=0.95
)

# Retrieve it
memory = manager.get_memory(user_pref_id)
print(f"Content: {memory.content}")
print(f"Category: {memory.category}")
print(f"Confidence: {memory.confidence}")

# Update it
manager.update_memory(
    user_pref_id,
    content="User prefers dark mode and system font size 14"
)

# Delete it
manager.delete_memory(user_pref_id)
```

### Working with Categories

```python
# Store different types of memories
manager.add_memory("Desktop is ~/Desktop", "system_config", 1.0)
manager.add_memory("Browser is Chrome", "system_config", 1.0)
manager.add_memory("Prefers Python", "user_preference", 0.95)

# Retrieve by category
configs = manager.get_memories_by_category("system_config")
preferences = manager.get_memories_by_category("user_preference")
```

### Searching Memories

```python
# Search for specific content
results = manager.search_memories("python")

# Search within a category
dev_tools = manager.search_memories("vscode", category="user_preference")
```

## Testing

Run the comprehensive test suite:

```bash
python3 test_memory_manager.py
```

Expected output:
```
✓ ALL TESTS PASSED!
```

Run the usage example:

```bash
python3 example_memory_usage.py
```

## Design Principles

1. **Single Responsibility**: Each component has one clear purpose
   - Memory: Data model
   - MemoryStore: Storage implementation
   - MemoryManager: Gateway & business logic

2. **Gateway Pattern**: MemoryManager is the only entry point
   - Prevents direct store manipulation
   - Enables future storage layer changes
   - Centralizes memory logic

3. **Clear Data Structure**: Memories are not arbitrary strings
   - Structured with content, category, confidence, timestamp, ID
   - Enables filtering, searching, and future processing

4. **No External Dependencies**: Pure Python, uses only stdlib
   - uuid for unique identifiers
   - datetime for timestamps
   - typing for type hints

## Important Notes

### What's NOT Implemented (By Design)

❌ Database persistence (Future milestone)  
❌ LLM/AI extraction (Future milestone)  
❌ Context Engine (Future milestone)  
❌ Event Engine (Future milestone)  
❌ Notifications (Future milestone)  
❌ Voice support (Future milestone)  

### Version 1 Compatibility

✅ All Version 1 functionality remains unchanged  
✅ No modifications to existing files  
✅ Memory Manager is optional (can be added later to existing flows)  

## Future Milestones

1. **Database Persistence**: Replace MemoryStore with SQLite/PostgreSQL
2. **LLM Integration**: Extract memories from natural language
3. **Context Engine**: Build context from related memories
4. **Event Engine**: React to application events
5. **Advanced Search**: Full-text search, semantic similarity
6. **Voice Support**: Add/retrieve memories via voice

## Integration with Version 1

To integrate memories into Version 1 flows:

```python
from memory import MemoryManager
from parser import parse_command
from executor import execute

# Initialize memory manager
memory_manager = MemoryManager()

# Parse and execute a command
command = input("Enter command: ")
parsed = parse_command(command)

if parsed:
    for cmd in parsed:
        # Optionally: Record the interaction
        memory_manager.add_memory(
            content=f"User executed: {command}",
            category="interaction",
            confidence=1.0
        )
        execute(cmd)
```

## Summary

The Memory Manager v1 provides:
- ✅ Clean, modular architecture
- ✅ Single gateway for memory operations
- ✅ Structured memory model
- ✅ In-memory storage
- ✅ CRUD operations
- ✅ Filtering and search
- ✅ Foundation for future enhancements

It's ready for the next milestone: Database persistence and LLM integration.
