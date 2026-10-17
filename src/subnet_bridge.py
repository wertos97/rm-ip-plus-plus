"""Most sieciowy: PC zostaje w swojej sieci (WiFi+internet), a kamery w obcej.

Jak to dziala:
- Nigdy nie ruszamy bramy WiFi ani domyslnego routingu. Na karcie od kamer
  (Ethernet) dodajemy TYLKO secondary IP z SkipAsSource i BEZ bramy.
- Jesli kamera jest w znanej podsieci (192.168.0.x) - wystarczy jeden temp IP.
- Jesli jest w LOSOWEJ podsieci - probujemy ja odgadnac bez zgadywania:
  1) SSDP/UPnP M-SEARCH na multicast 239.255.255.250:1900 - kamera odpowiada
     pakietem z naglowkiem LOCATION: http://<jej-IP>:... nawet gdy PC nie ma
     adresu w jej podsieci (multicast dziala na L2). Stary RM Tool tak wykrywa.
  2) Tablica ARP sasiadow na danym interfejsie - nowe wpisy = kandydaci.
  3) Dopiero potem dobieramy secondary IP w tej samej /24 i laczymy sie normalnie.

Wymaganie: link L1 musi byc UP (kabel + zasilanie kamery). Bez linku most nie zadziala.
"""
from __future__ import annotations

import re
import socket
import struct
import subprocess
import urllib.parse
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900


def _run(cmd: list[str], timeout: int = 15):
    return subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=timeout)
# tylko typowe dla kamer / broadcast - nie skanujemy calego internetu
COMMON_CAMERA_SUBNETS = [
    "192.168.0", "192.168.1", "192.168.10", "192.168.100",
    "10.0.0", "10.1.1", "172.16.0",
]
LIKELY_HOSTS = [".100", ".101", ".1", ".10", ".11", ".120", ".50"]


def ssdp_search(timeout: float = 4.0) -> list[dict]:
    """Wysyla M-SEARCH, zbiera odpowiedzi. Zwraca [{ip, location, st, usn}]."""
    msg = ("\r\n".join([
        "M-SEARCH * HTTP/1.1",
        f"HOST: {SSDP_ADDR}:{SSDP_PORT}",
        'MAN: "ns:01"',
        "MX: 2",
        "ST: ssdp:all",
        "", ""])).encode()
    found: list[dict] = []
    seen: set[str] = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        # TTL lokalny + broadcast tez dla starszych kamer
        ttl = struct.pack("b", 2)
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        except Exception:
            pass
        try:
            sock.sendto(msg, (SSDP_ADDR, SSDP_PORT))
        except Exception:
            pass
        try:
            sock.sendto(msg, ("255.255.255.255", SSDP_PORT))
        except Exception:
            pass
        import time
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            except Exception:
                break
            try:
                text = data.decode("utf-8", "ignore")
            except Exception:
                continue
            loc = ""
            st = ""
            for line in text.splitlines():
                if line.lower().startswith("location:"):
                    loc = line.split(":", 1)[1].strip()
                elif line.lower().startswith("st:"):
                    st = line.split(":", 1)[1].strip()
            ip = addr[0]
            # LOCATION jest pewniejsze niz adres nadawcy (proxy/NAT)
            if loc:
                try:
                    host = urllib.parse.urlparse(loc).hostname
                    if host:
                        ip = host
                except Exception:
                    pass
            key = f"{ip}|{loc}"
            if ip and key not in seen:
                seen.add(key)
                found.append({"ip": ip, "location": loc, "st": st, "via": "ssdp"})
    finally:
        sock.close()
    return found


def arp_candidates(interface_alias: str | None = None) -> list[dict]:
    """Kandydaci z tablicy ARP (parsowanie `arp -a` - pokazuje tez INTERFEJS).

    Dziala dla obcych podsieci: wpis 192.168.4.101 pod interfejsem WiFi oznacza,
    ze kamera jest w zasiegu sieci korporacyjnej bez zadnych zmian w PC.
    """
    out: list[dict] = []
    try:
        p = _run(["arp", "-a"], timeout=15)
        cur_iface = ""
        for line in (p.stdout or "").splitlines():
            m = re.match(r"\s*Interface:\s+(\S+)\s+---", line)
            if m:
                cur_iface = m.group(1)
                continue
            m = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})\s+(\w+)", line)
            if not m:
                continue
            ip, mac, dtype = m.group(1), m.group(2), m.group(3)
            if ip.endswith(".255") or ip.startswith(("224.", "239.", "255.", "0.")):
                continue
            if mac.lower().startswith("01-00-5e") or mac.lower() == "ff-ff-ff-ff-ff-ff":
                continue
            if interface_alias and cur_iface and interface_alias not in cur_iface and cur_iface not in interface_alias:
                # dopasowanie po aliasie LUB adresie (arp podaje adres interfejsu)
                alias_match = False
                try:
                    for a in list_ipv4_addresses():
                        if a["alias"] == interface_alias and a["ip"] == cur_iface:
                            alias_match = True
                except Exception:
                    pass
                if not alias_match:
                    continue
            out.append({"ip": ip, "mac": mac, "state": dtype, "via": "arp", "iface": cur_iface})
    except Exception:
        pass
    return out


def subnet_of(ip: str, prefix: int = 24) -> str:
    parts = ip.split(".")
    n = prefix // 8
    return ".".join(parts[:n])


def bridge_ip_for(target_ip: str, prefix: int = 24, host: int = 200) -> str:
    """Jaki secondary IP dolozyc zeby widziec target (ta sama /24, host .200)."""
    base = subnet_of(target_ip, prefix)
    # jesli target sam jest .200, wez .201 zeby nie kolidowac
    if target_ip == f"{base}.{host}":
        host = 201
    return f"{base}.{host}"


def guess_homes(candidates: list[dict]) -> list[str]:
    """Z kandydatow (ssdp/arp) wyciagn Rudzial liste baz /24 do dobudowy mostu."""
    homes: list[str] = []
    for c in candidates:
        ip = c.get("ip", "")
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
            b = subnet_of(ip)
            if b not in homes:
                homes.append(b)
    return homes
