from actions.config import SITES,APPS
from actions.browser import open_site
from actions.apps import open_app

def open_target(target):
    if target in SITES:
        open_site(target)
    elif target in APPS:
        open_app(target)
    else:
        print(f"'{target}' is not a supported website or application.")