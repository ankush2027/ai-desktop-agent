from actions.browser import open_site
from actions.search import search_google

ACTION_MAP = {
    "open": open_site,
    "search": search_google
}


def execute(command):
    action = command.get("action")
    target = command.get("target")

    handler = ACTION_MAP.get(action)

    if handler:
        handler(target)
    else:
        print("Unsupported action")