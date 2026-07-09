import webbrowser

def search_google(target, params=None):
    url = f"https://www.google.com/search?q={target}"
    webbrowser.open(url)