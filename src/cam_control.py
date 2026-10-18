"""Sterowanie kamera Sony (SRG-X400/BRC-X400/BRC-AM7) przez udokumentowane CGI.

SRG-X400 / BRC-X400: zweryfikowane na zywo (HTTP digest auth) - Move/stop,
RelativePanTilt, presety, imaging.
BRC-AM7: mapowanie wg "CGI Command List" v2.0 - PanTiltMove/ZoomMove/
PanTiltSpeedMode/AbsoluteFocus (kroki), 20-bitowe koordynaty, inne jednostki
imaging. Wykrywanie modelu automatyczne (inq=viewermode -> ModelName).
"""
from __future__ import annotations

import requests
from requests.auth import HTTPDigestAuth

try:
    from .human import AM7_IRIS_CLOSE, AM7_IRIS_MIN, AM7_IRIS_MAX
except ImportError:  # uruchomienie bez pakietu
    from human import AM7_IRIS_CLOSE, AM7_IRIS_MIN, AM7_IRIS_MAX  # noqa: E402

TIMEOUT = 8
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
}

# BRC-AM7
AM7_STEP_SCALE = 5.5          # krok UI (16-bit SRG) -> 20-bit 1/1000° (AM7)
AM7_WB_MODES = ("atw", "memory_a", "preset")


def rel16(v: int) -> str:
    """Wzgledna wartosc PT dla SRG (16-bit, hex 4 cyfry)."""
    return f"{v & 0xFFFF:04x}"


def rel20(v: int) -> str:
    """Wzgledna wartosc PT dla BRC-AM7 (20-bit, hex 5 cyfr)."""
    return f"{v & 0xFFFFF:05x}"


def _to_signed(hex4: str) -> int:
    v = int(hex4, 16)
    return v - 0x10000 if v >= 0x8000 else v


