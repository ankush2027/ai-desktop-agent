from parser import parse_command
from executor import execute


def main():
    command = input("Enter command: ")

    parsed = parse_command(command)

    if parsed:
        execute(parsed)
    else:
        print("Invalid command")


if __name__ == "__main__":
    main()