import subprocess
import webbrowser

from config import BROWSERS, SITE_ALIASES, SITES


BROWSER_APP_NAMES = {
    "brave": "Brave Browser",
    "safari": "Safari",
}


def open_site(site_name: str):
    site_name = site_name.lower()

    site_name = SITE_ALIASES.get(site_name, site_name)

    if site_name in SITES:
        if not webbrowser.open(SITES[site_name]):
            raise RuntimeError("Browser did not accept the site launch request.")
        print(f"Opening {site_name}...")
    else:
        print("Site not supported.")


def open_browser(browser_name: str, url: str | None = None):
    browser_name = browser_name.lower()

    if browser_name not in BROWSERS["available"]:
        raise ValueError("Browser not supported.")

    app_name = BROWSER_APP_NAMES[browser_name]
    command = ["open", "-a", app_name]
    if url:
        command.append(url)

    subprocess.run(command, check=True)
    print(f"Browser launch request accepted by {app_name}; page loading is not verified.")
