import os
from datetime import datetime
from config import APPS, BROWSERS, FOLDERS, SITES, SITE_ALIASES

LOG_FOLDER = "logs"
LOG_FILE = os.path.join(LOG_FOLDER, "history.log")
ACTIONS = {"open", "search", "draft_email", "list", "help", "exit", "create", "delete", "rename", "copy", "move"}


def error_category(error):
    name = type(error).__name__
    if name in {"TimeoutError", "TimeoutException", "ConnectTimeout", "ReadTimeout", "APITimeoutError"}:
        return "timeout"
    if name in {"ConnectionError", "ConnectError", "NetworkError", "APIConnectionError"}:
        return "network"
    if name in {"MemoryStorageError", "OperationalError", "DatabaseError"}:
        return "storage"
    code = getattr(error, "code", getattr(error, "status_code", None))
    if code in (401, 403):
        return "authentication"
    if code == 429:
        return "quota"
    return "operation"


def safe_target(action, target):
    if action == "search":
        return "search"
    if action == "draft_email":
        return "gmail"
    known = set(APPS) | set(BROWSERS["available"]) | set(FOLDERS) | set(SITES) | set(SITE_ALIASES)
    if action == "open" and isinstance(target, str) and target.lower() in known:
        return target.lower()
    if action == "list" and target in {"sites", "apps", "folders"}:
        return target
    return "local" if action in {"open", "create", "delete", "rename", "copy", "move"} else "command"


def log_action(action, target, status="requested", error=None):
    action = action if action in ACTIONS else "unknown"
    status = status if status in {"requested", "succeeded", "failed"} else "unknown"
    details = f"action={action}, target={safe_target(action, target)}, status={status}"
    if error is not None:
        details += f", error={error_category(error)}"
    try:
        print(f"[LOG] {details}")
        os.makedirs(LOG_FOLDER, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as file:
            file.write(f"{datetime.now().isoformat(timespec='seconds')} {details}\n")
    except (OSError, UnicodeError):
        try:
            print("[LOG] History unavailable; command execution is unaffected.")
        except (OSError, UnicodeError):
            pass
