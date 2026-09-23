import os


def delete_folder(folder_name):
    # Empty directories only; propagate failures to the existing executor.
    os.rmdir(folder_name)
    print("Folder deleted.")
