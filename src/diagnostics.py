"""Diagnostyka srodowiska: admin, ping, porty, firewall."""
from __future__ import annotations

import ctypes
import socket
import subprocess


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ping(ip: str, timeout_ms: int = 800) -> tuple[bool, str]:
    try:
        p = subprocess.run(["ping", "-n", "1", "-w", str(timeout_ms), ip],
                           capture_output=True, text=True, timeout=10)
        ok = p.returncode == 0
        # wytnij tylko linie z czasem/statystyka
        tail = "\n".join((p.stdout or "").splitlines()[-3:])
        return ok, tail.strip()[:300]
    except Exception as e:
        return False, str(e)[:200]


def tcp_open(ip: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def firewall_has_app_rule() -> bool:
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-NetFirewallRule | Where-Object {$_.DisplayName -like '*RM*IP*'} | Select-Object -First 1"],
                           capture_output=True, text=True, timeout=15)
        return bool(p.stdout.strip())
    except Exception:
        return False


def env_report() -> str:
    lines = [f"admin(UAC): {is_admin()}"]
    try:
        hn = socket.gethostname()
        lines.append(f"host: {hn} -> {socket.gethostbyname(hn)}")
    except Exception as e:
        lines.append(f"host blad: {e}")
    return " | ".join(lines)
