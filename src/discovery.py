"""Camera discovery: fast path for a direct cable + subnet sweep with progress."""
from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from .sony_client import SonyCamera
except ImportError:
    from sony_client import SonyCamera  # noqa: E402

LIKELY_DEFAULTS = ["192.168.0.100", "192.168.0.101", "192.168.0.1",
                   "192.168.0.10", "192.168.0.11", "192.168.0.120"]
VISCA_TCP_PORT = 52381


def tcp_open(ip: str, port: int, timeout: float = 0.6, retries: int = 2) -> bool:
    """TCP attempt with retry - the first SYN is often lost on a cold ARP."""
    for _ in range(max(1, retries)):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except Exception:
            continue
    return False


def udp_discover(timeout: float = 2.0, extra_broadcasts=(), log=None) -> list[dict]:
    """Sony UDP 52380 (ENQ:network) - finds cameras even with a different IP (L2)."""
    try:
        from . import sony_udp
    except ImportError:
        import sony_udp  # noqa: E402
    return sony_udp.discover(timeout=timeout, extra_broadcasts=extra_broadcasts,
                             log=log)


def merge_udp(found: list[dict], udp_hits: list[dict]) -> list[dict]:
    """Adds cameras seen over UDP to the TCP probe result.

    A camera in a foreign subnet will not answer TCP, but the UDP broadcast
    finds it - it is listed with http=False and a note so it stays in results.
    """
    out = list(found)
    by_ip = {c["ip"]: c for c in out}
    for u in udp_hits:
        ip = u.get("ip") or u.get("src_ip")
        if not ip:
            continue
        label = u.get("model") or ""
        name = u.get("name") or ""
        if name and name not in label:
            label = f"{label} ({name})" if label else name
        if ip in by_ip:
            cam = by_ip[ip]
            cam["udp"] = u
            if cam.get("model", "?") in ("?", "") and label:
                cam["model"] = label
            continue
        cam = {"ip": ip, "http": False, "http_port": 0, "visca_52381": False,
               "model": label or "?", "udp": u}
        mac = u.get("mac") or ""
        cam["note"] = (f"UDP 52380: MAC {mac} - no HTTP confirmation "
                       "(check subnet/route)") if mac else \
                      "UDP 52380 - no HTTP confirmation (check subnet/route)"
        out.append(cam)
        by_ip[ip] = cam
    return sorted(out, key=lambda d: d["ip"])


