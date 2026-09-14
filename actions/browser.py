import os
import platform
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


def _windows_brave_executable():
    """Find stable Brave installations without searching the current directory."""
    for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(variable)
        if root and os.path.isabs(root):
            executable = os.path.join(root, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
            if os.path.isfile(executable):
                return executable
    raise RuntimeError("Brave is not installed in a supported Windows location.")


def open_browser(browser_name: str, url: str | None = None):
    browser_name = browser_name.lower()

    if browser_name not in BROWSERS["available"]:
        raise ValueError("Browser not supported.")

    app_name = BROWSER_APP_NAMES[browser_name]
    system = platform.system()
    if system == "Darwin":
        command = ["open", "-a", app_name]
    elif system == "Windows":
        if browser_name != "brave":
            raise RuntimeError(f"Browser '{browser_name}' is not supported on Windows.")
        command = [_windows_brave_executable()]
    else:
        raise RuntimeError(f"Browser launching is not supported on {system}.")
    if url:
        command.append(url)

    if system == "Windows":
        # A GUI browser can remain running until the user closes it.
        # Process creation confirms launch acceptance, not page loading.
        try:
            subprocess.Popen(command)
        except OSError as exc:
            raise RuntimeError("Windows could not launch Brave.") from exc
    else:
        subprocess.run(command, check=True)
    print(f"Browser launch request accepted by {app_name}; page loading is not verified.")
