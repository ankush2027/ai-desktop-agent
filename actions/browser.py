import webbrowser
from config import SITES

def open_site(site_name: str):
    """
    Opens commonly used websites based on input.
    
    Args:
        site_name (str): Name of the site (youtube/google)
    """

    site_name = site_name.lower()

    if site_name in SITES:
        webbrowser.open(SITES[site_name])
        print(f"Opening {site_name}...")
    else:
        print("Site not supported.")
        