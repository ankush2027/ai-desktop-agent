def parse_command(command):
    command = command.lower().strip()

    if not command:
        return None

    parts = command.split()

    if len(parts) < 2:
        return None

    action = parts[0]
    target = " ".join(parts[1:])

    if action in ["open", "search"]:
        return {
            "action": action,
            "target": target,
            "params": {}
        }

    return None