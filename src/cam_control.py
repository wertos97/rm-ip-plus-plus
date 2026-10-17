"""Sterowanie kamera Sony (SRG-X400/BRC) przez udokumentowane CGI.

Zweryfikowane na zywo na SRG-X400 (HTTP digest auth):
odczyt pozycji, RelativePanTilt, Move/stop, presety, imaging - wszystko 200/204.
"""
from __future__ import annotations

import requests
from requests.auth import HTTPDigestAuth

TIMEOUT = 8
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
}


def _to_signed(hex4: str) -> int:
    v = int(hex4, 16)
    return v - 0x10000 if v >= 0x8000 else v


class CameraAPI:
    def __init__(self, ip: str, user: str, password: str, http_port: int = 80):
        self.ip = ip
        self.user = user
        self.password = password
        self.http_port = http_port

    def base(self) -> str:
        return f"http://{self.ip}:{self.http_port}"

    def _get(self, path: str, timeout: float = TIMEOUT):
        return requests.get(self.base() + path, headers={**BROWSER_HEADERS, "Referer": self.base() + "/"},
                            auth=HTTPDigestAuth(self.user, self.password), timeout=timeout)

    def cmd(self, cgi: str, query: str, timeout: float = TIMEOUT) -> tuple[bool, str]:
        """Wysyla command/xxx.cgi?... Zwraca (ok, tekst). 200/204 = ok."""
        try:
            r = self._get(f"/command/{cgi}?{query}", timeout=timeout)
            if r.status_code in (200, 204):
                return True, r.text.strip()
            if r.status_code == 401:
                return False, "401 - zly login/haslo."
            return False, f"HTTP {r.status_code}: {r.text[:150]}"
        except Exception as e:
            return False, str(e)[:200]

    @staticmethod
    def parse_kv(text: str) -> dict:
        out: dict[str, str] = {}
        for chunk in text.replace("\n", "&").split("&"):
            if "=" in chunk:
                k, v = chunk.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def inquiry(self, what: str) -> tuple[bool, dict | str]:
        ok, txt = self.cmd("inquiry.cgi", f"inq={what}")
        if not ok:
            return False, txt
        return True, self.parse_kv(txt)

    # ---------- PTZ ----------
    def move(self, direction: str, speed: int) -> tuple[bool, str]:
        """direction: left/right/up/down/up-left/... speed 0-24 (0=auto wg zoom).
        25+ to zakres serwisowy - przycinamy zeby nie psuc ruchu."""
        return self.cmd("ptzf.cgi", f"Move={direction},{max(0, min(24, int(speed)))}")

    def zoom_move(self, direction: str, speed: int) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", f"Move={direction},{int(speed)}")  # tele/wide 0-8

    def focus_move(self, direction: str, speed: int = 4) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", f"Move={direction},{int(speed)}")  # near/far/onepushaf

    def stop(self, what: str = "pantilt") -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", f"Move=stop,{what}")

    def stop_all(self):
        for w in ("pantilt", "zoom", "focus"):
            self.stop(w)

    def cancel(self):
        return self.cmd("ptzf.cgi", "Cancel=on")

    def home(self):
        return self.cmd("presetposition.cgi", "HomePos=recall")

    def relative_pt(self, pan_hex: str, tilt_hex: str, speed: int) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", f"RelativePanTilt={pan_hex},{tilt_hex},{int(speed)}")

    def relative_zoom(self, delta_hex: str) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", f"RelativeZoom={delta_hex}")

    def absolute_zoom(self, pos_hex: str) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", f"AbsoluteZoom={pos_hex}")

    def absolute_ptzf(self, pan: str, tilt: str, zoom: str, focus: str) -> tuple[bool, str]:
        """Ruch absolutny PTZ+F - nie rusza imaging (ekspozycja/WB/kolory)."""
        return self.cmd("ptzf.cgi", f"AbsolutePTZF={pan},{tilt},{zoom},{focus}")

    def slow_mode(self, on: bool) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", f"SlowPanTiltMode={'on' if on else 'off'}")

    def status(self) -> tuple[bool, dict | str]:
        return self.inquiry("ptzf")

    # ---------- presety ----------
    def preset_list(self) -> tuple[bool, dict]:
        """Zwraca {num: name} dla zdefiniowanych (parsuje PresetName=1,Preset1,2,...)."""
        ok, data = self.inquiry("presetposition")
        if not ok:
            return False, {}
        names: dict[int, str] = {}
        raw = data.get("PresetName", "") if isinstance(data, dict) else ""
        parts = [p.strip() for p in raw.split(",")]
        for i in range(0, len(parts) - 1, 2):
            try:
                names[int(parts[i])] = parts[i + 1]
            except ValueError:
                continue
        return True, names

    def preset_recall(self, num: int, speed: int | None = None) -> tuple[bool, str]:
        q = f"PresetCall={int(num)}" + (f",{int(speed)}" if speed else "")
        return self.cmd("presetposition.cgi", q)

    def preset_set(self, num: int, name: str = "", thumb: str = "on") -> tuple[bool, str]:
        return self.cmd("presetposition.cgi", f"PresetSet={int(num)},{name},{thumb}")

    def thumb(self, num: int, timeout: float = TIMEOUT) -> bytes | None:
        """Miniaturka presetu z kamery (64x36!) albo None. Slabe - wole still()."""
        try:
            r = requests.get(f"{self.base()}/preset/presetimg{int(num)}.jpg",
                             headers={**BROWSER_HEADERS, "Referer": self.base() + "/"},
                             auth=HTTPDigestAuth(self.user, self.password), timeout=timeout)
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image"):
                return r.content
        except Exception:
            pass
        return None

    def still(self, timeout: float = TIMEOUT) -> bytes | None:
        """Pelen kadr JPEG (aktualny obraz) - do ostrych miniaturek."""
        for path in ("/oneshotimage1", "/oneshotimage2"):
            try:
                r = requests.get(f"{self.base()}{path}",
                                 headers={**BROWSER_HEADERS, "Referer": self.base() + "/"},
                                 auth=HTTPDigestAuth(self.user, self.password), timeout=timeout)
                if r.status_code == 200 and len(r.content) > 10000:
                    return r.content
            except Exception:
                continue
        return None

    def preset_clear(self, num: int) -> tuple[bool, str]:
        return self.cmd("presetposition.cgi", f"PresetClear={int(num)}")

    def preset_rename(self, num: int, name: str) -> tuple[bool, str]:
        return self.cmd("presetposition.cgi", f"PresetName={int(num)},{name}")

    def preset_speed_mode(self, mode: str, common: int = 4) -> tuple[bool, str]:
        """mode: compatible/separate/common."""
        ok, m = self.cmd("presetposition.cgi", f"SpeedSelect={mode}")
        if not ok:
            return ok, m
        if mode == "common":
            return self.cmd("presetposition.cgi", f"CommonSpeed={int(common)}")
        return True, m

    # ---------- obraz ----------
    def imaging(self) -> tuple[bool, dict | str]:
        return self.inquiry("imaging")

    def set_imaging(self, **params) -> tuple[bool, str]:
        q = "&".join(f"{k}={v}" for k, v in params.items())
        return self.cmd("imaging.cgi", q)

    def wb_onepush(self):
        return self.cmd("imaging.cgi", "WhiteBalanceOnePushTrg=on")
