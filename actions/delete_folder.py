import os


def delete_folder(folder_name):
    try:
        os.rmdir(folder_name)
        print("Folder deleted.")
    except FileNotFoundError:
        print("Folder does not exist.")
    except OSError:
        print("Folder could not be removed.")