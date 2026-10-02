SITES={
     "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "gmail":"https://mail.google.com",
        "github":"https://github.com"
}


APPS = {
    "calculator": "Calculator",
    "vscode": "Visual Studio Code",
    "whatsapp": "WhatsApp",
    "telegram": "Telegram"
}

BROWSERS = {
    "available": ["safari", "brave"],
    "preferred": "brave",
}


SITE_ALIASES={
    "yt":"youtube",
    "mail":"gmail",
    "gh":"github"
}

FILLER_WORDS = {
    "please",
    "can",
    "could",
    "would",
    "you",
    "me",
    "the",
    "a",
    "an",
    "to"
}

FOLDERS = {
    "desktop": "~/Desktop",
    "downloads": "~/Downloads",
    "documents": "~/Documents"
}

ACTION_ALIASES = {
    "launch": "open",
    "start": "open",
    "open": "open",
    "find": "search",
    "google": "search",
    "search": "search",
    "list": "list",
    "help": "help",
    "make":"create",
    "create":"create",
    "new":"create",
    "delete": "delete",
    "remove": "delete",
    "del": "delete",
    "rename": "rename",
    "change": "rename",
    "copy":"copy",
    "move":"move"
}

# Trusted Mac workspace destinations. AI plans cannot extend this catalog.
WORKSPACE_URLS = {"youtube_music": "https://music.youtube.com"}

# Trusted workspace folder aliases, not planner-supplied paths. Folders must
# already exist and pass the existing safe local-open policy; never create them.
WORKSPACE_FOLDERS = {
    "ai-desktop-agent": "~/Desktop/ai-desktop-agent",
    "projects": "~/Desktop/Test",
    "documents": FOLDERS["documents"],
}
