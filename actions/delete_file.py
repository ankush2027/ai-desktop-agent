import os


def delete_file(file_name):
    try:
        os.remove(file_name)
        print(f"Deleted '{file_name}'.")
    except FileNotFoundError:
        print(f"'{file_name}' does not exist.")