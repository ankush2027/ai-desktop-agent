import shutil

def copy_file(source, destination):
    try:
        shutil.copy(source, destination)
        print(f"Copied '{source}' to '{destination}'.")
    except FileNotFoundError:
        print(f"'{source}' does not exist.")