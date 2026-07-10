import os


def rename_folder(old_name, new_name):
    try:
        os.rename(old_name, new_name)
        print(f"Renamed '{old_name}' to '{new_name}'.")
    except FileNotFoundError:
        print(f"'{old_name}' does not exist.")