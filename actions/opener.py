from actions.folders import open_folder
from config import SITE_ALIASES, SITES, APPS ,FOLDERS
from actions.browser import open_site
from actions.apps import open_app

def open_target(target):
    if target in SITES or target in SITE_ALIASES:
        open_site(target)
    elif target in APPS:
        open_app(target)
    elif target in FOLDERS:
        open_folder(target)
    else:
        print(f"'{target}' is not a supported website or application.")