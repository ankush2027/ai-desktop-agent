from actions.platforms import get_platform


def open_app(app_name: str):
    get_platform().open_app(app_name.lower())
    print("Application launch request accepted; readiness is not verified.")


def close_app(target="", params=None):
    if params:
        raise ValueError("Close action does not accept parameters.")
    adapter = get_platform()
    if adapter.name != "Darwin":
        raise RuntimeError("Application closing is supported only on macOS.")
    adapter.close_app(target.lower())
    print("Application quit request completed; closure is not verified.")
