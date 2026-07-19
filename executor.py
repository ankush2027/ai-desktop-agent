from actions.delete import delete
from actions.copy import copy
from actions.create import create
from actions.rename import rename
from actions.exit import exit_program
from actions.help import show_help
from actions.list_items import list_items
from logger import log_action
from actions.opener import open_target
from actions.search import search_google

ACTION_MAP = {
    "open": open_target,
    "search": search_google,
    "list": list_items,
    "help": show_help,
    "exit": exit_program,
    "create": create,
    "delete":delete,
    "rename":rename,
    "copy":copy
}

def execute(command):
    action = command.get("action")
    target = command.get("target")
    params = command.get("params", {})

    handler = ACTION_MAP.get(action)

    if handler:
        log_action(action, target)
        handler(target, params)
    else:
        print(f"Unsupported action: {action}")