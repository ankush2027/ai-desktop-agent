import os
from datetime import datetime


LOG_FOLDER = "logs"
LOG_FILE = os.path.join(LOG_FOLDER, "history.log")


def log_action(action, target):
    if not os.path.exists(LOG_FOLDER):
        os.makedirs(LOG_FOLDER)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"[LOG] {action} --> {target}")

    with open(LOG_FILE, "a") as file:
        file.write(f"Time   : {current_time}\n")
        file.write(f"Action : {action}\n")
        file.write(f"Target : {target}\n")
        file.write("-" * 40 + "\n")