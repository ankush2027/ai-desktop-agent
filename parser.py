def parse_command(command):
    command = command.lower().strip()

    if not command:
        return None

    parts = command.split()

    if parts[0] == "open":
        if len(parts) == 2:
            return {
                "action": "open",
                "target": parts[1]
            }

    return None