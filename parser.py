from config import ACTION_ALIASES

SPECIAL_COMMANDS = {"help", "exit"}
FILE_ACTIONS = {"create", "delete", "rename", "copy", "move"}


def is_file_command(command):
    """Recognize explicit file syntax even when its arguments are invalid."""
    words = command.split(maxsplit=2)
    return bool(
        words and ACTION_ALIASES.get(words[0].lower()) in FILE_ACTIONS
        and (len(words) == 1 or words[1].lower() in {"file", "folder"})
    )


def _tokens(command):
    """Return argument spans without shell escaping or backslash conversion.

    Quotes delimit a whole operand; embedded apostrophes remain literal text.
    Outside quotes, the standalone word 'and' is the command separator.
    """
    tokens = []
    index = 0
    while index < len(command):
        if command[index].isspace():
            index += 1
            continue
        start = index
        quoted = command[index] in "\"'"
        if quoted:
            quote = command[index]
            end = command.find(quote, index + 1)
            if end == -1 or (end + 1 < len(command) and not command[end + 1].isspace()):
                return None
            value = command[index + 1:end]
            index = end + 1
        else:
            while index < len(command) and not command[index].isspace():
                if command[index] == '"':
                    return None
                index += 1
            value = command[start:index]
        tokens.append((value, start, index, quoted))
    return tokens


def _parse_part(command, tokens):
    if not tokens or tokens[0][3]:
        return None
    word = tokens[0][0].lower()
    if word in SPECIAL_COMMANDS:
        return {"action": word, "target": "", "params": {}} if len(tokens) == 1 else None
    action = ACTION_ALIASES.get(word)
    if action is None:
        return None

    operands = tokens[1:]
    params = {}
    if action in FILE_ACTIONS:
        if not operands or operands[0][3] or operands[0][0].lower() not in {"file", "folder"}:
            return None
        params["type"] = operands[0][0].lower()
        operands = operands[1:]
    if not operands or any(not token[0] for token in operands):
        return None

    if action in {"rename", "copy", "move"}:
        # Never guess a split within an unquoted multiword filename.
        if len(operands) != 2:
            return None
        target, destination = (token[0] for token in operands)
        params["new_name" if action == "rename" else "destination"] = destination
    elif any(token[3] for token in operands):
        if len(operands) != 1:
            return None
        target = operands[0][0]
    else:
        # Preserve internal whitespace instead of joining normalized words.
        target = command[operands[0][1]:operands[-1][2]]
    return {"action": action, "target": target, "params": params}


def parse_command(command):
    """Preserve V1 operands exactly; return None on invalid/ambiguous syntax.

    Surrounding unquoted whitespace separates syntax. Whole-operand single or
    double quotes represent two-operand names containing spaces, literal 'and',
    or leading/trailing spaces. Backslashes are literal, never escapes.
    """
    if any(character in command for character in "\r\n\x00"):
        return None
    tokens = _tokens(command)
    if not tokens:
        return None
    parts = [[]]
    for token in tokens:
        if token[0].lower() == "and" and not token[3]:
            parts.append([])
        else:
            parts[-1].append(token)
    actions = [_parse_part(command, part) for part in parts]
    return actions if all(action is not None for action in actions) else None
