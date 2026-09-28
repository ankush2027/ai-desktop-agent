import shutil
from pathlib import Path

def copy_file(source, destination):
    if not Path(source).is_file():
        raise ValueError("Copy source must be an existing file.")
    shutil.copy(source, destination)
    print("File copied.")
