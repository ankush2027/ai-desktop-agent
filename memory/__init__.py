"""
Memory Manager Module for Personal AI OS v2

This module implements the Memory Foundation architecture, providing:
- Memory Model: Data structure for storing memory items
- Memory Store: In-memory persistence layer (to be replaced with database)
- Memory Manager: Single gateway for all memory operations

Architecture Flow:
    User/AI Brain → Memory Manager → Memory Store → Persistent Storage (future)
"""

from memory.models import Memory
from memory.store import MemoryStore
from memory.manager import MemoryManager

__all__ = ['Memory', 'MemoryStore', 'MemoryManager']
