from config import SITES, APPS

def list_items(target="",params=None):
    if target == "sites":
        print("Available sites:")
        for site in SITES:
            print(f"- {site}")
    elif target == "apps":
        print("Available apps:")
        for app in APPS:
            print(f"- {app}")
    else:
        print(f"Unsupported target: {target}")
