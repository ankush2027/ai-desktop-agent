from actions.config import APPS

def open_app(app_name:str):
    if app_name in APPS:
        print(f"Opening {app_name}...")
    else:
        print("App not supported.")