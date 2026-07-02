ACTION_ALIASES = {
    "launch": "open",
    "start": "open",
    "open": "open",
    "find": "search",
    "google": "search",
    "search": "search"
    }


def parse_command(command):
    command = command.lower().strip()

    if not command:
        return None

    parts = command.split()

    if len(parts) < 2:
        return None

    action = ACTION_ALIASES.get(parts[0])
    target = " ".join(parts[1:])
    
    
    if action:
        return {
            "action": action,
            "target": target,
            "params": {}
        }

    return None