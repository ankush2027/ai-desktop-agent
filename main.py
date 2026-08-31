from ai.orchestrator import process_natural_language_command
from parser import parse_command
from executor import execute


def main():
    command = input("Enter command: ").lower().strip()

    parsed = parse_command(command)

    if parsed:
        for cmd in parsed:
            execute(cmd)
        return

    try:
        process_natural_language_command(command)
    except ValueError as exc:
        print(f"Invalid command: {exc}")
        print("Invalid command. Type 'help' to see available commands.")


if __name__ == "__main__":
    main()