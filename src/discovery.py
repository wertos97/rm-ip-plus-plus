"""Wykrywanie kamer: szybka sciezka dla kabla + sweep podsieci z progressem."""
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
    """Proba TCP z powtorka - pierwszy SYN czesto ginie na zimnym ARP."""
    for _ in range(max(1, retries)):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except Exception:
            continue
    return False


def probe_ip(ip: str, user: str = "admin", password: str = "admin",
             cgi_timeout: float = 2.5) -> dict | None:
    """Szybki probe: TCP rownolegle krotko, CGI z krotszym timeoutem (skan nie wiesza sie)."""
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
        cam = SonyCamera(ip, user, password, http_port=http_port)
        ok, net = cam.get_network(timeout=cgi_timeout)
        if ok and isinstance(net, dict):
            model = net.get("ModelName") or net.get("CameraName") or "?"
            cam_name = net.get("CameraName", "")
            if model != "?" and cam_name and cam_name not in model:
                model = f"{model} ({cam_name})"
            info["model"] = model
            info["network"] = net
        else:
            # fallback: tytul strony glownej (dziala bez logowania, np. 'Sony Network Camera')
            try:
                import re
                import requests
                r = requests.get(f"http://{ip}:{http_port}/", timeout=cgi_timeout)
                m = re.search(r"<title>(.*?)</title>", r.text, re.I | re.S)
                info["model"] = m.group(1).strip()[:60] if m else "?"
            except Exception:
                pass
            if isinstance(net, str) and net:
                info["note"] = str(net)[:150]
    elif visca:
        info["note"] = "VISCA:52381 otwarty, HTTP zamkniete (sprawdz port HTTP w kamerze)"
    return info


def probe_many(ips: list[str], user="admin", password="admin",
               max_workers: int = 16, cgi_timeout: float = 2.5,
               progress=None) -> list[dict]:
    """Rownolegly probe listy IP - calosc w pare sekund, nie wiesza UI."""
    targets = list(dict.fromkeys(ips))
    total = len(targets)
    found = []
    done_n = [0]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(probe_ip, ip, user, password, cgi_timeout): ip for ip in targets}
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


def scan_defaults(user="admin", password="admin") -> list[dict]:
    found = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(probe_ip, ip, user, password): ip for ip in LIKELY_DEFAULTS}
        for f in as_completed(futs):
            hit = f.result()
            if hit:
                found.append(hit)
    return sorted(found, key=lambda d: d["ip"])


def scan_subnet(cidr: str, user="admin", password="admin", max_workers: int = 64,
                progress=None, stop_flag=None) -> list[dict]:
    """Skan z progressem (progress(done,total)) i przerwaniem (stop_flag()->bool)."""
    net = ipaddress.ip_network(cidr, strict=False)
    ips = [str(h) for h in net.hosts()][:512]
    total = len(ips)
    found: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(probe_ip, ip, user, password): ip for ip in ips}
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
