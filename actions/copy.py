from actions.copy_file import copy_file

def copy(target, params):
    copy_file(target, params["new_name"])