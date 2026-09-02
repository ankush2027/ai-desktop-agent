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
        webbrowser.open(SITES[site_name])
        print(f"Opening {site_name}...")
    else:
        print("Site not supported.")


def open_browser(browser_name: str, url: str | None = None):
    browser_name = browser_name.lower()

    if browser_name not in BROWSERS["available"]:
        print("Browser not supported.")
        return

    app_name = BROWSER_APP_NAMES[browser_name]
    command = ["open", "-a", app_name]
    if url:
        command.append(url)

    subprocess.run(command)
    print(f"Opening {app_name}...")