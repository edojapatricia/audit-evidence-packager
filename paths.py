"""Path helpers that behave the same from source and inside a PyInstaller bundle.

When frozen, read-only resources (index.html) live next to the bundled code in
``sys._MEIPASS``, while anything the user can change - the saved API key and
logs - lives in a writable per-user directory instead.
"""

import os
import sys
from pathlib import Path

APP_NAME = "AuditPack"
APP_DIR_NAME = "AuditPack"


def is_frozen():
    """True when running from a PyInstaller build rather than source."""
    return bool(getattr(sys, "frozen", False))


def resource_root():
    """Directory that holds bundled read-only files (index.html)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def user_data_dir():
    """Per-user writable directory, created on first access."""
    if sys.platform == "win32":
        base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir():
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
