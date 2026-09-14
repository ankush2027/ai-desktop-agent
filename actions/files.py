def create_file(file_name):
    try:
        file = open(file_name, "x")
        file.close()
        print("File created.")
    except FileExistsError:
        print("File already exists.")