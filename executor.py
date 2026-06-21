from actions.browser import open_site

def execute(command):
    if command["action"] == "open":
        open_site(command["target"])