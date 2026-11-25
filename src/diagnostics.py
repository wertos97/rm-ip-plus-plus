"""Environment diagnostics for Windows and macOS."""

from __future__ import annotations

import os
import socket
import subprocess


def is_admin() -> bool:
    if os.name == "nt":
        import ctypes

        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def ping(ip: str, timeout_ms: int = 800) -> tuple[bool, str]:
    if os.name == "nt":
        command = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        command = ["ping", "-c", "1", "-t", str(max(1, timeout_ms // 1000)), ip]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        tail = "\n".join((result.stdout or "").splitlines()[-3:])
        return result.returncode == 0, tail.strip()[:300]
    except Exception as exc:
        return False, str(exc)[:200]


def tcp_open(ip: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def firewall_has_app_rule() -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-NetFirewallRule | Where-Object {$_.DisplayName -like '*RM*IP*'} | Select-Object -First 1",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def env_report() -> str:
    lines = [f"admin: {is_admin()}"]
    try:
        hostname = socket.gethostname()
        lines.append(f"host: {hostname} -> {socket.gethostbyname(hostname)}")
    except Exception as exc:
        lines.append(f"host error: {exc}")
    return " | ".join(lines)
