import shutil

def move_file(source,destination):
    shutil.move(source, destination)
    print("File moved.")