def probe_ip(ip: str, user: str = "admin", password: str = "admin",
             cgi_timeout: float = 2.5, creds_list=None) -> dict | None:
    """Fast probe: short parallel TCP, CGI with a shorter timeout (scan does not hang).

    creds_list: optional list of (user, password) to try in order (per-camera
    defaults/saved credentials). Falls back to the user/password arguments.
    """
    http_port = 0
    for p in (80, 8080):
        if tcp_open(ip, p, 0.5):
            http_port = p
            break
    visca = tcp_open(ip, VISCA_TCP_PORT, 0.5)
    if not http_port and not visca:
        return None
    info: dict = {"ip": ip, "http": bool(http_port), "http_port": http_port,
                  "visca_52381": visca, "model": "?"}
    if http_port:
        attempts = list(creds_list) if creds_list else [(user, password)]
        net: dict | str | None = None
        used: tuple[str, str] | None = None
        auth_failed = False
        for (u, p) in attempts:
            cam = SonyCamera(ip, u, p, http_port=http_port)
            ok, data = cam.get_network(timeout=cgi_timeout)
            if ok and isinstance(data, dict):
                net = data
                used = (u, p)
                break
            net = data
            if isinstance(data, str) and "401" in data:
                auth_failed = True
                continue
            break  # timeout/HTTP error - trying more passwords will not help
        if used is not None and isinstance(net, dict):
            model = net.get("ModelName") or net.get("CameraName") or "?"
            cam_name = net.get("CameraName", "")
            if model != "?" and cam_name and cam_name not in model:
                model = f"{model} ({cam_name})"
            info["model"] = model
            info["network"] = net
            info["user"], info["password"] = used
        else:
            # The Sony API did not confirm a camera. Before treating the device as a camera,
            # look for Sony/camera traces in the page title and HTTP headers - otherwise a
            # router/NAS/printer with open HTTP (e.g. MikroTik "RouterOS router
            # configuration page") would end up in the "Devices" list.
            ident = ""
            try:
                import re
                import requests
                r = requests.get(f"http://{ip}:{http_port}/", timeout=cgi_timeout,
                                 allow_redirects=True)
                m = re.search(r"<title>(.*?)</title>", r.text[:8000], re.I | re.S)
                title = m.group(1).strip()[:60] if m else ""
                hdrs = " ".join(f"{k} {v}" for k, v in r.headers.items())
                if re.search(r"sony|srg|snc|ipela|camera|kamera|ptz|visca",
                             f"{title} {hdrs}", re.I):
                    ident = title or "camera (HTTP)"
            except Exception:
                pass
            if ident:
                info["model"] = ident
            elif visca:
                # no HTTP confirmation, but an open VISCA port = almost certainly a camera
                info["model"] = "camera (VISCA 52381)"
                info["note"] = "HTTP did not confirm the model - check the camera HTTP port"
            else:
                return None  # not a camera - do not clutter the device list
            if auth_failed:
                info["auth_failed"] = True
                info["note"] = "Login required - open the camera to enter credentials."
            elif isinstance(net, str) and net and not info.get("note"):
                info["note"] = str(net)[:150]
    elif visca:
        info["note"] = "VISCA:52381 open, HTTP closed (check the camera HTTP port)"
    return info


def probe_many(ips: list[str], user="admin", password="admin",
               max_workers: int = 16, cgi_timeout: float = 2.5,
               progress=None, creds_for=None) -> list[dict]:
    """Parallel probe of an IP list - done in seconds, does not hang the UI."""
    targets = list(dict.fromkeys(ips))
    total = len(targets)
    found = []
    done_n = [0]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(probe_ip, ip, user, password, cgi_timeout,
                          creds_for(ip) if creds_for else None): ip for ip in targets}
        for f in as_completed(futs):
            try:
                hit = f.result()
            except Exception:
                hit = None
            if hit:
                found.append(hit)
            done_n[0] += 1
            if progress:
                try:
                    progress(done_n[0], total)
                except Exception:
                    pass
    return sorted(found, key=lambda d: d["ip"])


def scan_defaults(user="admin", password="admin", creds_for=None) -> list[dict]:
    found = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(probe_ip, ip, user, password, 2.5,
                          creds_for(ip) if creds_for else None): ip for ip in LIKELY_DEFAULTS}
        for f in as_completed(futs):
            hit = f.result()
            if hit:
                found.append(hit)
    return sorted(found, key=lambda d: d["ip"])


def scan_subnet(cidr: str, user="admin", password="admin", max_workers: int = 64,
                progress=None, stop_flag=None, creds_for=None) -> list[dict]:
    """Scan with progress (progress(done,total)) and cancel (stop_flag()->bool)."""
    net = ipaddress.ip_network(cidr, strict=False)
    ips = [str(h) for h in net.hosts()][:512]
    total = len(ips)
    found: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(probe_ip, ip, user, password, 2.5,
                          creds_for(ip) if creds_for else None): ip for ip in ips}
        for f in as_completed(futs):
            if stop_flag and stop_flag():
                for ff in futs:
                    ff.cancel()
                break
            done += 1
            try:
                hit = f.result()
                if hit:
                    found.append(hit)
            except Exception:
                pass
            if progress:
                try:
                    progress(done, total)
                except Exception:
                    pass
    return sorted(found, key=lambda d: d["ip"])
