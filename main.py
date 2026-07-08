from parser import parse_command
from executor import execute

def main():
    command = input("Enter command: ").lower().strip()

    parsed = parse_command(command)

    if parsed:
        for cmd in parsed:
            execute(cmd)
    else:
        print("Invalid command. Type 'help' to see available commands.")


if __name__ == "__main__":
    main()