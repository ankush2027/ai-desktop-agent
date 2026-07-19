import shutil

def move_file(source,destination):
    try:
        shutil.move(source, destination)
        print(f"Moved '{source}' to '{destination}'.")
    except FileNotFoundError:
        print(f"'{source}' does not exist.")