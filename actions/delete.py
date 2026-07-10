from actions.delete_file import delete_file
from actions.delete_folder import delete_folder


def delete(target, params):
    item_type = params.get("type")

    if item_type == "file":
        delete_file(target)

    elif item_type == "folder":
        delete_folder(target)

    else:
        print("Unknown delete type.")