import webbrowser
from urllib.parse import urlencode

from actions.browser import open_browser
from config import BROWSERS

def search_google(target, params=None):
    """Execute a search using fixed endpoints and application-owned encoding."""
    params = params or {}
    engine = params.get("engine", "google").lower()
    query = params.get("query", target)
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query must be a non-empty string.")
    if engine == "youtube":
        url = "https://www.youtube.com/results?" + urlencode({"search_query": query})
        browsers = params.get("context", {}).get("system_context", {}).get("browsers", BROWSERS)
        open_browser(browsers["preferred"], url)
    elif engine == "google":
        url = "https://www.google.com/search?" + urlencode({"q": query})
        if not webbrowser.open(url):
            raise RuntimeError("Browser did not accept the search launch request.")
    else:
        raise ValueError("Search engine not supported.")
