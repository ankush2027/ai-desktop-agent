import os


def rename_folder(old_name, new_name):
    try:
        os.rename(old_name, new_name)
        print("Folder renamed.")
    except FileNotFoundError:
        print("Folder does not exist.")