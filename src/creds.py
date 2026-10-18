"""Per-camera credentials: model defaults, saved entries and legacy global.

Resolution order for a camera IP:
  1. credentials saved for that IP (entered by the user, remembered),
  2. a custom global login from older config versions (if not the old default),
  3. SRG-X400 default: admin / admin123,
  4. BRC-AM7 default: admin / Admin123,
  5. legacy Sony default: admin / admin.
"""
from __future__ import annotations

SRG_DEFAULT = ("admin", "admin123")
AM7_DEFAULT = ("admin", "Admin123")
LEGACY_DEFAULT = ("admin", "admin")


def saved_credentials(config: dict, ip: str) -> tuple[str, str] | None:
    entry = (config.get("credentials") or {}).get(ip)
    if isinstance(entry, dict) and entry.get("user") is not None:
        return (str(entry.get("user") or ""), str(entry.get("password") or ""))
    return None


def save_credentials(config: dict, ip: str, user: str, password: str) -> None:
    creds = config.setdefault("credentials", {})
    if not isinstance(creds, dict):
        creds = {}
        config["credentials"] = creds
    creds[ip] = {"user": user, "password": password}


def candidates(config: dict, ip: str) -> list[tuple[str, str]]:
    """Credential pairs to try, in order, without duplicates."""
    out: list[tuple[str, str]] = []
    saved = saved_credentials(config, ip)
    if saved and saved[0]:
        out.append(saved)
    gu, gp = config.get("user"), config.get("password")
    if gu and gp is not None and (gu, gp) != LEGACY_DEFAULT and (gu, gp) not in out:
        out.append((gu, gp))
    for pair in (SRG_DEFAULT, AM7_DEFAULT, LEGACY_DEFAULT):
        if pair not in out:
            out.append(pair)
    return out
