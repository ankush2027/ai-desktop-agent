from actions.folders import open_folder
from config import BROWSERS, SITE_ALIASES, SITES, APPS ,FOLDERS
from actions.browser import open_browser, open_site
from actions.apps import open_app
from actions.local_paths import open_local_target

def open_target(target="", params=None):
    params = params or {}
    normalized = target.lower()
    supported = {"context", "url"} if normalized in BROWSERS["available"] else {"context"}
    if set(params) - supported:
        raise ValueError("Open action contains unsupported parameters.")
    if normalized in SITES or normalized in SITE_ALIASES:
        open_site(normalized)

    elif normalized in APPS:
        open_app(normalized)

    elif normalized in FOLDERS:
        open_folder(normalized)

    elif normalized in BROWSERS["available"]:
        url = params.get("url") if params else None
        open_browser(normalized, url)

    else:
        open_local_target(target)
