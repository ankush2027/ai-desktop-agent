from config import SITES, APPS, FOLDERS

def list_items(target="", params=None):
    if set(params or {}) - {"context"}:
        raise ValueError("List action contains unsupported parameters.")
    target = target.lower()
    if target == "sites":
        print("Available sites:")
        for site in SITES:
            print(f"- {site}")

    elif target == "apps":
        print("Available apps:")
        for app in APPS:
            print(f"- {app}")

    elif target == "folders":
        print("Available folders:")
        for folder in FOLDERS:
            print(f"- {folder}")

    else:
        raise ValueError("List target is not supported.")
