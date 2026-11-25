"""Simulated camera for exploring the UI without hardware.

DemoCameraAPI implements the same surface as CameraAPI (SRG family) entirely
in memory: PTZ moves update a virtual position, presets and exposure settings
are stored locally, and still() renders a synthetic frame so preset thumbnails
also work. No sockets, no ports, no camera traffic.
"""

from __future__ import annotations

DEMO_IP = "demo"

# SRG units: pan/tilt 16-bit signed, 1 unit = 1/51.2 deg; zoom 0x4000 = 20x
_PAN_LIMIT = int(170 * 51.2)
_TILT_MIN = int(-20 * 51.2)
_TILT_MAX = int(90 * 51.2)
_ZOOM_MAX = 0x4000
_FOCUS_MAX = 0xF000


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _s16(h) -> int:
    v = int(h, 16) & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def _h16(v: int) -> str:
    return f"{v & 0xFFFF:04x}"


class DemoCameraAPI:
    """Drop-in replacement for CameraAPI backed by local state."""

    family = "srg"

    def __init__(self, ip: str = DEMO_IP, *args, **kwargs):
        self.ip = ip
        self.http_port = 0
        self._pan = 0  # units (signed)
        self._tilt = 0
        self._zoom = 0  # 0..0x4000 -> 1..20x
        self._focus = 0x8000  # mid range
        self._presets: dict[int, dict] = {}
        self._imaging = {
            "ExposureMode": "auto",
            "ExposureIris": 20,  # F3.1
            "ExposureGain": 1,  # 0 dB
            "ExposureExposureTime": 18,  # 1/50
            "ExposureCompensation": 7,  # 0 dB
            "WhiteBalanceMode": "auto",
            "WhiteBalanceCbGain": 128,
            "WhiteBalanceCrGain": 128,
            "WhiteBalanceOffset": 7,
            "FocusMode": "auto",
        }

    def move(self, direction: str, speed: int = 8):
        sp = max(0, min(24, int(speed)))
        step = int((0.8 + 0.35 * sp) * 51.2)
        dp = -step if "left" in direction else (step if "right" in direction else 0)
        dt = -step if "down" in direction else (step if "up" in direction else 0)
        self._pan = _clamp(self._pan + dp, -_PAN_LIMIT, _PAN_LIMIT)
        self._tilt = _clamp(self._tilt + dt, _TILT_MIN, _TILT_MAX)
        return True, ""

    def zoom_move(self, direction: str, speed: int = 3):
        sp = max(0, min(8, int(speed)))
        step = int(_ZOOM_MAX * (0.01 + 0.004 * sp))
        d = -step if direction == "wide" else step
        self._zoom = _clamp(self._zoom + d, 0, _ZOOM_MAX)
        return True, ""

    def focus_move(self, direction: str = "near", speed: int = 4):
        if direction == "onepushaf":
            return self.one_push_af_press()
        d = 400 if direction == "near" else -400
        self._focus = _clamp(self._focus + d, 0, _FOCUS_MAX)
        return True, ""

    def focus_step(self, direction: str = "near", step: int = 0x0400, timeout: float = 2.0):
        d = int(step) if direction == "near" else -int(step)
        self._focus = _clamp(self._focus + d, 0, _FOCUS_MAX)
        return True, ""

    def one_push_af_press(self):
        return True, ""

    def one_push_af_release(self):
        return True, ""

    def stop(self, what: str = "pantilt"):
        return True, ""

    def stop_all(self):
        return True, ""

    def home(self):
        self._pan = 0
        self._tilt = 0
        self._zoom = 0
        return True, ""

    def relative_pt(self, pan_hex: str, tilt_hex: str, speed: int = 5):
        try:
            dp, dt = _s16(pan_hex), _s16(tilt_hex)
        except (ValueError, TypeError):
            return False, "bad relative value"
        self._pan = _clamp(self._pan + dp, -_PAN_LIMIT, _PAN_LIMIT)
        self._tilt = _clamp(self._tilt + dt, _TILT_MIN, _TILT_MAX)
        return True, ""

    def relative_zoom(self, delta_hex: str):
        try:
            self._zoom = _clamp(self._zoom + _s16(delta_hex), 0, _ZOOM_MAX)
        except (ValueError, TypeError):
            return False, "bad zoom value"
        return True, ""

    def absolute_zoom(self, pos_hex: str):
        try:
            self._zoom = _clamp(int(pos_hex, 16), 0, _ZOOM_MAX)
        except (ValueError, TypeError):
            return False, "bad zoom value"
        return True, ""

    def absolute_ptzf(self, pan: str, tilt: str, zoom: str, focus: str):
        try:
            self._pan = _clamp(_s16(pan), -_PAN_LIMIT, _PAN_LIMIT)
            self._tilt = _clamp(_s16(tilt), _TILT_MIN, _TILT_MAX)
            self._zoom = _clamp(int(zoom, 16), 0, _ZOOM_MAX)
            self._focus = _clamp(int(focus, 16), 0, _FOCUS_MAX)
        except (ValueError, TypeError):
            return False, "bad PTZF value"
        return True, ""

    def slow_mode(self, on: bool):
        return True, ""

    def set_focus_mode(self, mode: str):
        self._imaging["FocusMode"] = mode
        return True, ""

    def status(self, timeout: float = 8):
        return True, {
            "AbsolutePTZF": (f"{_h16(self._pan)},{_h16(self._tilt)},{self._zoom:04x},{self._focus:04x}"),
            "PtzfStatus": "idle",
        }

    def _ptzf(self):
        return [_h16(self._pan), _h16(self._tilt), f"{self._zoom:04x}", f"{self._focus:04x}"]

    def preset_list(self, timeout=8):
        return True, {num: p["name"] for num, p in self._presets.items()}

    def preset_recall(self, num: int, speed: int | None = None):
        p = self._presets.get(int(num))
        if not p:
            return False, f"preset {num} is empty"
        self.absolute_ptzf(*p["ptzf"])
        return True, ""

    def preset_set(self, num: int, name: str = "", thumb: str = "on"):
        self._presets[int(num)] = {"name": name or f"Preset{int(num)}", "ptzf": self._ptzf()}
        return True, ""

    def preset_clear(self, num: int):
        self._presets.pop(int(num), None)
        return True, ""

    def preset_rename(self, num: int, name: str):
        p = self._presets.get(int(num))
        if p is None:
            return False, f"preset {num} is empty"
        p["name"] = name
        return True, ""

    def preset_speed_mode(self, mode: str, common: int = 4):
        return True, ""

    def thumb(self, num: int, timeout: float = 8):
        return self.still()

    def imaging(self, timeout=8):
        return True, dict(self._imaging)

    def set_imaging(self, **params):
        for key, value in params.items():
            self._imaging[key] = value
        return True, ""

    def wb_onepush(self):
        return True, ""

    def wb_onepush_release(self):
        return True, ""

    def set_exposure_am7(self, mode: str, iris: int, gain: int, shut: int, comp: int):
        self._imaging.update({"ExposureMode": mode, "ExposureCompensation": comp})
        return True, ""

    def set_wb_am7(self, mode: str, cb: int, cr: int, offset: int):
        self._imaging.update({"WhiteBalanceMode": mode, "WhiteBalanceCbGain": cb, "WhiteBalanceCrGain": cr})
        return True, ""

    def still(self, timeout: float = 8):
        """Render a synthetic JPEG frame reflecting the virtual position."""
        try:
            from PySide6.QtCore import QBuffer
            from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen
        except Exception:
            return None
        if QGuiApplication.instance() is None:
            return None  # drawing requires a Qt application object
        w, h = 640, 360
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(QColor("#0e1114"))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor("#1d2329"), 1))
        for x in range(0, w, 40):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 40):
            p.drawLine(0, y, w, y)
        zx = 1.0 + 19.0 * (self._zoom / _ZOOM_MAX)
        box_w = int(w * 0.55 / max(1.0, zx / 3.0))
        box_h = int(box_w * 9 / 16)
        p.setPen(QPen(QColor("#ff9e2c"), 2))
        p.drawRect((w - box_w) // 2, (h - box_h) // 2, box_w, box_h)
        cx = int(w / 2 + (self._pan / 51.2) / 170.0 * (w / 2 - 40))
        cy = int(h / 2 - (self._tilt / 51.2) / 90.0 * (h / 2 - 40))
        p.setPen(QPen(QColor("#8fce8f"), 2))
        p.drawLine(cx - 18, cy, cx + 18, cy)
        p.drawLine(cx, cy - 18, cx, cy + 18)
        p.setPen(QColor("#f2f2f2"))
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(16, 30, "DEMO CAMERA")
        f2 = QFont("Consolas")
        f2.setPointSize(10)
        p.setFont(f2)
        p.setPen(QColor("#9aa0a6"))
        p.drawText(16, h - 34, f"Pan {self._pan / 51.2:+.1f} deg   Tilt {self._tilt / 51.2:+.1f} deg")
        p.drawText(16, h - 16, f"Zoom {zx:.1f}x   Focus {self._focus:04x}   (simulated)")
        p.end()
        buf = QBuffer()
        buf.open(QBuffer.WriteOnly)
        img.save(buf, "JPG", 82)
        data = bytes(buf.data())
        buf.close()
        return data
