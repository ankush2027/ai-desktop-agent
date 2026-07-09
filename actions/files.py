def create_file(file_name):
    try:
        file = open(file_name, "x")
        file.close()
        print(f"Created '{file_name}'.")
    except FileExistsError:
        print(f"'{file_name}' already exists.")