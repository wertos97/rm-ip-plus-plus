"""HTTP CGI client for Sony SRG-X400 / BRC-X400 / BRC-AM7 - read only.

The app only detects cameras and opens connections to them (web tabs).
Writing (network.cgi) and VISCA control are out of scope.

Read:
  GET /command/inquiry.cgi?inq=network  -> network parameters / model
Authentication: digest (default admin/admin).
"""
from __future__ import annotations

import requests
from requests.auth import HTTPDigestAuth

DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
TIMEOUT = 6

# Fields present in a real inquiry.cgi?inq=network reply (SRG/BRC).
# HTTP 200 with "key=value" alone is not enough - a hotel router or Synology NAS
# answer the same way, and their HTML contains accidental key=value pairs.
SONY_NET_KEYS = {"ipaddress", "subnetmask", "defaultgateway", "dhcp", "dns",
                 "hostname", "modelname", "cameraname", "macaddress", "mac",
                 "serialnumber", "deviceuniqueid", "softversion"}


class SonyCamera:
    def __init__(self, ip: str, user: str = DEFAULT_USER, password: str = DEFAULT_PASSWORD,
                 http_port: int = 80):
        self.ip = ip
        self.user = user
        self.password = password
        self.http_port = http_port

    def base(self) -> str:
        return f"http://{self.ip}:{self.http_port}"

    def web_url(self) -> str:
        return f"{self.base()}/"

    BROWSER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
    }

    def _get(self, path: str, timeout: float = TIMEOUT):
        # browser headers are required - without them the camera returns 403
        return requests.get(self.base() + path, headers={**self.BROWSER_HEADERS, "Referer": self.base() + "/"},
                            auth=HTTPDigestAuth(self.user, self.password), timeout=timeout)

    def ping_http(self) -> tuple[bool, str]:
        try:
            r = self._get("/")
            return True, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)[:200]

    @staticmethod
    def _model_from_uid(uid: str) -> str:
        """'SRG-X400-03202816' -> 'SRG-X400' (strips the numeric serial)."""
        parts = (uid or "").split("-")
        if len(parts) >= 2 and parts[-1].strip().isdigit():
            return "-".join(parts[:-1])
        return uid

    def get_network(self, timeout: float = TIMEOUT) -> tuple[bool, dict | str]:
        """Queries inquiry.cgi?inq=network, parses it into a dict (for identification)."""
        try:
            r = self._get("/command/inquiry.cgi?inq=network", timeout=timeout)
            if r.status_code == 401:
                return False, "401 Unauthorized - wrong login/password (default admin/admin)."
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}: {r.text[:300]}"
            out: dict[str, str] = {}
            for line in r.text.replace(",", "\n").replace("&", "\n").splitlines():
                line = line.strip().strip("<>").strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip("'\"")
            # hardware model from the license: DeviceUniqueId="SRG-X400-03202816"
            try:
                rl = self._get("/command/inquiry.cgi?inqjs=license", timeout=timeout)
                if rl.status_code == 200:
                    for line in rl.text.replace(",", "\n").splitlines():
                        if "DeviceUniqueId" in line and "=" in line:
                            uid = line.split("=", 1)[1].strip().strip("'\"")
                            out["DeviceUniqueId"] = uid
                            out["ModelName"] = self._model_from_uid(uid)
                            break
            except Exception:
                pass
            if "ModelName" not in out:
                # BRC-AM7 has no inqjs=license - model from inq=viewermode (CGI 2.0)
                try:
                    rv = self._get("/command/inquiry.cgi?inq=viewermode", timeout=timeout)
                    if rv.status_code == 200:
                        for line in rv.text.replace(",", "\n").replace("&", "\n").splitlines():
                            if "ModelName" in line and "=" in line:
                                out["ModelName"] = line.split("=", 1)[1].strip().strip("'\"")
                                if out["ModelName"]:
                                    break
                except Exception:
                    pass
            if not any(k.lower() in SONY_NET_KEYS for k in out):
                return False, ("HTTP 200, but no Sony reply fields (not a "
                               "camera - e.g. router, NAS, captive portal).")
            return True, out
        except Exception as e:
            return False, str(e)[:300]
