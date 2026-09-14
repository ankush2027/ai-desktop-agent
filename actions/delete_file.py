import os


def delete_file(file_name):
    try:
        os.remove(file_name)
        print("File deleted.")
    except FileNotFoundError:
        print("File does not exist.")