"""Temporary secondary IPv4 addresses on Windows and macOS.

Addresses never change the default gateway or route. State in the platform cache
directory allows cleanup after a crash.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass

try:
    from .platform_paths import cache_dir
except ImportError:
    from platform_paths import cache_dir

if os.name == "nt":
    STATE_FILE = os.path.join(tempfile.gettempdir(), "rmip_pp_temp_ips.json")
else:
    STATE_FILE = os.path.join(cache_dir(), "temp_ips.json")


@dataclass
class TempIp:
    interface_alias: str
    ip: str
    prefix: int


def is_admin() -> bool:
    if os.name == "nt":
        import ctypes

        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def _run(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        shell=False,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _run_ps(script: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _mask_for_prefix(prefix: int) -> str:
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_admin_macos(command: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    script = " ".join(shlex.quote(argument) for argument in command)
    applescript = f"do shell script {_applescript_string(script)} with administrator privileges"
    return _run(["osascript", "-e", applescript], timeout=timeout)


def list_ipv4_addresses() -> list[dict]:
    if os.name == "nt":
        script = (
            "Get-NetIPAddress -AddressFamily IPv4 | "
            "Select-Object InterfaceAlias,IPAddress,PrefixLength | ConvertTo-Json"
        )
        try:
            result = _run_ps(script)
            if not result.stdout.strip():
                return []
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            return [
                {
                    "alias": item.get("InterfaceAlias", "?"),
                    "ip": item.get("IPAddress", "?"),
                    "prefix": int(item.get("PrefixLength", 24)),
                }
                for item in data
            ]
        except Exception:
            pass
    else:
        try:
            result = _run(["ifconfig", "-a"])
            addresses: list[dict] = []
            interface = ""
            for line in (result.stdout or "").splitlines():
                header = re.match(r"^([A-Za-z0-9]+):", line)
                if header:
                    interface = header.group(1)
                    continue
                match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(\S+)", line)
                if not interface or not match:
                    continue
                ip, mask = match.groups()
                try:
                    if mask.lower().startswith("0x"):
                        prefix = bin(int(mask, 16)).count("1")
                    else:
                        prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
                except ValueError:
                    prefix = 24
                addresses.append({"alias": interface, "ip": ip, "prefix": prefix})
            if addresses:
                return addresses
        except Exception:
            pass
    try:
        return [{"alias": "?", "ip": socket.gethostbyname(socket.gethostname()), "prefix": 24}]
    except Exception:
        return []


def _load_state() -> list[dict]:
    try:
        with open(STATE_FILE, encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_state(items: list[dict]) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as file:
            json.dump(items, file)
    except Exception:
        pass


def _remember(entry: TempIp) -> None:
    items = [
        item for item in _load_state() if (item["interface_alias"], item["ip"]) != (entry.interface_alias, entry.ip)
    ]
    items.append(asdict(entry))
    _save_state(items)


def _forget(alias: str, ip: str) -> None:
    _save_state([item for item in _load_state() if not (item["interface_alias"] == alias and item["ip"] == ip)])


def find_orphans() -> list[dict]:
    """Return remembered addresses that are no longer present on adapters."""
    state = _load_state()
    if not state:
        return []
    live = {(address["alias"], address["ip"]) for address in list_ipv4_addresses()}
    return [item for item in state if (item["interface_alias"], item["ip"]) not in live]


def _ps_add(alias: str, ip: str, prefix: int) -> tuple[bool, str]:
    escaped = alias.replace("'", "''")
    script = (
        f"New-NetIPAddress -InterfaceAlias '{escaped}' -IPAddress '{ip}' "
        f"-PrefixLength {prefix} -SkipAsSource $True -ErrorAction Stop | Out-Null; 'OK'"
    )
    result = _run_ps(script)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode == 0 and ("OK" in output or output == ""):
        return True, "OK"
    if "already" in output.lower() or "istnieje" in output.lower():
        return True, "ALREADY"
    return False, output[:500] or f"exit {result.returncode}"


def _netsh_add(alias: str, ip: str, prefix: int) -> tuple[bool, str]:
    result = _run(
        [
            "netsh",
            "interface",
            "ipv4",
            "add",
            "address",
            f"name={alias}",
            f"addr={ip}",
            f"mask={_mask_for_prefix(prefix)}",
        ]
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode == 0:
        return True, "OK"
    lowered = output.lower()
    if "already exists" in lowered or "istnieje" in lowered:
        return True, "ALREADY"
    return False, output[:500] or f"exit {result.returncode}"


def _elevated_add_windows(alias: str, ip: str, prefix: int) -> tuple[bool, str]:
    script = (
        f"Start-Process netsh -ArgumentList 'interface ipv4 add address "
        f'name="{alias}" addr={ip} mask={_mask_for_prefix(prefix)}\' -Verb RunAs -Wait'
    )
    try:
        _run_ps(script, timeout=60)
        for address in list_ipv4_addresses():
            if address["alias"] == alias and address["ip"] == ip:
                return True, "OK(elevated)"
        return False, "Elevation finished, but the address is not visible. Was UAC denied?"
    except Exception as exc:
        return False, str(exc)[:300]


def _macos_add(alias: str, ip: str, prefix: int) -> tuple[bool, str]:
    command = ["/sbin/ifconfig", alias, "alias", ip, "netmask", _mask_for_prefix(prefix)]
    result = _run(command) if is_admin() else _run_admin_macos(command)
    if result.returncode == 0:
        return True, "OK"
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if "already exists" in output.lower():
        return True, "ALREADY"
    return False, output[:500] or f"exit {result.returncode}"


def add_temp_ip(interface_alias: str, ip: str, prefix: int = 24) -> tuple[bool, str]:
    if os.name == "nt":
        if is_admin():
            ok, message = _ps_add(interface_alias, ip, prefix)
            if ok:
                _remember(TempIp(interface_alias, ip, prefix))
                extra = " (already existed)" if message == "ALREADY" else ""
                return True, f"Added {ip}/{prefix} to '{interface_alias}'{extra} [SkipAsSource]."
            ok, message = _netsh_add(interface_alias, ip, prefix)
            if ok:
                _remember(TempIp(interface_alias, ip, prefix))
                return True, f"Added {ip}/{prefix} to '{interface_alias}' (netsh fallback)."
            return False, f"No rights or error: {message}"
        ok, message = _elevated_add_windows(interface_alias, ip, prefix)
        if ok:
            _remember(TempIp(interface_alias, ip, prefix))
            return True, f"Added {ip}/{prefix} to '{interface_alias}' (UAC elevation)."
        return False, f"Admin rights needed. Accept the UAC prompt. Details: {message}"

    ok, message = _macos_add(interface_alias, ip, prefix)
    if ok:
        _remember(TempIp(interface_alias, ip, prefix))
        extra = " (already existed)" if message == "ALREADY" else ""
        return True, f"Added {ip}/{prefix} to '{interface_alias}'{extra}."
    return False, f"Administrator rights are needed for the network bridge. Details: {message}"


def remove_temp_ip(interface_alias: str, ip: str) -> tuple[bool, str]:
    live = {(address["alias"], address["ip"]) for address in list_ipv4_addresses()}
    if (interface_alias, ip) not in live:
        _forget(interface_alias, ip)
        return True, f"{ip} is already gone from '{interface_alias}'."

    if os.name == "nt":
        if is_admin():
            escaped = interface_alias.replace("'", "''")
            script = (
                f"Remove-NetIPAddress -InterfaceAlias '{escaped}' -IPAddress '{ip}' "
                "-Confirm:$false -ErrorAction SilentlyContinue; 'OK'"
            )
            result = _run_ps(script)
            fallback = _run(
                ["netsh", "interface", "ipv4", "delete", "address", f"name={interface_alias}", f"addr={ip}"]
            )
            gone = all(
                not (address["alias"] == interface_alias and address["ip"] == ip) for address in list_ipv4_addresses()
            )
            if gone:
                _forget(interface_alias, ip)
                return True, f"Removed {ip} from '{interface_alias}'."
            output = (((result.stderr or "") + (fallback.stderr or "")).strip())[:300]
            return False, f"Could not remove {ip}. {output}"
        script = (
            f"Start-Process netsh -ArgumentList 'interface ipv4 delete address "
            f'name="{interface_alias}" addr={ip}\' -Verb RunAs -Wait'
        )
        try:
            _run_ps(script, timeout=60)
        except Exception as exc:
            return False, f"Removal elevation failed: {exc}"[:300]
        gone = all(
            not (address["alias"] == interface_alias and address["ip"] == ip) for address in list_ipv4_addresses()
        )
        if gone:
            _forget(interface_alias, ip)
            return True, f"Removed {ip} from '{interface_alias}' (UAC elevation)."
        return False, f"Removal of {ip} not confirmed. Was UAC denied?"
    else:
        command = ["/sbin/ifconfig", interface_alias, "-alias", ip]
        try:
            result = _run(command) if is_admin() else _run_admin_macos(command)
        except Exception as exc:
            return False, f"Removal elevation failed: {exc}"[:300]
        gone = all(
            not (address["alias"] == interface_alias and address["ip"] == ip) for address in list_ipv4_addresses()
        )
        if gone:
            _forget(interface_alias, ip)
            return True, f"Removed {ip} from '{interface_alias}'."
        output = ((result.stderr or "") + (result.stdout or "")).strip()[:300]
        return False, f"Could not remove {ip}: {output}"


_CLEANED = False
_CLEAN_LOCK = threading.Lock()


def cleanup_all() -> list[str]:
    """Claim and remove remembered temporary addresses once per process."""
    global _CLEANED
    with _CLEAN_LOCK:
        claimed = _load_state()
        _save_state([])
        if not claimed or _CLEANED:
            _CLEANED = True
            return []
        _CLEANED = True
    return [remove_temp_ip(item["interface_alias"], item["ip"])[1] for item in claimed]


def ensure_homes_visible(interface_alias: str, homes: list[str], prefix: int = 24) -> tuple[bool, str]:
    """Add missing secondary addresses, using one elevation prompt."""
    want: list[tuple[str, str]] = []
    for home in dict.fromkeys(homes):
        parts = home.split(".")
        base = ".".join(parts[:3]) if len(parts) == 4 else home
        live = {address["ip"] for address in list_ipv4_addresses() if address["alias"] == interface_alias}
        if any(ip.startswith(base + ".") for ip in live):
            continue
        bridge_ip = f"{base}.200"
        if bridge_ip in live:
            bridge_ip = f"{base}.201"
        want.append((base, bridge_ip))
    if not want:
        return True, "All known subnets are already visible."

    if os.name == "nt":
        if is_admin():
            messages = []
            for _base, bridge_ip in want:
                ok, message = _ps_add(interface_alias, bridge_ip, prefix)
                if ok:
                    _remember(TempIp(interface_alias, bridge_ip, prefix))
                messages.append(message)
            return True, " | ".join(messages)
        mask = _mask_for_prefix(prefix)
        commands = "; ".join(
            f'netsh interface ipv4 add address name="{interface_alias}" addr={bridge_ip} mask={mask}'
            for _, bridge_ip in want
        )
        script = f"Start-Process powershell -ArgumentList '-NoProfile -Command \"{commands}\"' -Verb RunAs -Wait"
        try:
            _run_ps(script, timeout=90)
        except Exception as exc:
            return False, f"Elevation failed: {exc}"[:200]
    else:
        mask = _mask_for_prefix(prefix)
        commands = [["/sbin/ifconfig", interface_alias, "alias", bridge_ip, "netmask", mask] for _, bridge_ip in want]
        try:
            if is_admin():
                for command in commands:
                    result = _run(command)
                    if result.returncode != 0:
                        return False, ((result.stderr or "") + (result.stdout or "")).strip()[:300]
            else:
                script = "; ".join(" ".join(shlex.quote(argument) for argument in command) for command in commands)
                # Run one shell with all commands so the user sees one prompt.
                result = _run_admin_macos(["/bin/sh", "-c", script])
                if result.returncode != 0:
                    return False, ((result.stderr or "") + (result.stdout or "")).strip()[:300]
        except Exception as exc:
            return False, f"Elevation failed: {exc}"[:200]

    live = {(address["alias"], address["ip"]) for address in list_ipv4_addresses()}
    done = [bridge_ip for _, bridge_ip in want if (interface_alias, bridge_ip) in live]
    for _, bridge_ip in want:
        if (interface_alias, bridge_ip) in live:
            _remember(TempIp(interface_alias, bridge_ip, prefix))
    if done:
        return True, f"Bridge built ({', '.join(done)}) on '{interface_alias}'."
    return False, "Elevation finished, but the addresses are not visible."


def ensure_subnet_visible(interface_alias: str, subnet_ip: str = "192.168.0.200", prefix: int = 24) -> tuple[bool, str]:
    """Single secondary IP (compatibility)."""
    base = ".".join(subnet_ip.split(".")[: prefix // 8])
    for address in list_ipv4_addresses():
        if address["alias"] == interface_alias and address["ip"].startswith(base + "."):
            return True, f"Adapter '{interface_alias}' already sees {base}.0/{prefix} ({address['ip']})."
    return add_temp_ip(interface_alias, subnet_ip, prefix)


VIRTUAL_HINTS = (
    "bluetooth",
    "loopback",
    "polaczenie lokalne",
    "połączenie lokalne",
    "local area connection",
    "wi-fi direct",
    "wifi direct",
    "direct",
    "virtual",
    "komorkowa",
    "komórkowa",
    "cellular",
    "wwan",
    "remote ndis",
    "vpn",
    "tap-",
    "hyper-v",
    "vmware",
    "virtualbox",
    "utun",
    "awdl",
    "llw",
)


def _norm(value: str) -> str:
    return (
        (value or "")
        .lower()
        .replace("ą", "a")
        .replace("ć", "c")
        .replace("ę", "e")
        .replace("ł", "l")
        .replace("ń", "n")
        .replace("ó", "o")
        .replace("ś", "s")
        .replace("ź", "z")
        .replace("ż", "z")
    )


def is_virtual_alias(alias: str, desc: str = "") -> bool:
    text = _norm(alias) + " " + _norm(desc)
    return any(hint in text for hint in VIRTUAL_HINTS)


def list_adapters() -> list[dict]:
    """All adapters: {alias, status, mediatype, desc, virtual}."""
    if os.name != "nt":
        try:
            result = _run(["networksetup", "-listallhardwareports"])
            ports: list[dict] = []
            current: dict[str, str] = {}
            for line in (result.stdout or "").splitlines():
                if line.startswith("Hardware Port:"):
                    if current.get("device"):
                        ports.append(current)
                    current = {"port": line.split(":", 1)[1].strip()}
                elif line.startswith("Device:"):
                    current["device"] = line.split(":", 1)[1].strip()
                elif line.startswith("Ethernet Address:"):
                    current["mac"] = line.split(":", 1)[1].strip()
            if current.get("device"):
                ports.append(current)
            adapters = []
            for port in ports:
                device = port["device"]
                status = "Down"
                try:
                    detail = _run(["ifconfig", device])
                    if re.search(r"\bstatus:\s*active\b", detail.stdout or "") or "UP" in (
                        next((line for line in (detail.stdout or "").splitlines() if "flags=" in line), "")
                    ):
                        status = "Up"
                except Exception:
                    pass
                name = port.get("port", device)
                adapters.append(
                    {
                        "alias": device,
                        "status": status,
                        "mediatype": name,
                        "desc": name,
                        "virtual": is_virtual_alias(name, device),
                    }
                )
            return adapters
        except Exception:
            return []

    script = "Get-NetAdapter | Select-Object Name,Status,MediaType,InterfaceDescription | ConvertTo-Json"
    try:
        result = _run_ps(script)
        if not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        adapters = []
        for item in data:
            alias = str(item.get("Name", "?"))
            description = str(item.get("InterfaceDescription", ""))
            adapters.append(
                {
                    "alias": alias,
                    "status": str(item.get("Status", "?")),
                    "mediatype": str(item.get("MediaType", "")),
                    "desc": description,
                    "virtual": is_virtual_alias(alias, description),
                }
            )
        return adapters
    except Exception:
        return []


def best_bridge_iface() -> str | None:
    """Choose a physical Ethernet adapter, preferably with link."""
    try:
        adapters = list_adapters()
    except Exception:
        return None
    ethernet = [
        adapter
        for adapter in adapters
        if ("802.3" in adapter["mediatype"] or adapter["mediatype"].lower() == "ethernet") and not adapter["virtual"]
    ]
    for adapter in ethernet:
        if adapter["status"].lower() == "up":
            return adapter["alias"]
    return ethernet[0]["alias"] if ethernet else None


def tcp_reachable(ip: str, timeout: float = 1.0) -> bool:
    for port in (80, 8080):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except Exception:
            continue
    return False


def ensure_reachable(ip: str, prefix: int = 24) -> tuple[bool, str]:
    """Add a temporary address only when the camera is unreachable."""
    if tcp_reachable(ip):
        return True, f"{ip} reachable without changes."
    interface = best_bridge_iface()
    if not interface:
        return False, f"{ip} unreachable and no physical Ethernet for the bridge."
    ok, message = ensure_homes_visible(interface, [ip], prefix)
    if not ok:
        return False, message
    if tcp_reachable(ip, timeout=2.0):
        return True, f"{ip} reachable via the bridge ({message})"
    return False, f"Bridge added ({message}), but {ip} still does not respond."
