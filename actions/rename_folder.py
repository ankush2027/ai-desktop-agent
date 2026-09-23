import os
from pathlib import Path


def rename_folder(old_name, new_name):
    if not Path(old_name).is_dir():
        raise ValueError("Rename source must be an existing folder.")
    os.rename(old_name, new_name)
    print("Folder renamed.")
