from actions.browser import open_site


ACTION_MAP = {
    "open": open_site
}


def execute(command):
    action = command.get("action")
    target = command.get("target")

    handler = ACTION_MAP.get(action)

    if handler:
        handler(target)
    else:
        print("Unsupported action")