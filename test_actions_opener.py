"""Tests for open-action target resolution."""

from unittest.mock import patch

from actions.opener import open_target


def test_brave_with_url_opens_url_in_brave():
    with patch("actions.browser.subprocess.run") as run:
        open_target("brave", {"url": "https://www.youtube.com/results?search_query=python"})

    run.assert_called_once_with(
        ["open", "-a", "Brave Browser", "https://www.youtube.com/results?search_query=python"]
    )


def test_safari_with_url_opens_url_in_safari():
    with patch("actions.browser.subprocess.run") as run:
        open_target("safari", {"url": "https://www.youtube.com"})

    run.assert_called_once_with(["open", "-a", "Safari", "https://www.youtube.com"])


def test_browser_without_url_launches_browser():
    with patch("actions.browser.subprocess.run") as run:
        open_target("brave", {})

    run.assert_called_once_with(["open", "-a", "Brave Browser"])


def test_existing_site_opening_behavior_is_preserved():
    with patch("actions.opener.open_site") as open_site:
        open_target("yt", {})

    open_site.assert_called_once_with("yt")


def test_existing_app_opening_behavior_is_preserved():
    with patch("actions.opener.open_app") as open_app:
        open_target("calculator", {})

    open_app.assert_called_once_with("calculator")


if __name__ == "__main__":
    test_brave_with_url_opens_url_in_brave()
    test_safari_with_url_opens_url_in_safari()
    test_browser_without_url_launches_browser()
    test_existing_site_opening_behavior_is_preserved()
    test_existing_app_opening_behavior_is_preserved()
    print("Open action tests passed.")
