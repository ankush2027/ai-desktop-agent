import re

from ai.orchestrator import process_natural_language_command
from parser import parse_command
from executor import execute
from memory import MemoryManager


REMEMBER_PATTERN = re.compile(r"^remember(?:\s+that)?\s+(.+?)\s*[.!?]?$", re.IGNORECASE)
MEMORY_QUERY_PATTERN = re.compile(
    r"^what do you remember(?:\s+about\s+(.+?))?\s*[.!?]?$",
    re.IGNORECASE,
)
REMEMBER_QUERY_PATTERN = re.compile(
    r"^do you remember(?:\s+that\s+(.+?))?\s*[.!?]?$",
    re.IGNORECASE,
)
PREFERENCES_QUERY_PATTERN = re.compile(r"^what are my preferences\s*[.!?]?$", re.IGNORECASE)


def parse_remember_command(command):
    """Return a memory action for an explicit remember command."""
    match = REMEMBER_PATTERN.match(command.strip())
    if not match:
        return None

    content = match.group(1).strip()
    if not content:
        return None

    return {
        "action": "remember",
        "target": content,
        "params": {},
    }


def parse_memory_query(command):
    """Return a deterministic memory retrieval request, if recognized."""
    normalized = command.strip()

    if PREFERENCES_QUERY_PATTERN.match(normalized):
        return {"action": "retrieve", "query": None, "category": "user_preference"}

    for pattern in (MEMORY_QUERY_PATTERN, REMEMBER_QUERY_PATTERN):
        match = pattern.match(normalized)
        if match:
            query = match.group(1)
            if query and query.strip().lower() == "me":
                query = None
            return {
                "action": "retrieve",
                "query": query.strip() if query else None,
                "category": None,
            }

    return None


def _unique_memories(memories):
    """Keep one entry for each equivalent persisted memory."""
    unique_memories = []
    seen = set()
    for memory in memories:
        key = (memory.category, memory.content)
        if key not in seen:
            seen.add(key)
            unique_memories.append(memory)
    return unique_memories


def route_command(command):
    """Return whether this command is handled by the V1 parser or the AI path."""
    normalized = command.strip().lower()

    remembered = parse_remember_command(command)
    if remembered:
        return "memory", [remembered]

    memory_query = parse_memory_query(command)
    if memory_query:
        return "memory_retrieval", [memory_query]

    natural_language_markers = (
        "please",
        "can you",
        "could you",
        "would you",
        "help me",
        "make me",
        "kindly",
    )
    if any(marker in normalized for marker in natural_language_markers):
        return "ai", None

    parsed = parse_command(command)
    if not parsed:
        return "ai", None

    if len(parsed) == 1:
        return "v1", parsed

    multi_action_parts = [part.strip() for part in normalized.split(" and ") if part.strip()]
    if not multi_action_parts:
        return "ai", None

    if all(
        (" file " in part or " folder " in part or part in {"help", "exit"})
        for part in multi_action_parts
    ):
        return "v1", parsed

    return "ai", None


def handle_command(command):
    route, parsed = route_command(command)

    if route == "memory":
        memory = parsed[0]
        memory_manager = MemoryManager()
        memory_manager.add_memory(
            content=memory["target"],
            category="user_preference",
            confidence=1.0,
        )
        print(f"Remembered: {memory['target']}")
        return parsed

    if route == "memory_retrieval":
        request = parsed[0]
        memory_manager = MemoryManager()
        if request["category"]:
            memories = memory_manager.get_memories_by_category(request["category"])
        elif request["query"]:
            memories = memory_manager.search_memories(request["query"])
        else:
            memories = memory_manager.get_all_memories()
        memories = _unique_memories(memories)

        if memories:
            for memory in memories:
                print(f"I remember: {memory.content}.")
        elif request["query"]:
            print(f"I don't remember anything about {request['query']}.")
        elif request["category"]:
            print("I don't have any stored preferences.")
        else:
            print("I don't have any stored memories.")
        return parsed

    if route == "v1":
        for cmd in parsed:
            execute(cmd)
        return parsed

    try:
        return process_natural_language_command(command)
    except ValueError as exc:
        print(f"Invalid command: {exc}")
        print("Invalid command. Type 'help' to see available commands.")
        return []


def main():
    command = input("Enter command: ").strip()
    handle_command(command)


if __name__ == "__main__":
    main()