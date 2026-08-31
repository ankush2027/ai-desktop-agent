from ai.orchestrator import process_natural_language_command
from parser import parse_command
from executor import execute


def route_command(command):
    """Return whether this command is handled by the V1 parser or the AI path."""
    normalized = command.strip().lower()

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
    command = input("Enter command: ").lower().strip()
    handle_command(command)


if __name__ == "__main__":
    main()