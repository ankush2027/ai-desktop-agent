from actions.list_items import list_items
from logger import log_action
from actions.opener import open_target
from actions.search import search_google

ACTION_MAP = {
    "open": open_target,
    "search": search_google,
    "list":list_items
}
def execute(command):
    action = command.get("action")
    target = command.get("target")

    handler = ACTION_MAP.get(action)

    if handler:
        log_action(action,target)
        handler(target)
    else:
        print(f"Unsupported action : {action}")