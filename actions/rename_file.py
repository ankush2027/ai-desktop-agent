import os
from pathlib import Path


def rename_file(old_name, new_name):
    if not Path(old_name).is_file():
        raise ValueError("Rename source must be an existing file.")
    os.rename(old_name, new_name)
    print("File renamed.")
