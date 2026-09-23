from config import SITE_ALIASES, SITES
from actions.platforms import get_platform, open_default_url


def open_site(site_name: str):
    site_name = SITE_ALIASES.get(site_name.lower(), site_name.lower())
    if site_name not in SITES:
        raise ValueError("Site not supported.")
    open_default_url(SITES[site_name])
    print(f"Opening {site_name}...")


def open_browser(browser_name: str, url: str | None = None):
    get_platform().open_browser(browser_name.lower(), url)
    print("Browser launch request accepted; page loading is not verified.")
