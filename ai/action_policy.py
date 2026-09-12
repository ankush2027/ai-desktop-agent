import os
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from config import APPS, BROWSERS, FOLDERS, SITE_ALIASES, SITES
from ai.errors import AIPlanningError


class ActionPolicyError(AIPlanningError):
    """Raised when an AI action plan violates the execution safety policy."""


class ActionPolicy:
    """Allow only narrowly scoped, non-destructive AI actions."""

    ALLOWED_ACTIONS = {"open", "search", "list", "help"}
    _UNSAFE_TARGET = re.compile(r"[\x00-\x1f\x7f;&|`$]")

    def validate(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate a schema-checked plan before it reaches the executor."""
        for action in actions:
            action_name = action["action"]
            if action_name == "delete":
                raise ActionPolicyError("AI delete actions are not allowed.")
            if action_name not in self.ALLOWED_ACTIONS:
                raise ActionPolicyError(
                    f"AI action '{action_name}' is not allowed by safety policy."
                )

            self._validate_target(action_name, action["target"])
            self._validate_params(action_name, action["params"])

        return actions

    def _validate_target(self, action_name: str, target: str) -> None:
        if self._UNSAFE_TARGET.search(target):
            raise ActionPolicyError("AI action target contains unsafe characters.")

        if action_name == "open":
            normalized = target.strip().lower()
            known_targets = (
                set(SITES)
                | set(SITE_ALIASES)
                | set(APPS)
                | set(FOLDERS)
                | set(BROWSERS["available"])
            )
            if normalized in known_targets:
                return

            path = Path(os.path.expanduser(target))
            if re.fullmatch(r"[a-z0-9][a-z0-9._-]*", normalized):
                return
            try:
                resolved = path.resolve(strict=True)
            except OSError as exc:
                raise ActionPolicyError("AI open target is not supported.") from exc

            home = Path.home().resolve()
            if resolved != home and home not in resolved.parents:
                raise ActionPolicyError("AI open target is outside the allowed path.")
            return

        if action_name == "list":
            supported_targets = {"sites", "apps", "folders"} | set(FOLDERS)
            if target.strip().lower() not in supported_targets:
                raise ActionPolicyError("AI list target is not supported.")

    @staticmethod
    def _validate_params(action_name: str, params: Dict[str, Any]) -> None:
        allowed_params = {
            "open": {"browser", "mode", "theme", "url"},
            "search": {"engine", "query"},
            "list": set(),
            "help": set(),
        }[action_name]
        unexpected = set(params) - allowed_params
        if unexpected:
            raise ActionPolicyError("AI action contains unsupported parameters.")

        for key in allowed_params & set(params):
            if not isinstance(params[key], str):
                raise ActionPolicyError(f"AI parameter '{key}' must be a string.")
            if ActionPolicy._UNSAFE_TARGET.search(params[key]):
                raise ActionPolicyError(
                    f"AI parameter '{key}' contains unsafe characters."
                )
            if action_name == "open" and key == "url":
                parsed = urlparse(params[key])
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ActionPolicyError("AI open URL is not supported.")
            if action_name == "open" and key == "browser":
                if params[key].lower() not in BROWSERS["available"]:
                    raise ActionPolicyError("AI browser parameter is not supported.")
            if action_name == "open" and key == "theme":
                if params[key].lower() not in {"dark", "light", "system"}:
                    raise ActionPolicyError("AI theme parameter is not supported.")
            if action_name == "open" and key == "mode":
                if params[key].lower() not in {"dark", "light", "system"}:
                    raise ActionPolicyError("AI mode parameter is not supported.")
