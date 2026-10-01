"""Bounded workspace data validation; this module performs no OS operations."""

import re
from urllib.parse import urlsplit

from config import APPS, BROWSERS, SITES, WORKSPACE_URLS
from actions.platforms import get_platform, validate_browser_url
from ai.plan_schema import MAX_ACTIONS

CODING_APPS = ("vscode", "brave")


def workspace_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", value.lower()):
        raise ValueError("Workspace names must be 1-32 letters, digits, underscores or hyphens, starting with a letter.")
    return value.lower()


def workspace_app(value):
    if not isinstance(value, str):
        raise ValueError("Workspace application is not supported.")
    name = value.lower()
    adapter = get_platform()
    if adapter.name != "Darwin":
        raise ValueError("Workspaces are supported only on macOS.")
    if name in BROWSERS["available"]:
        adapter.require_browser(name)
    elif name in APPS:
        adapter.require_app(name)
    else:
        raise ValueError("Workspace application is not supported.")
    return name


def configured_workspace_urls():
    return set(SITES.values()) | set(WORKSPACE_URLS.values())


def workspace_url(value):
    # Exact configured destinations only, never generated arbitrary navigation.
    if not isinstance(value, str) or value not in configured_workspace_urls():
        raise ValueError("Workspace URL must be an explicitly configured destination.")
    validate_browser_url(value)
    parsed = urlsplit(value)
    if parsed.query or parsed.fragment or any(c in value for c in ';&|`$'):
        raise ValueError("Workspace URL must be a configured site home destination.")
    return value


def validate_workspace(definition):
    if not isinstance(definition, dict) or set(definition) not in ({"name", "apps"}, {"name", "apps", "urls"}):
        raise ValueError("Stored workspace is invalid.")
    name = workspace_name(definition["name"])
    apps, urls = definition["apps"], definition.get("urls", [])
    # Preserve the exact legacy coding record without interpreting edited legacy
    # data as a newly configured workspace. New records always include urls.
    if "urls" not in definition and (name != "coding" or apps != list(CODING_APPS)):
        raise ValueError("Legacy coding workspace is invalid.")
    if (not isinstance(apps, list) or not isinstance(urls, list)
            or not 1 <= len(apps) + len(urls) <= MAX_ACTIONS):
        raise ValueError("Workspace must contain between 1 and 10 items.")
    apps = [workspace_app(app) for app in apps]
    urls = [workspace_url(url) for url in urls]
    if len(set(apps)) != len(apps) or len(set(urls)) != len(urls):
        raise ValueError("Workspace items must not be duplicated.")
    result = {"name": name, "apps": apps}
    if "urls" in definition:
        result["urls"] = urls
    return result


def workspace_open_actions(definition):
    definition = validate_workspace(definition)
    actions = [{"action": "open", "target": app, "params": {}} for app in definition["apps"]]
    urls = definition.get("urls", [])
    if urls:
        # Use the first saved browser, or the configured default when none is
        # listed. Its capability is subsequently checked by ActionPolicy.
        browser = next((app for app in definition["apps"] if app in BROWSERS["available"]), BROWSERS["preferred"])
        actions.extend({"action": "open", "target": browser, "params": {"url": url}} for url in urls)
    return actions
