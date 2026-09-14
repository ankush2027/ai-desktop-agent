from actions.move_file import move_file

def move(target, params):
    if params.get("type") != "file" or not isinstance(params.get("destination"), str) or not params["destination"]:
        raise ValueError("Move requires a file and destination.")
    if set(params) - {"type", "destination", "context"}:
        raise ValueError("Move contains unsupported parameters.")
    move_file(target, params["destination"])
