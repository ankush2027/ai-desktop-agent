import webbrowser
from config import SITE_ALIASES, SITES


def open_site(site_name: str):
    site_name = site_name.lower()

    site_name = SITE_ALIASES.get(site_name, site_name)

    if site_name in SITES:
        webbrowser.open(SITES[site_name])
        print(f"Opening {site_name}...")
    else:
        print("Site not supported.")