"""Human-readable sensor values: index -> unit mappings (from the CGI Command List)."""
from __future__ import annotations

# Shutter for 1080/50p (camera VideoFormat: 1080p_50_ModeB)
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
    """Approximate optical zoom 1-20x (linear; the optics are not perfectly linear)."""
    return zoom_x_max(h, 20.0)


def zoom_x_max(h: str, max_x: float = 25.0) -> float:
    """AM7: optical tele end = 0x4000 (25x); above that Clear Image Zoom kicks in."""
    try:
        return 1.0 + (max_x - 1.0) * max(0, int(h, 16)) / 0x4000
    except (ValueError, TypeError):
        return float("nan")


def fmt_deg(d: float) -> str:
    return "?" if d != d else f"{d:+.1f}°"


# ---------- BRC-AM7 (CGI Command List 2.0): different units than SRG-X400 ----------

def _s20(h: str) -> int:
    """AM7 pan/tilt: 20-bit signed number, 1 unit = 0.001°."""
    v = int(h, 16)
    return v - 0x100000 if v >= 0x80000 else v


def pan_deg20(h: str) -> float:
    try:
        return _s20(h) / 1000.0
    except (ValueError, TypeError):
        return float("nan")


def tilt_deg20(h: str) -> float:
    return pan_deg20(h)


def gain_db_am7(v) -> str:
    """AM7: 0=-9dB, 9=0dB, 45=+36dB."""
    try:
        return f"{int(v) - 9}dB"
    except (ValueError, TypeError):
        return "?"


def ae_level_ev(v) -> str:
    """AM7 AE Level: 0..24 -> -3.0..+3.0 EV (0.25 EV/step, 12 = 0)."""
    try:
        ev = (int(v) - 12) * 0.25
    except (ValueError, TypeError):
        return "?"
    if ev == 0:
        return "0 EV"
    s = f"{ev:+.2f}".rstrip("0").rstrip(".")
    return s + " EV"


# BRC-AM7 shutter for 1080/50p (CGI Command List 2.0, "Shutter (Speed)")
SHUTTER_50P_AM7 = {
    5: "64F", 6: "32F", 7: "16F", 8: "8F", 9: "7F", 10: "6F", 11: "5F",
    12: "4F", 13: "3F", 14: "2F", 15: "1/50", 16: "1/60", 17: "1/100",
    18: "1/120", 19: "1/125", 20: "1/250", 21: "1/500", 22: "1/1000",
    23: "1/2000", 24: "1/4000", 25: "1/8000",
}

# AM7 iris: 27366 = CLOSE, 30975 (F11) .. 32000 (F2.8), 1 unit = 1/256 EV.
# The UI slider maps to 0..1025 (0=CLOSE, 1025=F2.8) to avoid a dead zone.
AM7_IRIS_CLOSE = 27366
AM7_IRIS_MIN = 30975
AM7_IRIS_MAX = 32000
AM7_IRIS_SPAN = AM7_IRIS_MAX - AM7_IRIS_MIN  # 1025

_IRIS_STD = (2.8, 3.2, 3.5, 4.0, 4.5, 5.0, 5.6, 6.3, 7.1, 8.0, 9.0, 10.0,
             11.0, 13.0, 14.0, 16.0, 18.0, 20.0, 22.0)


def am7_iris_to_cam(slider_v) -> int:
    v = int(slider_v)
    return AM7_IRIS_CLOSE if v <= 0 else AM7_IRIS_MIN + min(v, AM7_IRIS_SPAN)


def am7_iris_from_cam(cam_v) -> int:
    try:
        cam_v = int(cam_v)
    except (ValueError, TypeError):
        return 0
    return 0 if cam_v <= AM7_IRIS_CLOSE + 34 else max(1, min(AM7_IRIS_SPAN, cam_v - AM7_IRIS_MIN))


def am7_iris_label(slider_v) -> str:
    try:
        v = int(slider_v)
    except (ValueError, TypeError):
        return "?"
    if v <= 0:
        return "CLOSE"
    f = 2.8 * 2 ** ((AM7_IRIS_SPAN - min(v, AM7_IRIS_SPAN)) / 512.0)
    best = min(_IRIS_STD, key=lambda x: abs(x - f))
    return f"F{best:g}"
