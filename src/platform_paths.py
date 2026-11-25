"""User-scoped paths for Windows and macOS."""

from __future__ import annotations

import os
import sys

APP_NAME = "RMIP++"
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"


def app_data_dir() -> str:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif IS_MACOS:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, APP_NAME)


def cache_dir() -> str:
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    elif IS_MACOS:
        base = os.path.expanduser("~/Library/Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    return os.path.join(base, APP_NAME)


def thumbnail_dir() -> str:
    return os.path.join(cache_dir(), "thumbnails")
