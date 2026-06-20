from parser import parse_command
from actions.browser import open_site


def main():
    command = input("Enter command: ")

    parsed = parse_command(command)

    if parsed is not None:
        if parsed["action"] == "open":
            open_site(parsed["target"])
    else:
        print("Invalid command")

if __name__ == "__main__":
    main()