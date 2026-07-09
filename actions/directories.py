import os

def create_folder(folder_name):
    try:
        os.makedirs(folder_name)
        print(f"Created '{folder_name}'.")
    except FileExistsError:
        print(f"'{folder_name}' already exists.")