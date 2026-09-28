from actions.copy_file import copy_file

def copy(target, params):
    if params.get("type") != "file" or not isinstance(params.get("destination"), str) or not params["destination"]:
        raise ValueError("Copy requires a file and destination.")
    if set(params) - {"type", "destination", "context"}:
        raise ValueError("Copy contains unsupported parameters.")
    copy_file(target, params["destination"])
