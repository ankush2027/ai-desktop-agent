import subprocess
from config import APPS


def open_app(app_name: str):
    app_name = app_name.lower()

    if app_name in APPS:
        real_app_name = APPS[app_name]

        subprocess.run(["open", "-a", real_app_name])

        print(f"Opening {real_app_name}...")
    else:
        print(f"App '{app_name}' not supported.")