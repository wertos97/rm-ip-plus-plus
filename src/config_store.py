"""Simple settings store: %APPDATA%/RMIP++/config.json"""
from __future__ import annotations

import json
import os

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "RMIP++")
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
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return {**DEFAULTS, **cfg}
    except Exception:
        return dict(DEFAULTS)


def save(cfg: dict) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
