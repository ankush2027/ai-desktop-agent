from actions.files import create_file
from actions.directories import create_folder

def create(target, params):
    item_type = params.get("type")

    if item_type == "file":
        create_file(target)

    elif item_type == "folder":
        create_folder(target)

    else:
        print("Unknown create type.")