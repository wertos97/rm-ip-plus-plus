"""Edge windows as 'tabs': one window per camera, clicking again restores focus.

Dedicated profile (does not touch the user's main Edge, passwords are remembered
between sessions); the main process per camera is kept in a dict.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
_PROFILE_TAG = "rmip_edge_profile"
_pid_cache: tuple[float, set[int]] = (0.0, set())


def profile_dir() -> str:
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "RMIP++", "edge_profile")
    os.makedirs(base, exist_ok=True)
    return base


def browser_exe() -> str | None:
    if os.path.exists(EDGE_EXE):
        return EDGE_EXE
    if os.path.exists(CHROME_EXE):
        return CHROME_EXE
    return None


def _profile_pids() -> set[int]:
    """Browser PIDs using the app profile (60 s cache)."""
    global _pid_cache
    if time.time() - _pid_cache[0] < 60 and _pid_cache[1]:
        return _pid_cache[1]
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"Get-CimInstance Win32_Process -Filter 'CommandLine like \'%{_PROFILE_TAG}%\'\'"
                            " | Select-Object -ExpandProperty ProcessId"],
                           capture_output=True, text=True, timeout=25,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        pids = {int(x) for x in p.stdout.split() if x.strip().isdigit()}
    except Exception:
        pids = set()
    _pid_cache = (time.time(), pids)
    return pids


def _enum_windows() -> list[tuple[int, int, str]]:
    user32 = ctypes.windll.user32
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    out: list[tuple[int, int, str]] = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        ln = user32.GetWindowTextLengthW(hwnd)
        if ln == 0:
            return True
        buf = ctypes.create_unicode_buffer(ln + 1)
        user32.GetWindowTextW(hwnd, buf, ln + 1)
        out.append((hwnd, pid.value, buf.value))
        return True

    user32.EnumWindows(proto(cb), 0)
    return out


def focus_window(hwnd: int) -> bool:
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


class EdgeTabs:
    """One window per IP. open() returns 'focused' | 'opened' | 'no-browser'."""

    def __init__(self):
        self.procs: dict[str, subprocess.Popen] = {}

    def _find(self, ip: str, pid: int | None) -> int:
        ours = _profile_pids()
        if pid is not None:
            ours = ours | {pid}
        cands = []
        for hwnd, wpid, title in _enum_windows():
            if ours and wpid not in ours:
                continue
            if ip in title or "Sony Network Camera" in title:
                rect = wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                area = (rect.right - rect.left) * (rect.bottom - rect.top)
                cands.append((area, hwnd))
        cands.sort(reverse=True)
        return cands[0][1] if cands else 0

    def open(self, ip: str, port: int = 80) -> tuple[str, str]:
        exe = browser_exe()
        if not exe:
            return "no-browser", "Edge/Chrome not found."
        proc = self.procs.get(ip)
        if proc is not None and proc.poll() is None:
            hwnd = self._find(ip, proc.pid)
            if hwnd and focus_window(hwnd):
                return "focused", f"Restored window {ip}."
        # the window may have survived an app restart - look in profile processes
        hwnd = self._find(ip, None)
        if hwnd and focus_window(hwnd):
            return "focused", f"Restored window {ip}."
        url = f"http://{ip}:{port}/"
        try:
            self.procs[ip] = subprocess.Popen(
                [exe, f"--app={url}", f"--user-data-dir={profile_dir()}",
                 "--no-first-run", "--no-default-browser-check"])
        except Exception as e:
            return "no-browser", f"Browser start failed: {e}"[:200]
        return "opened", f"Opened window {url} (Edge, app profile)."
