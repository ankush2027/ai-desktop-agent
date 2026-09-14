import os

def create_folder(folder_name):
    try:
        os.makedirs(folder_name)
        print("Folder created.")
    except FileExistsError:
        print("Folder already exists.")