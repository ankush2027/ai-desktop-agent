"""Conservative local document/folder targets for the open capability."""

import os
from pathlib import Path
import platform
import stat
import subprocess

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log"}
PREVIEW_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
BUNDLE_SUFFIXES = {".app", ".bundle", ".framework", ".workflow", ".scptd"}


def resolve_local_target(target):
    kind = None
    words = target.split(maxsplit=1)
    if words and words[0].lower() in {"file", "folder"}:
        if len(words) != 2:
            raise ValueError("Local open target is missing.")
        kind, target = words[0].lower(), words[1]
    path = Path(os.path.expanduser(target)).absolute()
    try:
        # Reject links rather than trusting a later resolution of the same name.
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError("Linked open targets are not supported.")
        resolved = path.resolve(strict=True)
        home = Path.home().resolve()
        if not resolved.is_relative_to(home):
            raise ValueError("Local open target is outside the allowed path.")
        if any(part.suffix.lower() in BUNDLE_SUFFIXES for part in (resolved, *resolved.parents)):
            raise ValueError("Application bundles are not local document targets.")
        mode = resolved.stat().st_mode
        if stat.S_ISDIR(mode):
            if kind == "file":
                raise ValueError("Expected a file target.")
        elif stat.S_ISREG(mode):
            if kind == "folder" or resolved.suffix.lower() not in TEXT_SUFFIXES | PREVIEW_SUFFIXES:
                raise ValueError("Local file type is not supported for safe opening.")
            if platform.system() == "Darwin" and mode & 0o111:
                raise ValueError("Executable files are not safe document targets.")
        else:
            raise ValueError("Local open target must be a regular file or folder.")
        return resolved
    except (OSError, RuntimeError):
        raise ValueError("Local open target is unavailable.") from None


def open_local_target(target):
    if platform.system() != "Darwin":
        raise RuntimeError("Local file/folder opening is supported only on macOS.")
    path = resolve_local_target(target)
    if path.is_dir():
        command = ["open", str(path)]
    else:
        # A document is opened with a fixed reader, never an executable association.
        viewer = "TextEdit" if path.suffix.lower() in TEXT_SUFFIXES else "Preview"
        command = ["open", "-a", viewer, str(path)]
    subprocess.run(command, check=True)
