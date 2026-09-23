from actions.platforms import get_platform


def open_app(app_name: str):
    get_platform().open_app(app_name.lower())
    print("Application launch request accepted; readiness is not verified.")
