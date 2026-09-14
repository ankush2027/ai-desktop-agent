from actions.delete import delete
from actions.copy import copy
from actions.create import create
from actions.move import move
from actions.rename import rename
from actions.exit import exit_program
from actions.help import show_help
from actions.list_items import list_items
from logger import log_action
from actions.opener import open_target
from actions.search import search_google
from actions.email import draft_email
from memory import MemoryManager
from context import ContextEngine
from copy import deepcopy


context_engine = None  # Optional caller-owned context engine; no import-time storage.

ACTION_MAP = {
    "draft_email": draft_email,
    "open": open_target,
    "search": search_google,
    "list": list_items,
    "help": show_help,
    "exit": exit_program,
    "create": create,
    "delete":delete,
    "rename":rename,
    "copy":copy,
    "move":move
}


def execute(command):
    action = command.get("action")
    target = command.get("target")
    params = deepcopy(command.get("params", {}))
    handler = ACTION_MAP.get(action)
    if handler is None:
        raise ValueError("Unsupported action.")
    log_action(action, target)
    try:
        # Only preference-dependent workflows require storage during execution.
        if action == "draft_email" or (action == "search" and params.get("engine", "google").lower() == "youtube"):
            if context_engine is not None:
                context = context_engine.build_context(query=target or action)
            else:
                with MemoryManager() as manager:
                    context = ContextEngine(manager).build_context(query=target or action)
            params["context"] = deepcopy(context.to_dict())
        if handler(target, params) is False:
            raise RuntimeError("Action reported failure.")
    except Exception as exc:
        log_action(action, target, "failed", error=exc)
        raise
    log_action(action, target, "succeeded")
