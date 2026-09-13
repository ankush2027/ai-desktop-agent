"""Bounded Gmail compose preparation. This module has no sending capability."""

import re
import subprocess
from urllib.parse import urlencode, urlsplit

from actions.browser import open_browser
from config import BROWSERS, SITES


FIELD_LIMITS = {"to": 254, "subject": 200, "body": 4000}
_RECIPIENT = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)


def validate_email_fields(target, params):
    """Validate plain text, separately from shell-oriented action parameters."""
    if target != "gmail":
        raise ValueError("Email preparation supports only gmail.")
    if not isinstance(params, dict) or set(params) != set(FIELD_LIMITS):
        raise ValueError("Email preparation requires only to, subject, and body.")
    for name, limit in FIELD_LIMITS.items():
        value = params[name]
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"Email {name} must be a string of at most {limit} characters.")
        allowed_controls = "\n\r\t" if name == "body" else ""
        if any((ord(char) < 32 or 127 <= ord(char) <= 159) and char not in allowed_controls for char in value):
            raise ValueError(f"Email {name} contains unsupported control characters.")
    recipient = params["to"]
    if recipient and (not _RECIPIENT.fullmatch(recipient) or len(recipient.split("@")[0]) > 64):
        raise ValueError("Email recipient must be empty or one supported email address.")
    if not (params["subject"].strip() or params["body"].strip()):
        raise ValueError("Email preparation requires a subject or body.")


def compose_url(target, params):
    validate_email_fields(target, params)
    base = SITES["gmail"]
    parsed = urlsplit(base)
    if parsed.scheme != "https" or parsed.netloc != "mail.google.com" or parsed.path not in ("", "/", "/mail", "/mail/") or parsed.query or parsed.fragment:
        raise ValueError("Configured Gmail destination is not supported.")
    url = base.rstrip("/") + ("/" if parsed.path.rstrip("/") == "/mail" else "/mail/")
    url += "?" + urlencode({"view": "cm", "fs": "1", "to": params["to"], "su": params["subject"], "body": params["body"]})
    if len(url) > 8000:
        raise ValueError("Encoded email exceeds the compose URL limit.")
    return url


def draft_email(target, params):
    fields = {key: value for key, value in params.items() if key != "context"}
    url = compose_url(target, fields)
    browsers = params.get("context", {}).get("system_context", {}).get("browsers", BROWSERS)
    try:
        open_browser(browsers["preferred"], url)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        # Browser exceptions may contain the command-line URL and email text.
        raise RuntimeError("Gmail compose launch failed.") from None
    print("Gmail compose preparation launch requested. Review the compose window manually.")
    if not fields["to"]:
        print("Recipient is empty; fill it in manually in Gmail.")
