import subprocess
import platform
from config import APPS


def open_app(app_name: str):
    app_name = app_name.lower()

    if app_name in APPS:
        if platform.system() != "Darwin":
            raise RuntimeError("Application opening is supported only on macOS.")
        real_app_name = APPS[app_name]

        subprocess.run(["open", "-a", real_app_name], check=True)

        print(f"Opening {real_app_name}...")
    else:
        raise ValueError("Application is not supported.")
