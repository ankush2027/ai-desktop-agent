from actions.browser import open_site


def main():
    command = input("Enter command: ").lower().strip()

    if not command:
        print("Empty command")
        return

    parts = command.split()
    
    if parts[0] == "open":
        if len(parts) > 1:
            open_site(parts[1])
        else:
            print("Please specify what to open (e.g., 'open youtube').")
    else:
        print("Command not recognized.")


if __name__ == "__main__":
    main()