class CameraAPI:
    def __init__(self, ip: str, user: str, password: str, http_port: int = 80):
        self.ip = ip
        self.user = user
        self.password = password
        self.http_port = http_port
        self._family: str | None = None      # 'srg' | 'am7' | None (auto)
        self._family_try = 0.0
        self._speedstep: str | None = None   # AM7: normal/extended
        self._focus_val: int | None = None   # AM7: cache pozycji focus
        self._focus_t = 0.0

    # ---------- wykrywanie modelu ----------
    @property
    def family(self) -> str:
        """'srg' (SRG/BRC-X400...) albo 'am7' (BRC-AM7). Detekcja raz na sesje."""
        if self._family:
            return self._family
        import time
        now = time.monotonic()
        if now - self._family_try < 30.0:
            return "srg"  # kamera milczy - nie cache'ujemy, ponowimy za chwile
        self._family_try = now
        ok, data = self.inquiry("viewermode", timeout=3)
        if ok and isinstance(data, dict):
            # kamera odpowiedziala na viewermode -> to nie AM7, chyba ze model mowi inaczej
            name = (data.get("ModelName") or "").upper()
            self._family = "am7" if "AM7" in name else "srg"
            if self._family == "am7":
                self._read_speedstep()
        return self._family or "srg"

    def _read_speedstep(self):
        """AM7: krok predkosci PT (normal=24, extended=127; fabrycznie extended)."""
        ok, pt = self.inquiry("ptzf", timeout=3)
        if ok and isinstance(pt, dict):
            v = (pt.get("PanTiltSpeedStep") or "").lower()
            if v in ("normal", "extended"):
                self._speedstep = v
                return
        self._speedstep = "extended"

    def _speed_for_ui(self, ui_speed: int) -> int:
        """Skaluje predkosc UI (0-24, jak SRG) na skale BRC-AM7."""
        v = max(0, min(24, int(ui_speed)))
        if self.family == "am7" and self._speedstep != "normal":
            return max(0, min(127, round(v * 127 / 24)))
        return v

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
                return False, "401 - wrong login/password."
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

    def inquiry(self, what: str, timeout: float = TIMEOUT) -> tuple[bool, dict | str]:
        ok, txt = self.cmd("inquiry.cgi", f"inq={what}", timeout=timeout)
        if not ok:
            return False, txt
        return True, self.parse_kv(txt)

    # ---------- PTZ ----------
    def move(self, direction: str, speed: int) -> tuple[bool, str]:
        """direction: left/right/up/down/up-left/... speed 0-24 (0=auto wg zoom).
        25+ to zakres serwisowy - przycinamy zeby nie psuc ruchu."""
        if self.family == "am7":
            sp = self._speed_for_ui(speed)
            return self.cmd("ptzf.cgi", f"PanTiltMove={direction},{sp},{sp}")
        return self.cmd("ptzf.cgi", f"Move={direction},{max(0, min(24, int(speed)))}")

    def zoom_move(self, direction: str, speed: int) -> tuple[bool, str]:
        if self.family == "am7":
            v = max(0, min(8, int(speed)))
            sp = int(round(32766 * (v / 8.0) ** 2))  # kwadratowo: precyzja na dole
            return self.cmd("ptzf.cgi", f"ZoomMove={direction},{sp}")
        return self.cmd("ptzf.cgi", f"Move={direction},{int(speed)}")  # tele/wide 0-8

    def focus_move(self, direction: str, speed: int = 4) -> tuple[bool, str]:
        if self.family == "am7":
            if direction == "onepushaf":
                return self.one_push_af_press()
            # BRC-AM7 nie ma ciaglego ruchu focus - UI kroczkuje przez focus_step()
            return False, "BRC-AM7: no continuous focus (Near/Far steps)."
        return self.cmd("ptzf.cgi", f"Move={direction},{int(speed)}")  # near/far/onepushaf

    def focus_step(self, direction: str, step: int = 0x0400, timeout: float = 2.0) -> tuple[bool, str]:
        """BRC-AM7: krok ostrosci przez AbsoluteFocus (near=+, far=-)."""
        import time
        now = time.monotonic()
        if self._focus_val is None or now - self._focus_t > 1.5:
            ok, pt = self.inquiry("ptzf", timeout=timeout)
            if not ok or not isinstance(pt, dict):
                return False, str(pt)[:120]
            parts = (pt.get("AbsolutePTZF") or "").split(",")
            if len(parts) < 4:
                return False, "no AbsolutePTZF in the reply"
            try:
                self._focus_val = int(parts[3], 16)
            except ValueError:
                return False, "bad focus value"
            self._focus_t = now
        d = step if direction == "near" else -step
        val = max(0, min(0xF7FF, self._focus_val + d))
        if val == self._focus_val:
            return True, "end of range"
        ok, msg = self.cmd("ptzf.cgi", f"AbsoluteFocus={val:04x}")
        if ok:
            self._focus_val = val
            self._focus_t = time.monotonic()
        return ok, msg

    def one_push_af_press(self) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", "FocusPushAFMF=press")

    def one_push_af_release(self) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", "FocusPushAFMF=release")

    def stop(self, what: str = "pantilt") -> tuple[bool, str]:
        if self.family == "am7":
            if what == "focus":
                return True, ""  # focus kroczy - nie ma czego zatrzymywac
            tests = ("ZoomMove=stop", "ZoomMove=stop,0") if what == "zoom" \
                else ("PanTiltMove=stop", "PanTiltMove=stop,0,0")
            last: tuple[bool, str] = (False, "?")
            for q in tests:  # kamera moze wymagac wartosci predkosci - probujemy oba warianty
                last = self.cmd("ptzf.cgi", q)
                if last[0]:
                    return last
            if what != "zoom":
                return self.cancel()
            return last
        return self.cmd("ptzf.cgi", f"Move=stop,{what}")

    def stop_all(self):
        for w in ("pantilt", "zoom", "focus"):
            self.stop(w)

    def cancel(self):
        return self.cmd("ptzf.cgi", "Cancel=on")

    def home(self):
        return self.cmd("presetposition.cgi", "HomePos=recall")

    def relative_pt(self, pan_hex: str, tilt_hex: str, speed: int) -> tuple[bool, str]:
        if self.family == "am7":
            return self.cmd("ptzf.cgi",
                            f"RelativePanTilt={pan_hex},{tilt_hex},{max(1, self._speed_for_ui(speed) or 1)}")
        return self.cmd("ptzf.cgi", f"RelativePanTilt={pan_hex},{tilt_hex},{int(speed)}")

    def relative_zoom(self, delta_hex: str) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", f"RelativeZoom={delta_hex}")

    def absolute_zoom(self, pos_hex: str) -> tuple[bool, str]:
        return self.cmd("ptzf.cgi", f"AbsoluteZoom={pos_hex}")

    def absolute_ptzf(self, pan: str, tilt: str, zoom: str, focus: str) -> tuple[bool, str]:
        """Ruch absolutny PTZ+F - nie rusza imaging (ekspozycja/WB/kolory)."""
        return self.cmd("ptzf.cgi", f"AbsolutePTZF={pan},{tilt},{zoom},{focus}")

    def slow_mode(self, on: bool) -> tuple[bool, str]:
        if self.family == "am7":
            return self.cmd("ptzf.cgi", f"PanTiltSpeedMode={'slow' if on else 'normal'}")
        return self.cmd("ptzf.cgi", f"SlowPanTiltMode={'on' if on else 'off'}")

    def set_focus_mode(self, mode: str) -> tuple[bool, str]:
        if self.family == "am7":
            return self.cmd("ptzf.cgi", f"FocusMode={mode}")  # AM7: item w ptzf.cgi
        return self.set_imaging(FocusMode=mode)

    def status(self, timeout: float = TIMEOUT) -> tuple[bool, dict | str]:
        return self.inquiry("ptzf", timeout=timeout)

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
        if self.family == "am7":
            # AM7: PresetCall przyjmuje tylko numer (predkosc ustawia sie osobno)
            return self.cmd("presetposition.cgi", f"PresetCall={int(num)}")
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
        if self.family == "am7":
            return self.cmd("imaging.cgi", "WhiteBalanceWBSet=press")
        return self.cmd("imaging.cgi", "WhiteBalanceOnePushTrg=on")

    def wb_onepush_release(self):
        """BRC-AM7: konczy 'press' przycisku WB Set (momentary)."""
        return self.cmd("imaging.cgi", "WhiteBalanceWBSet=release")

    # ---------- BRC-AM7: ekspozycja i balans bieli bez ExposureMode ----------
    def set_exposure_am7(self, mode: str, iris: int, gain: int, shut: int, comp: int) -> tuple[bool, str]:
        """Mapuje tryb SRG (auto/shutter/iris/manual) na przelaczniki AM7.

        auto    -> AutoShutter on, AutoIris on,  AGC on
        shutter -> AutoShutter off, AutoIris on,  AGC on  (priorytet migawki)
        iris    -> AutoShutter on,  AutoIris off, AGC on  (priorytet przyslony)
        manual  -> wszystko off
        iris/gain/migawka wysylamy tylko tam, gdzie funkcja auto jest wylaczona.
        """
        auto_shutter = mode in ("auto", "iris")
        auto_iris = mode in ("auto", "shutter")
        agc = mode != "manual"
        ok, msg = self.cmd("imaging.cgi", "ExposureAutoShutterEnable={}&ExposureAutoIris={}&ExposureAGCEnable={}".format(
            "on" if auto_shutter else "off", "on" if auto_iris else "off", "on" if agc else "off"))
        if not ok:
            return ok, msg
        q = f"ExposureCompensation={int(comp)}"
        if not auto_iris:
            v = int(iris)
            v = AM7_IRIS_CLOSE if v <= AM7_IRIS_CLOSE + 34 else min(AM7_IRIS_MAX, max(AM7_IRIS_MIN, v))
            q += f"&ExposureIris={v}"
        if not agc:
            q += f"&ExposureGain={int(gain)}"
        if not auto_shutter:
            q += f"&ExposureExposureTime={int(shut)}"
        return self.cmd("imaging.cgi", q)

    def set_wb_am7(self, mode: str, cb: int, cr: int, offset: int) -> tuple[bool, str]:
        """atw/memory_a/preset; CbGain/CrGain tylko w memory_a, offset tylko w atw."""
        mode = mode if mode in AM7_WB_MODES else "atw"
        q = f"WhiteBalanceMode={mode}"
        if mode == "memory_a":
            q += f"&WhiteBalanceCbGain={int(cb)}&WhiteBalanceCrGain={int(cr)}"
        elif mode == "atw":
            q += f"&WhiteBalanceOffsetColorTemp={int(offset)}"
        return self.cmd("imaging.cgi", q)
