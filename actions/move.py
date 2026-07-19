from actions.move_file import move_file

def move(target, params):
    move_file(target, params["new_name"])