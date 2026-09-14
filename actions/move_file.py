import shutil

def move_file(source,destination):
    shutil.move(source, destination)
    print(f"Moved '{source}' to '{destination}'.")
