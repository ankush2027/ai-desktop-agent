import os
import subprocess
from actions.folders import open_folder
from config import BROWSERS, SITE_ALIASES, SITES, APPS ,FOLDERS
from actions.browser import open_browser, open_site
from actions.apps import open_app

def open_target(target="", params=None):
    if target in SITES or target in SITE_ALIASES:
        open_site(target)

    elif target in APPS:
        open_app(target)

    elif target in FOLDERS:
        open_folder(target)

    elif target in BROWSERS["available"]:
        url = params.get("url") if params else None
        open_browser(target, url)

    elif os.path.exists(target):
        subprocess.run(["open", target])

    else:
        print(f"'{target}' is not a supported website, folder, application or file.")