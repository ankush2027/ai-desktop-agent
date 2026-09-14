import os


def rename_file(old_name, new_name):
    try:
        os.rename(old_name, new_name)
        print("File renamed.")
    except FileNotFoundError:
        print("File does not exist.")