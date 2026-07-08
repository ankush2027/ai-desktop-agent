ACTION_ALIASES = {
    "launch": "open",
    "start": "open",
    "open": "open",
    "find": "search",
    "google": "search",
    "search": "search",
    "list": "list",
    "help": "help"
}

SPECIAL_COMMANDS = {"help", "exit"}


def parse_command(command):
    command = command.lower().strip()

    if not command:
        return None

    commands = []

    parts = command.split(" and ")

    for part in parts:
        words = part.split()

        if words[0] in SPECIAL_COMMANDS:
            commands.append({
                "action": words[0],
                "target": "",
                "params": {}
            })
            continue

        if len(words) < 2:
            return None

        action = ACTION_ALIASES.get(words[0])
        target = " ".join(words[1:])

        if not action:
            return None

        commands.append({
            "action": action,
            "target": target,
            "params": {}
        })

    return commands