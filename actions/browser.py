import webbrowser

def open_site(site_name: str):
    """
    Opens commonly used websites based on input.
    
    Args:
        site_name (str): Name of the site (youtube/google)
    """

    sites = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com"
    }

    site_name = site_name.lower()

    if site_name in sites:
        webbrowser.open(sites[site_name])
        print(f"Opening {site_name}...")
    else:
        print("Site not supported.")

