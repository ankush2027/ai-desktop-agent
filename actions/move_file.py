import shutil
from pathlib import Path

def move_file(source,destination):
    if not Path(source).is_file():
        raise ValueError("Move source must be an existing file.")
    shutil.move(source, destination)
    print("File moved.")
