import subprocess
import os
from config import FOLDERS


def open_folder(folder_name):
    folder_name = folder_name.lower()

    if folder_name in FOLDERS:
        real_folder_path = os.path.expanduser(FOLDERS[folder_name])

        subprocess.run(["open", real_folder_path])

        print(f"Opening {real_folder_path}...")
    else:
        print(f"Folder '{folder_name}' not supported.")