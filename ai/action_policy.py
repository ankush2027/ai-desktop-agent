import re
from typing import Any, Dict, List
from urllib.parse import urlsplit

from config import APPS, BROWSERS, FOLDERS, SITE_ALIASES, SITES
from ai.errors import AIPlanningError
from ai.plan_schema import ALLOWED_ACTIONS, validate_plan
from actions.email import compose_url
from actions.local_paths import resolve_local_target
from actions.platforms import get_platform


class ActionPolicyError(AIPlanningError):
    """Raised when an AI action plan violates the execution safety policy."""


class ActionPolicy:
    """Validate the entire plan and return the exact targets to execute."""

    ALLOWED_ACTIONS = ALLOWED_ACTIONS
    _UNSAFE_TARGET = re.compile(r"[\x00-\x1f\x7f;&|`$]")

    @staticmethod
    def _platform():
        try:
            return get_platform()
        except RuntimeError as exc:
            raise ActionPolicyError(str(exc)) from None

    @staticmethod
    def _browser_platform(browser):
        try:
            ActionPolicy._platform().require_browser(browser)
        except (RuntimeError, ValueError) as exc:
            raise ActionPolicyError(str(exc)) from None

    @staticmethod
    def _site_url(url):
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
                raise ValueError
            # URLs are only navigation to configured home destinations. Workflow
            # queries/content must go through search or draft_email instead.
            for configured in SITES.values():
                site = urlsplit(configured)
                if (parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/")) == (
                    site.scheme, site.netloc.lower(), site.path.rstrip("/"),
                ):
                    return
        except ValueError:
            pass
        raise ActionPolicyError("AI open URL must be a configured site home destination.")

    def validate(self, actions: List[Dict[str, Any]], *, preferred_browser=None) -> List[Dict[str, Any]]:
        try:
            validated = validate_plan({"actions": actions})["actions"]
        except AIPlanningError:
            raise ActionPolicyError("AI action schema is not supported.") from None
        preferred = preferred_browser or BROWSERS["preferred"]
        for item in validated:
            action, target, params = item["action"], item["target"], item["params"]
            if action == "draft_email":
                try:
                    compose_url(target, params)
                except ValueError as exc:
                    raise ActionPolicyError(str(exc)) from None
                self._browser_platform(preferred)
                continue
            if self._UNSAFE_TARGET.search(target) or any(self._UNSAFE_TARGET.search(value) for value in params.values()):
                raise ActionPolicyError("AI action contains unsafe characters.")
            allowed = {"open": {"url"}, "search": {"engine", "query"}, "list": set(), "help": set()}[action]
            if set(params) - allowed:
                raise ActionPolicyError("AI action contains unsupported parameters.")
            if action == "open":
                normalized = target.lower()
                if normalized in BROWSERS["available"]:
                    self._browser_platform(normalized)
                    if "url" in params:
                        self._site_url(params["url"])
                    item["target"] = normalized
                else:
                    if params:
                        raise ActionPolicyError("Only browser targets accept an open URL.")
                    if normalized in SITES or normalized in SITE_ALIASES:
                        self._platform()
                        site = SITE_ALIASES.get(normalized, normalized)
                        self._site_url(SITES[site])
                        item["target"] = normalized
                    elif normalized in APPS:
                        try:
                            self._platform().require_app(normalized)
                        except RuntimeError as exc:
                            raise ActionPolicyError(str(exc)) from None
                        item["target"] = normalized
                    else:
                        self._platform()
                        try:
                            # Folder aliases also undergo containment and type checks.
                            local = FOLDERS[normalized] if normalized in FOLDERS else target
                            item["target"] = str(resolve_local_target(local))
                        except ValueError as exc:
                            raise ActionPolicyError(str(exc)) from None
            elif action == "search":
                self._platform()
                engine = params.get("engine", "google").lower()
                if engine not in {"google", "youtube"} or not params.get("query", target).strip():
                    raise ActionPolicyError("AI search parameters are not supported.")
                if engine == "youtube":
                    self._browser_platform(preferred)
            elif action == "list":
                if target.lower() not in {"sites", "apps", "folders"}:
                    raise ActionPolicyError("AI list target is not supported.")
                item["target"] = target.lower()
            elif target.lower() != "help":
                raise ActionPolicyError("AI help target is not supported.")
        return validated
