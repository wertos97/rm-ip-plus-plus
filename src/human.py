"""Czytelne wartosci sensora: mapowania indeks -> jednostki (z CGI Command List)."""
from __future__ import annotations

# Migawka dla 1080/50p (VideoFormat kamery: 1080p_50_ModeB)
SHUTTER_50P = {
    33: "1/10000", 32: "1/6000", 31: "1/4000", 30: "1/3000", 29: "1/2000",
    28: "1/1500", 27: "1/1000", 26: "1/600", 25: "1/425", 24: "1/300",
    23: "1/215", 22: "1/150", 21: "1/120", 20: "1/100", 19: "1/60",
    18: "1/50", 17: "1/30", 16: "1/25", 15: "1/20", 14: "1/15",
    13: "1/12", 12: "1/8", 11: "1/6", 10: "1/4", 9: "1/3", 8: "1/2",
    7: "2/3", 6: "1/1",
}

IRIS_F = {
    25: "F2.0", 24: "F2.2", 23: "F2.4", 22: "F2.6", 21: "F2.8", 20: "F3.1",
    19: "F3.4", 18: "F3.7", 17: "F4.0", 16: "F4.4", 15: "F4.8", 14: "F5.2",
    13: "F5.6", 12: "F6.2", 11: "F6.8", 10: "F7.3", 9: "F8.0", 8: "F8.7",
    7: "F9.6", 6: "F10", 5: "F11", 4: "F12", 3: "F14", 2: "F16", 1: "F18",
    0: "CLOSE",
}


def gain_db(v: int) -> str:
    try:
        return f"{(int(v) - 1) * 3}dB"
    except (ValueError, TypeError):
        return "?"


def expcomp_db(v: int) -> str:
    try:
        d = (int(v) - 7) * 1.5
        return f"{d:+.1f}dB".replace(".0dB", "dB")
    except (ValueError, TypeError):
        return "?"


def _s16(h: str) -> int:
    v = int(h, 16)
    return v - 0x10000 if v >= 0x8000 else v


def pan_deg(h: str) -> float:
    try:
        return _s16(h) / 51.2
    except (ValueError, TypeError):
        return float("nan")


def tilt_deg(h: str) -> float:
    return pan_deg(h)


def zoom_x(h: str) -> float:
    """Przybliżone powiekszenie optyczne 1-20x (liniowo; optyka nie jest idealnie liniowa)."""
    try:
        return 1.0 + 19.0 * max(0, int(h, 16)) / 0x4000
    except (ValueError, TypeError):
        return float("nan")


def fmt_deg(d: float) -> str:
    return "?" if d != d else f"{d:+.1f}°"
