"""Open camera web UIs in a browser window.

Windows keeps dedicated Edge/Chrome app windows. macOS uses Chrome or Edge when
available and otherwise falls back to the default browser.
"""

from __future__ import annotations

import os
import subprocess
import time

try:
    from .platform_paths import app_data_dir
except ImportError:
    from platform_paths import app_data_dir

EDGE_EXE_WINDOWS = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CHROME_EXE_WINDOWS = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EDGE_EXE_MACOS = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
CHROME_EXE_MACOS = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_PROFILE_TAG = "rmip_edge_profile"
_pid_cache: tuple[float, set[int]] = (0.0, set())


def profile_dir() -> str:
    base = os.path.join(app_data_dir(), "edge_profile")
    os.makedirs(base, exist_ok=True)
    return base


def browser_exe() -> str | None:
    candidates = (EDGE_EXE_WINDOWS, CHROME_EXE_WINDOWS) if os.name == "nt" else (EDGE_EXE_MACOS, CHROME_EXE_MACOS)
    return next((path for path in candidates if os.path.exists(path)), None)


def _profile_pids() -> set[int]:
    """Browser PIDs using the app profile on Windows."""
    global _pid_cache
    if os.name != "nt":
        return set()
    if time.time() - _pid_cache[0] < 60 and _pid_cache[1]:
        return _pid_cache[1]
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-CimInstance Win32_Process -Filter 'CommandLine like '%{_PROFILE_TAG}%''"
                " | Select-Object -ExpandProperty ProcessId",
            ],
            capture_output=True,
            text=True,
            timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        pids = {int(value) for value in result.stdout.split() if value.strip().isdigit()}
    except Exception:
        pids = set()
    _pid_cache = (time.time(), pids)
    return pids


def _enum_windows() -> list[tuple[int, int, str]]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    prototype = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    windows: list[tuple[int, int, str]] = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        windows.append((hwnd, pid.value, buffer.value))
        return True

    user32.EnumWindows(prototype(callback), 0)
    return windows


def focus_window(hwnd: int) -> bool:
    import ctypes

    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


def _activate_macos_browser(executable: str) -> None:
    name = "Google Chrome" if "Chrome" in executable else "Microsoft Edge"
    subprocess.Popen(["osascript", "-e", f'tell application "{name}" to activate'])


class EdgeTabs:
    """One browser window per camera IP."""

    def __init__(self):
        self.procs: dict[str, subprocess.Popen] = {}

    def _find(self, ip: str, pid: int | None) -> int:
        import ctypes
        from ctypes import wintypes

        ours = _profile_pids()
        if pid is not None:
            ours = ours | {pid}
        candidates = []
        for hwnd, window_pid, title in _enum_windows():
            if ours and window_pid not in ours:
                continue
            if ip in title or "Sony Network Camera" in title:
                rect = wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                area = (rect.right - rect.left) * (rect.bottom - rect.top)
                candidates.append((area, hwnd))
        candidates.sort(reverse=True)
        return candidates[0][1] if candidates else 0

    def open(self, ip: str, port: int = 80) -> tuple[str, str]:
        executable = browser_exe()
        if not executable:
            return "no-browser", "Edge/Chrome not found."

        process = self.procs.get(ip)
        if process is not None and process.poll() is None:
            if os.name == "nt":
                hwnd = self._find(ip, process.pid)
                if hwnd and focus_window(hwnd):
                    return "focused", f"Restored window {ip}."
            else:
                _activate_macos_browser(executable)
                return "focused", f"Restored browser for {ip}."

        if os.name == "nt":
            hwnd = self._find(ip, None)
            if hwnd and focus_window(hwnd):
                return "focused", f"Restored window {ip}."

        url = f"http://{ip}:{port}/"
        try:
            self.procs[ip] = subprocess.Popen(
                [
                    executable,
                    f"--app={url}",
                    f"--user-data-dir={profile_dir()}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
            )
        except Exception as exc:
            return "no-browser", f"Browser start failed: {exc}"[:200]
        browser = "Edge" if "Edge" in executable else "Chrome"
        return "opened", f"Opened window {url} ({browser}, app profile)."
