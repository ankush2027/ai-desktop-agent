from actions.rename_file import rename_file
from actions.rename_folder import rename_folder


def rename(target, params):
    item_type = params.get("type")

    if item_type == "file":
        rename_file(target, params["new_name"])

    elif item_type == "folder":
        rename_folder(target, params["new_name"])

    else:
        print("Unknown rename type.")