import os
from config import FOLDERS
from actions.local_paths import open_local_target


def open_folder(folder_name):
    folder_name = folder_name.lower()

    if folder_name in FOLDERS:
        real_folder_path = os.path.expanduser(FOLDERS[folder_name])

        open_local_target(real_folder_path)

        print(f"Opening {real_folder_path}...")
    else:
        raise ValueError("Folder is not supported.")
