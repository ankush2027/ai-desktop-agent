import os


def delete_folder(folder_name):
    try:
        os.rmdir(folder_name)
        print(f"Deleted '{folder_name}'.")
    except FileNotFoundError:
        print(f"'{folder_name}' does not exist.")
    except OSError:
        print(f"'{folder_name}' is not empty.")