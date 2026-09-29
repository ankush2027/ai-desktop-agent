"""Bounded desktop operations; AI plans still enter through ActionPolicy.

Adapters accept capability names, never commands or executable paths. Installation
roots are trusted process environment, as with the original Brave discovery.
"""

import os
import platform
import subprocess
import webbrowser
from urllib.parse import urlsplit

from config import APPS, BROWSERS


class DesktopUnavailable(RuntimeError):
    """A safe, user-facing capability or installation failure."""


def validate_browser_url(url):
    if url is None:
        return
    if not isinstance(url, str) or not url or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ValueError("Browser URL is not supported.")
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError
        parsed.port  # Reject malformed ports before invoking any OS operation.
    except ValueError:
        raise ValueError("Browser URL is not supported.") from None


def _installed(candidates, label):
    for variable, parts in candidates:
        root = os.environ.get(variable)
        if root and os.path.isabs(root):
            executable = os.path.join(root, *parts)
            if os.path.isfile(executable):
                return executable
    raise DesktopUnavailable(f"{label} is not installed in a supported Windows location.")


class WindowsAdapter:
    name = "Windows"
    browsers = {"brave": "Brave Browser"}
    apps = {
        "calculator": (("SystemRoot", ("System32", "calc.exe")),),
        "vscode": (
            ("LOCALAPPDATA", ("Programs", "Microsoft VS Code", "Code.exe")),
            ("PROGRAMFILES", ("Microsoft VS Code", "Code.exe")),
            ("PROGRAMFILES(X86)", ("Microsoft VS Code", "Code.exe")),
        ),
        "whatsapp": (("LOCALAPPDATA", ("WhatsApp", "WhatsApp.exe")),),
        "telegram": (
            ("APPDATA", ("Telegram Desktop", "Telegram.exe")),
            ("PROGRAMFILES", ("Telegram Desktop", "Telegram.exe")),
        ),
    }

    def require_browser(self, name):
        if name not in BROWSERS["available"]:
            raise ValueError("Browser not supported.")
        if name not in self.browsers:
            raise DesktopUnavailable("Browser is not supported on Windows. Supported browser: Brave.")

    def require_app(self, name):
        if name not in APPS or name not in self.apps:
            raise DesktopUnavailable("Application is not supported on Windows.")

    @staticmethod
    def _brave():
        return _installed(tuple(
            (root, ("BraveSoftware", "Brave-Browser", "Application", "brave.exe"))
            for root in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
        ), "Brave")

    @staticmethod
    def _launch(command):
        try:
            subprocess.Popen(command)
        except OSError:
            raise DesktopUnavailable("Windows could not launch the requested application.") from None

    def open_app(self, name):
        self.require_app(name)
        self._launch([_installed(self.apps[name], "Requested application")])

    def open_browser(self, name, url=None):
        self.require_browser(name)
        validate_browser_url(url)
        self._launch([self._brave()] + ([url] if url else []))

    def open_local(self, target):
        from actions.local_paths import resolve_local_target, TEXT_SUFFIXES

        path = resolve_local_target(target)
        if path.is_dir():
            reader = _installed((("SystemRoot", ("explorer.exe",)),), "Explorer")
            argument = str(path)
        elif path.suffix.lower() in TEXT_SUFFIXES:
            reader = _installed((("SystemRoot", ("System32", "notepad.exe")),), "Notepad")
            argument = str(path)
        else:
            reader = self._brave()  # Fixed reader, never file associations.
            argument = path.as_uri()
        self._launch([reader, argument])


class MacOSAdapter:
    name = "Darwin"
    browsers = {"brave": "Brave Browser", "safari": "Safari"}
    apps = {
        "calculator": "Calculator",
        "vscode": "Visual Studio Code",
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
    }

    def require_browser(self, name):
        if name not in BROWSERS["available"] or name not in self.browsers:
            raise ValueError("Browser not supported.")

    def require_app(self, name):
        if name not in APPS or name not in self.apps:
            raise DesktopUnavailable("Application is not supported on macOS.")

    def require_close_app(self, name):
        if name in BROWSERS["available"]:
            self.require_browser(name)
        else:
            self.require_app(name)

    def close_app(self, name):
        self.require_close_app(name)
        application = self.browsers[name] if name in BROWSERS["available"] else self.apps[name]
        # Only adapter-owned names enter this fixed AppleScript. Checking running
        # first avoids launching an application merely to quit it.
        script = f'if application "{application}" is running then tell application "{application}" to quit'
        try:
            subprocess.run(["/usr/bin/osascript", "-e", script], check=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise DesktopUnavailable("macOS could not complete the application quit request.") from None

    def open_app(self, name):
        self.require_app(name)
        subprocess.run(["/usr/bin/open", "-a", self.apps[name]], check=True)

    def open_browser(self, name, url=None):
        self.require_browser(name)
        validate_browser_url(url)
        subprocess.run(["/usr/bin/open", "-a", self.browsers[name]] + ([url] if url else []), check=True)

    def open_local(self, target):
        from actions.local_paths import resolve_local_target, TEXT_SUFFIXES

        path = resolve_local_target(target)
        command = ["/usr/bin/open"]
        if not path.is_dir():
            command += ["-a", "TextEdit" if path.suffix.lower() in TEXT_SUFFIXES else "Preview"]
        subprocess.run(command + [str(path)], check=True)


def get_platform():
    system = platform.system()
    if system == "Windows":
        return WindowsAdapter()
    if system == "Darwin":
        return MacOSAdapter()
    raise DesktopUnavailable("Desktop actions are not supported on this platform. Supported platforms: Windows, macOS.")


def open_default_url(url):
    get_platform()
    validate_browser_url(url)
    if not webbrowser.open(url):
        raise DesktopUnavailable("Browser did not accept the launch request.")
