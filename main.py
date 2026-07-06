from parser import parse_command
from executor import execute


def show_help():
    print("""
Available Commands
------------------
open <website>
search <query>

Aliases
-------
launch -> open
start  -> open
find   -> search
google -> search

Examples
--------
open youtube
launch gmail
search python tutorial
find docker compose
""")


def main():
    command = input("Enter command: ").lower().strip()

    # Application commands
    if command == "help":
        show_help()
        return

    if command == "exit":
        print("Goodbye!")
        return

    # Parse user command
    parsed = parse_command(command)

    if parsed:
        for cmd in parsed:
            execute(cmd)
    else:
        print("Invalid command. Type 'help' to see available commands.")


if __name__ == "__main__":
    main()