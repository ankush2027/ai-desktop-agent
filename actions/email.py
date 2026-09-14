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


def _field_marker(text, pattern):
    # Quoted values may themselves contain structural words such as 'body'.
    marker = re.compile(pattern, re.IGNORECASE)
    index = 0
    while index < len(text):
        if text[index] in ('"', "'") and (index == 0 or text[index - 1].isspace() or text[index - 1] == ":"):
            end = text.find(text[index], index + 1)
            if end == -1:
                raise ValueError("Email field quoting is ambiguous.")
            index = end + 1
            continue
        match = marker.match(text, index)
        if match:
            return match
        index += 1
    return None


def _field_value(text):
    text = text.strip()
    if text.startswith(('"', "'")):
        if len(text) < 2 or text[-1] != text[0]:
            raise ValueError("Email field quoting is ambiguous.")
        return text[1:-1]
    return text


def extract_email_fields(command):
    """Extract complete fields from the existing explicit compose wording.

    Unlabelled body text uses 'saying'; otherwise subject/body labels delimit
    fields. Quotes protect literal labels, punctuation, and boundary whitespace.
    No address lookup, paraphrasing, or subject/body generation is performed.
    """
    prefix = re.match(r"^\s*(?:(?:please|can you|could you)\s+)?(?:draft|compose|prepare)\s+(?:an?\s+)?email\b", command, re.IGNORECASE)
    if not prefix:
        raise ValueError("Email preparation requires an explicit draft, compose, or prepare request.")
    remainder = command[prefix.end():]
    body_marker = _field_marker(remainder, r"\b(?:(?:and|with)\s+)?(?:body(?:\s*:\s*|\s+)|saying\s+)")
    header = remainder[:body_marker.start()] if body_marker else remainder
    raw_body = remainder[body_marker.end():] if body_marker else ""
    subject_marker = _field_marker(header, r"\b(?:(?:with|and)\s+)?subject(?:\s*:\s*|\s+)")
    recipient_text = header[:subject_marker.start()] if subject_marker else header
    raw_subject = header[subject_marker.end():] if subject_marker else ""
    if _field_marker(raw_subject, r"\bsubject\s*:?\s+"):
        raise ValueError("Email subject boundaries are ambiguous; quote the value.")
    if _field_marker(raw_body, r"\b(?:subject(?:\s*:\s*|\s+)|body(?:\s*:\s*|\s+)|to\s+[^\s]+@)"):
        raise ValueError("Email field order is ambiguous; put recipient/subject before body or quote literal body text.")
    if re.search(r"\b(?:and|then)\s+(?:please\s+)?send\b", recipient_text, re.IGNORECASE):
        raise ValueError("Sending email is not supported.")
    if not raw_body.strip().startswith(('"', "'")) and re.search(r"\b(?:and|then)\s+(?:please\s+)?send\b", raw_body, re.IGNORECASE):
        raise ValueError("Sending email is not supported; quote literal email text.")
    recipient_text = recipient_text.strip()
    if recipient_text and not re.match(r"^to(?:\s|$)", recipient_text, re.IGNORECASE):
        raise ValueError("Email recipient boundaries are ambiguous.")
    recipient_text = re.sub(r"^to\s*", "", recipient_text, flags=re.IGNORECASE)
    recipient = _field_value(recipient_text.rstrip(".,;")) if "@" in recipient_text else ""
    fields = {"to": recipient, "subject": _field_value(raw_subject), "body": _field_value(raw_body)}
    validate_email_fields("gmail", fields)
    return fields


def validate_email_provenance(command, fields):
    expected = extract_email_fields(command)
    if fields != expected:
        raise ValueError("Email fields must come from the complete supplied fields; recipient must match the supplied address.")


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
