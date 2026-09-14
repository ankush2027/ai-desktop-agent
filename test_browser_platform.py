"""Platform boundary tests; all process launches and install checks are mocked."""

# Direct script runs must enter pytest before importing application singletons.
if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


import os
import subprocess
from unittest.mock import patch

import pytest

from actions.browser import open_browser
from actions.opener import open_target


@pytest.fixture(autouse=True)
def processes():
    with patch("actions.browser.subprocess.run") as run, \
         patch("actions.browser.subprocess.Popen") as popen:
        yield run, popen


@pytest.mark.parametrize("browser,app", [("brave", "Brave Browser"), ("safari", "Safari")])
@pytest.mark.parametrize("url", [None, "https://www.youtube.com/results?search_query=C%2B%2B"])
def test_macos_command_unchanged(browser, app, url, processes):
    run, popen = processes
    with patch("actions.browser.platform.system", return_value="Darwin"):
        open_browser(browser, url)
    run.assert_called_once_with(["open", "-a", app] + ([url] if url else []), check=True)
    popen.assert_not_called()


@pytest.mark.parametrize("variable", ["LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"])
@pytest.mark.parametrize("url", [None, "https://www.youtube.com/results?search_query=C%2B%2B"])
def test_windows_brave_standard_locations(variable, url, processes):
    run, popen = processes
    root = os.path.abspath("Mock Installation With Spaces")
    executable = os.path.join(root, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
    with patch("actions.browser.platform.system", return_value="Windows"), \
         patch.dict(os.environ, {variable: root}, clear=True), \
         patch("actions.browser.os.path.isfile", side_effect=lambda path: path == executable):
        open_target("brave", {"url": url} if url else {})
    popen.assert_called_once_with([executable] + ([url] if url else []))
    popen.return_value.wait.assert_not_called()
    run.assert_not_called()


def test_windows_prefers_user_install(processes):
    root = os.path.abspath("User Install")
    with patch("actions.browser.platform.system", return_value="Windows"), \
         patch.dict(os.environ, {"LOCALAPPDATA": root, "PROGRAMFILES": os.path.abspath("System Install")}, clear=True), \
         patch("actions.browser.os.path.isfile", return_value=True):
        open_browser("BRAVE")
    assert processes[1].call_args.args[0][0].startswith(root + os.sep)


@pytest.mark.parametrize("environment", [{}, {"LOCALAPPDATA": "relative-path"}, {"PROGRAMFILES": os.path.abspath("Missing")}])
def test_missing_brave_has_no_fallback(environment, processes):
    with patch("actions.browser.platform.system", return_value="Windows"), \
         patch.dict(os.environ, environment, clear=True), \
         patch("actions.browser.os.path.isfile", return_value=False), \
         patch("actions.browser.webbrowser.open") as fallback:
        with pytest.raises(RuntimeError, match="not installed"):
            open_browser("brave")
    fallback.assert_not_called()
    for process in processes:
        process.assert_not_called()


@pytest.mark.parametrize("system,browser,message", [
    ("Windows", "safari", "not supported on Windows"),
    ("Linux", "brave", "not supported on Linux"),
    ("Windows", "chrome", "Browser not supported"),
])
def test_unsupported_combinations_fail_before_launch(system, browser, message, processes):
    with patch("actions.browser.platform.system", return_value=system):
        with pytest.raises((RuntimeError, ValueError), match=message):
            open_browser(browser)
    for process in processes:
        process.assert_not_called()


def test_windows_spawn_failure_is_reported(processes, capsys):
    processes[1].side_effect = PermissionError("denied")
    with patch("actions.browser.platform.system", return_value="Windows"), \
         patch("actions.browser._windows_brave_executable", return_value="mock-brave.exe"):
        with pytest.raises(RuntimeError, match="Windows could not launch Brave"):
            open_browser("brave")
    assert "accepted" not in capsys.readouterr().out


def test_macos_failure_still_propagates(processes, capsys):
    processes[0].side_effect = subprocess.CalledProcessError(1, ["open"])
    with patch("actions.browser.platform.system", return_value="Darwin"):
        with pytest.raises(subprocess.CalledProcessError):
            open_browser("brave")
    assert "accepted" not in capsys.readouterr().out
