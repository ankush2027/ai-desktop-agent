"""Tests for open-action target resolution."""

from unittest.mock import patch

from actions.opener import open_target
from actions.search import search_google


def test_brave_with_url_opens_url_in_brave():
    with patch("actions.browser.subprocess.run") as run:
        open_target("brave", {"url": "https://www.youtube.com/results?search_query=python"})

    run.assert_called_once_with(
        ["open", "-a", "Brave Browser", "https://www.youtube.com/results?search_query=python"], check=True
    )


def test_safari_with_url_opens_url_in_safari():
    with patch("actions.browser.subprocess.run") as run:
        open_target("safari", {"url": "https://www.youtube.com"})

    run.assert_called_once_with(["open", "-a", "Safari", "https://www.youtube.com"], check=True)


def test_browser_without_url_launches_browser():
    with patch("actions.browser.subprocess.run") as run:
        open_target("brave", {})

    run.assert_called_once_with(["open", "-a", "Brave Browser"], check=True)


def test_existing_site_opening_behavior_is_preserved():
    with patch("actions.opener.open_site") as open_site:
        open_target("yt", {})

    open_site.assert_called_once_with("yt")


def test_configured_sites_open_through_browser_capability():
    with patch("actions.opener.open_site") as open_site:
        open_target("gmail", {})
        open_target("github", {})

    assert [call.args for call in open_site.call_args_list] == [
        ("gmail",),
        ("github",),
    ]


def test_search_uses_safe_target_without_shell_execution():
    with patch("actions.search.webbrowser.open") as open_browser:
        search_google("Mphasis interview questions")

    open_browser.assert_called_once_with(
        "https://www.google.com/search?q=Mphasis+interview+questions"
    )


def test_existing_app_opening_behavior_is_preserved():
    with patch("actions.opener.open_app") as open_app:
        open_target("calculator", {})

    open_app.assert_called_once_with("calculator")


if __name__ == "__main__":
    test_brave_with_url_opens_url_in_brave()
    test_safari_with_url_opens_url_in_safari()
    test_browser_without_url_launches_browser()
    test_existing_site_opening_behavior_is_preserved()
    test_configured_sites_open_through_browser_capability()
    test_search_uses_safe_target_without_shell_execution()
    test_existing_app_opening_behavior_is_preserved()
    print("Open action tests passed.")
