from config import SITES, APPS

def list_items(target):
    if target == "sites":
        for site in SITES:
            print(site)
        return None
    return
    for app in APPS:
        print(app)
    return None