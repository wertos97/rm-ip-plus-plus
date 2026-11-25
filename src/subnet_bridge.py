"""Network bridge: the PC stays on its own network (Wi-Fi+internet), cameras on another.

How it works:
- We never touch the Wi-Fi gateway or the default routing. On the camera
  adapter (Ethernet) we add ONLY a secondary IP with SkipAsSource and NO gateway.
- If the camera is in a known subnet (192.168.0.x) - one temp IP is enough.
- If it is in a RANDOM subnet - we try to infer it without guessing:
  1) SSDP/UPnP M-SEARCH on multicast 239.255.255.250:1900 - the camera replies
     with a packet carrying LOCATION: http://<its-IP>:... even when the PC has
     no address in its subnet (multicast works on L2). The old RM Tool detects this way.
  2) The neighbor ARP table on the given interface - new entries = candidates.
  3) Only then do we pick a secondary IP in the same /24 and connect normally.

Requirement: the L1 link must be UP (cable + camera power). Without link the bridge will not work.
"""

from __future__ import annotations

import os
import re
import socket
import struct
import subprocess
import urllib.parse

try:
    from .net_manager import list_ipv4_addresses
except ImportError:
    from net_manager import list_ipv4_addresses

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900


def _run(cmd: list[str], timeout: int = 15):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        shell=False,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


# only typical camera/broadcast ones - we do not scan the whole internet
COMMON_CAMERA_SUBNETS = [
    "192.168.0",
    "192.168.1",
    "192.168.10",
    "192.168.100",
    "10.0.0",
    "10.1.1",
    "172.16.0",
]
LIKELY_HOSTS = [".100", ".101", ".1", ".10", ".11", ".120", ".50"]


def ssdp_search(timeout: float = 4.0) -> list[dict]:
    """Sends M-SEARCH, collects replies. Returns [{ip, location, st, usn}]."""
    msg = (
        "\r\n".join(
            ["M-SEARCH * HTTP/1.1", f"HOST: {SSDP_ADDR}:{SSDP_PORT}", 'MAN: "ns:01"', "MX: 2", "ST: ssdp:all", "", ""]
        )
    ).encode()
    found: list[dict] = []
    seen: set[str] = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        # local TTL + broadcast also for older cameras
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
            except TimeoutError:
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
            # LOCATION is more reliable than the sender address (proxy/NAT)
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
    """Read neighbor candidates from the Windows or macOS ARP table."""
    out: list[dict] = []
    try:
        command = ["arp", "-a"] if os.name == "nt" else ["arp", "-an"]
        result = _run(command, timeout=15)
        cur_iface = ""
        for line in (result.stdout or "").splitlines():
            if os.name == "nt":
                header = re.match(r"\s*Interface:\s+(\S+)\s+---", line)
                if header:
                    cur_iface = header.group(1)
                    continue
                match = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})\s+(\w+)", line)
                if not match:
                    continue
                ip, mac, state = match.groups()
            else:
                match = re.match(
                    r"\s*\??\s*\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5})\s+on\s+(\S+)",
                    line,
                )
                if not match:
                    continue
                ip, mac, cur_iface = match.groups()
                state = "reachable"
            if ip.endswith(".255") or ip.startswith(("224.", "239.", "255.", "0.")):
                continue
            normalized_mac = mac.lower().replace(":", "-")
            if normalized_mac.startswith("01-00-5e") or normalized_mac == "ff-ff-ff-ff-ff-ff":
                continue
            if interface_alias and cur_iface and interface_alias not in cur_iface and cur_iface not in interface_alias:
                alias_match = False
                try:
                    for address in list_ipv4_addresses():
                        if address["alias"] == interface_alias and address["ip"] == cur_iface:
                            alias_match = True
                            break
                except Exception:
                    pass
                if not alias_match:
                    continue
            out.append({"ip": ip, "mac": mac, "state": state, "via": "arp", "iface": cur_iface})
    except Exception:
        pass
    return out


def subnet_of(ip: str, prefix: int = 24) -> str:
    parts = ip.split(".")
    n = prefix // 8
    return ".".join(parts[:n])


def bridge_ip_for(target_ip: str, prefix: int = 24, host: int = 200) -> str:
    """Which secondary IP to add so the target is visible (same /24, host .200)."""
    base = subnet_of(target_ip, prefix)
    # if the target itself is .200, use .201 to avoid a conflict
    if target_ip == f"{base}.{host}":
        host = 201
    return f"{base}.{host}"


def guess_homes(candidates: list[dict]) -> list[str]:
    """From candidates (ssdp/arp) extract the list of /24 bases to build the bridge."""
    homes: list[str] = []
    for c in candidates:
        ip = c.get("ip", "")
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
            b = subnet_of(ip)
            if b not in homes:
                homes.append(b)
    return homes
