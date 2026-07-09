from config import FILLER_WORDS

ACTION_ALIASES = {
    "launch": "open",
    "start": "open",
    "open": "open",
    "find": "search",
    "google": "search",
    "search": "search",
    "list": "list",
    "help": "help",
    "make":"create",
    "create":"create",
    "new":"create"
}

SPECIAL_COMMANDS = {"help", "exit"}

def parse_command(command):
    command = command.lower().strip()
    

    words = command.split()

    filtered_words = []
    
    for word in words:
        if word not in FILLER_WORDS:
            filtered_words.append(word)

    command = " ".join(filtered_words)

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

        if not action:
            return None

        params = {}
        target = " ".join(words[1:])

        if action == "create":
            if len(words) < 3:
                return None

            item_type = words[1]

            if item_type not in ["file", "folder"]:
                return None

            target = " ".join(words[2:])
            params["type"] = item_type

        commands.append({
            "action": action,
            "target": target,
            "params": params
        })
    return commands