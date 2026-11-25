"""Simple settings store in the platform application-data directory."""

from __future__ import annotations

import copy
import json
import os
import tempfile

try:
    from .platform_paths import app_data_dir
except ImportError:
    from platform_paths import app_data_dir

APP_DIR = app_data_dir()
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    "user": "",
    "password": "",
    "credentials": {},
    "subnet_base": "192.168.0.200",
    "prefix": 24,
    "scan_cidr": "192.168.0.0/24",
    "table_file": "",
    "known_ips": [],
}


def load() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as file:
            config = json.load(file)
        if not isinstance(config, dict):
            return copy.deepcopy(DEFAULTS)
        return {**copy.deepcopy(DEFAULTS), **config}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return copy.deepcopy(DEFAULTS)


def save(config: dict) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=APP_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=2, ensure_ascii=False)
        os.replace(temporary, CONFIG_FILE)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
