import shutil

def copy_file(source, destination):
    shutil.copy(source, destination)
    print("File copied.")
