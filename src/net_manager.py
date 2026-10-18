"""Zarzadzanie tymczasowymi adresami IP na Windows.

Kamery Sony fabrycznie siedza w 192.168.0.x, a PC czesto jest gdzie indziej
(10.x / 169.254 APIPA przy kablu bezposrednim). Aplikacja doklada DRUGI
(secondary) adres IP do wybranej karty i usuwa go przy zamknieciu.

v2: dodawanie przez PowerShell New-NetIPAddress -SkipAsSource (nie psuje
domyslnego routingu), usuwanie przez Remove-NetIPAddress, fallback do netsh,
wykrywanie admina + elevacja pojedynczej komendy, wykrywanie sierot po crashu.
"""
from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass

STATE_FILE = os.path.join(tempfile.gettempdir(), "rmip_pp_temp_ips.json")


@dataclass
class TempIp:
    interface_alias: str
    ip: str
    prefix: int


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=timeout)


def _run_ps(script: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-Command", script],
                          capture_output=True, text=True, timeout=timeout)


def list_ipv4_addresses() -> list[dict]:
    ps = ("Get-NetIPAddress -AddressFamily IPv4 | "
          "Select-Object InterfaceAlias,IPAddress,PrefixLength | ConvertTo-Json")
    try:
        p = _run_ps(ps)
        if not p.stdout.strip():
            return []
        data = json.loads(p.stdout)
        if isinstance(data, dict):
            data = [data]
        return [{"alias": d.get("InterfaceAlias", "?"),
                 "ip": d.get("IPAddress", "?"),
                 "prefix": int(d.get("PrefixLength", 24))} for d in data]
    except Exception:
        try:
            return [{"alias": "?", "ip": socket.gethostbyname(socket.gethostname()), "prefix": 24}]
        except Exception:
            return []


def _load_state() -> list[dict]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_state(items: list[dict]) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f)
    except Exception:
        pass


def _remember(e: TempIp) -> None:
    items = [i for i in _load_state() if (i["interface_alias"], i["ip"]) != (e.interface_alias, e.ip)]
    items.append(asdict(e))
    _save_state(items)


def _forget(alias: str, ip: str) -> None:
    _save_state([i for i in _load_state()
                 if not (i["interface_alias"] == alias and i["ip"] == ip)])


def find_orphans() -> list[dict]:
    """Prawdziwe sieroty: zapamietane w pliku, ale juz nieobecne na kartach
    (np. recznie usuniete albo po crashu przy sprzataniu). Wpisy nadal aktywne
    NIE sa siertami - nie pytamy o nie przy starcie."""
    state = _load_state()
    if not state:
        return []
    live = {(a["alias"], a["ip"]) for a in list_ipv4_addresses()}
    return [i for i in state if (i["interface_alias"], i["ip"]) not in live]


def _ps_add(alias: str, ip: str, prefix: int) -> tuple[bool, str]:
    # -SkipAsSource zeby nie zmieniac domyslnego zrodla ruchu PC
    esc = alias.replace("'", "''")
    script = (f"New-NetIPAddress -InterfaceAlias '{esc}' -IPAddress '{ip}' "
              f"-PrefixLength {prefix} -SkipAsSource $True -ErrorAction Stop | Out-Null; 'OK'")
    p = _run_ps(script)
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    if p.returncode == 0 and ("OK" in out or out == ""):
        return True, "OK"
    if "already" in out.lower() or "istnieje" in out.lower():
        return True, "ALREADY"
    return False, out[:500] or f"exit {p.returncode}"


def _netsh_add(alias: str, ip: str, prefix: int) -> tuple[bool, str]:
    mask = {24: "255.255.255.0", 16: "255.255.0.0", 8: "255.0.0.0"}.get(prefix, "255.255.255.0")
    r = _run(["netsh", "interface", "ipv4", "add", "address",
              f"name={alias}", f"addr={ip}", f"mask={mask}"])
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode == 0:
        return True, "OK"
    low = out.lower()
    if "already exists" in low or "istnieje" in low:
        return True, "ALREADY"
    return False, out[:500] or f"exit {r.returncode}"


def _elevated_add(alias: str, ip: str, prefix: int) -> tuple[bool, str]:
    """Jednorazowa elevacja tylko komendy netsh (UAC), bez restartu calej apki.

    Start-Process -Verb RunAs nie zwraca ExitCode (inny proces), wiec nie
    pytamy o ExitCode - odpalamy z -Wait i weryfikujemy skutek na karcie.
    """
    mask = {24: "255.255.255.0", 16: "255.255.0.0", 8: "255.0.0.0"}.get(prefix, "255.255.255.0")
    script = (f"Start-Process netsh -ArgumentList 'interface ipv4 add address "
              f"name=\"{alias}\" addr={ip} mask={mask}' -Verb RunAs -Wait")
    try:
        _run_ps(script, timeout=60)
        # weryfikacja skutku zamiast ExitCode
        for a in list_ipv4_addresses():
            if a["alias"] == alias and a["ip"] == ip:
                return True, "OK(elevated)"
        return False, "elevation done, but the address is not visible on the adapter (UAC denied?)"
    except Exception as e:
        return False, str(e)[:300]


def add_temp_ip(interface_alias: str, ip: str, prefix: int = 24) -> tuple[bool, str]:
    if is_admin():
        ok, msg = _ps_add(interface_alias, ip, prefix)
        if ok:
            _remember(TempIp(interface_alias, ip, prefix))
            extra = " (already existed)" if msg == "ALREADY" else ""
            return True, f"Added {ip}/{prefix} to '{interface_alias}'{extra} [SkipAsSource]."
        ok2, msg2 = _netsh_add(interface_alias, ip, prefix)
        if ok2:
            _remember(TempIp(interface_alias, ip, prefix))
            return True, f"Added {ip}/{prefix} to '{interface_alias}' (netsh fallback)."
        return False, f"No rights or error: {msg} / {msg2}"
    ok, msg = _elevated_add(interface_alias, ip, prefix)
    if ok:
        _remember(TempIp(interface_alias, ip, prefix))
        return True, f"Added {ip}/{prefix} to '{interface_alias}' (UAC elevation)."
    return False, (f"Admin rights needed (UAC). Click again and accept the UAC prompt. Details: {msg}. "
                   f"Or run the app as administrator.")


def remove_temp_ip(interface_alias: str, ip: str) -> tuple[bool, str]:
    live = {(a["alias"], a["ip"]) for a in list_ipv4_addresses()}
    if (interface_alias, ip) not in live:
        # adresu juz nie ma - tylko zapomnij, ZERO UAC
        _forget(interface_alias, ip)
        return True, f"{ip} is already gone from '{interface_alias}' (no UAC)."
    if is_admin():
        esc = interface_alias.replace("'", "''")
        script = (f"Remove-NetIPAddress -InterfaceAlias '{esc}' -IPAddress '{ip}' "
                  f"-Confirm:$false -ErrorAction SilentlyContinue; 'OK'")
        p = _run_ps(script)
        r = _run(["netsh", "interface", "ipv4", "delete", "address",
                  f"name={interface_alias}", f"addr={ip}"])
        _forget(interface_alias, ip)
        if p.returncode == 0 or r.returncode == 0:
            return True, f"Removed {ip} from '{interface_alias}'."
        out = (((p.stderr or "") + (r.stderr or ""))).strip()[:300]
        return False, f"Could not remove {ip} (maybe already gone). {out}"
    # bez admina: jednorazowa elevacja usuwania (UAC), weryfikacja skutku
    script = (f"Start-Process netsh -ArgumentList 'interface ipv4 delete address "
              f"name=\"{interface_alias}\" addr={ip}' -Verb RunAs -Wait")
    try:
        _run_ps(script, timeout=60)
    except Exception as e:
        return False, f"Removal elevation failed: {e}"[:300]
    gone = all(not (a["alias"] == interface_alias and a["ip"] == ip)
               for a in list_ipv4_addresses())
    _forget(interface_alias, ip)
    if gone:
        return True, f"Removed {ip} from '{interface_alias}' (UAC elevation)."
    return False, f"Removal of {ip} not confirmed (UAC denied?)."


_CLEANED = False
_CLEAN_LOCK = threading.Lock()

def cleanup_all() -> list[str]:
    """Sprzatanie jednokrotne na proces: pierwsze wywolanie przejmuje stan
    (zapisuje pusty), wiec rownolegle closeEvent+atexit nie dublowaly UAC."""
    global _CLEANED
    with _CLEAN_LOCK:
        claimed = _load_state()
        _save_state([])  # przejecie - drugie wywolanie nie ma juz czego sprzatac
        if not claimed or _CLEANED:
            _CLEANED = True
            return []
        _CLEANED = True
    return [remove_temp_ip(i["interface_alias"], i["ip"])[1] for i in claimed]


def ensure_homes_visible(interface_alias: str, homes: list[str], prefix: int = 24) -> tuple[bool, str]:
    """Jedno UAC na wiele podsieci: dobudowuje brakujace secondary IP na raz.

    homes to bazowe /24 w formie '192.168.4' (lub pelne IP - baza wyliczana).
    Zwraca (ok, komunikat). Bez nowych adresow - bez UAC w ogole.
    """
    want: list[tuple[str, str]] = []
    for h in dict.fromkeys(homes):
        # h moze byc '192.168.4' albo '192.168.4.101'
        parts = h.split(".")
        base = ".".join(parts[:3]) if len(parts) == 4 else h
        live = {a["ip"] for a in list_ipv4_addresses() if a["alias"] == interface_alias}
        if any(ip.startswith(base + ".") for ip in live):
            continue
        bip = f"{base}.200"
        if bip in live:
            bip = f"{base}.201"
        want.append((base, bip))
    if not want:
        return True, "All known subnets are already visible."
    if is_admin():
        msgs = []
        for base, bip in want:
            ok, m = _ps_add(interface_alias, bip, prefix)
            if ok:
                _remember(TempIp(interface_alias, bip, prefix))
            msgs.append(m)
        return True, " | ".join(msgs)
    # jedna elevacja na wszystko: powershell z wieloma netsh w srodku
    mask = {24: "255.255.255.0", 16: "255.255.0.0", 8: "255.0.0.0"}.get(prefix, "255.255.255.0")
    cmds = "; ".join(f"netsh interface ipv4 add address name=\"{interface_alias}\" addr={bip} mask={mask}"
                     for _, bip in want)
    script = (f"Start-Process powershell -ArgumentList '-NoProfile -Command \"{cmds}\"' "
              f"-Verb RunAs -Wait")
    try:
        _run_ps(script, timeout=90)
    except Exception as e:
        return False, f"Elevacja nieudana: {e}"[:200]
    live = {(a["alias"], a["ip"]) for a in list_ipv4_addresses()}
    done = [bip for _, bip in want if (interface_alias, bip) in live]
    for _, bip in want:
        if (interface_alias, bip) in live:
            _remember(TempIp(interface_alias, bip, prefix))
    if done:
        return True, f"Bridge built ({', '.join(done)}) on '{interface_alias}' (single UAC)."
    return False, "Elevation done, but the addresses are not visible (UAC denied?)."


def ensure_subnet_visible(interface_alias: str, subnet_ip: str = "192.168.0.200",
                          prefix: int = 24) -> tuple[bool, str]:
    """Pojedynczy secondary IP (kompatybilnosc)."""
    base = ".".join(subnet_ip.split(".")[: prefix // 8])
    for a in list_ipv4_addresses():
        if a["alias"] == interface_alias and a["ip"].startswith(base + "."):
            return True, f"Karta '{interface_alias}' juz widzi {base}.0/{prefix} ({a['ip']})."
    return add_temp_ip(interface_alias, subnet_ip, prefix)


# ---------- automatyczny wybor interfejsu (bez recznego ComboBox) ----------

VIRTUAL_HINTS = ("bluetooth", "loopback", "polaczenie lokalne", "połączenie lokalne",
                 "local area connection", "wi-fi direct", "wifi direct", "direct",
                 "virtual", "komorkowa", "komórkowa", "cellular", "wwan",
                 "remote ndis", "vpn", "tap-", "hyper-v", "vmware", "virtualbox")


def _norm(s: str) -> str:
    return (s or "").lower().replace("ą", "a").replace("ć", "c").replace("ę", "e") \
        .replace("ł", "l").replace("ń", "n").replace("ó", "o").replace("ś", "s") \
        .replace("ź", "z").replace("ż", "z")


def is_virtual_alias(alias: str, desc: str = "") -> bool:
    t = _norm(alias) + " " + _norm(desc)
    return any(h in t for h in VIRTUAL_HINTS)


def list_adapters() -> list[dict]:
    """Wszystkie karty: {alias, status, mediatype, desc, virtual}."""
    ps = ("Get-NetAdapter | Select-Object Name,Status,MediaType,InterfaceDescription | "
          "ConvertTo-Json")
    try:
        p = _run_ps(ps)
        if not p.stdout.strip():
            return []
        data = json.loads(p.stdout)
        if isinstance(data, dict):
            data = [data]
        out = []
        for d in data:
            alias = str(d.get("Name", "?"))
            out.append({"alias": alias,
                        "status": str(d.get("Status", "?")),
                        "mediatype": str(d.get("MediaType", "?")),
                        "desc": str(d.get("InterfaceDescription", "?")),
                        "virtual": is_virtual_alias(alias, str(d.get("InterfaceDescription", "")))})
        return out
    except Exception:
        return []


def best_bridge_iface() -> str | None:
    """Automatyczny wybor karty pod most: fizyczny Ethernet, najlepiej z linkiem."""
    try:
        ads = list_adapters()
    except Exception:
        return None
    eth = [a for a in ads if "802.3" in a["mediatype"] and not a["virtual"]]
    for a in eth:
        if a["status"].lower() == "up":
            return a["alias"]
    if eth:
        return eth[0]["alias"]
    return None


def tcp_reachable(ip: str, timeout: float = 1.0) -> bool:
    for port in (80, 8080):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except Exception:
            continue
    return False


def ensure_reachable(ip: str, prefix: int = 24) -> tuple[bool, str]:
    """Pelny automat: jesli IP osiagalne - nic nie rob; jesli nie - dobuduj most."""
    if tcp_reachable(ip):
        return True, f"{ip} osiagalne bez zmian."
    iface = best_bridge_iface()
    if not iface:
        return False, f"{ip} nieosiagalne i brak fizycznego Ethernetu pod most."
    ok, msg = ensure_homes_visible(iface, [ip], prefix)
    if not ok:
        return False, msg
    if tcp_reachable(ip, timeout=2.0):
        return True, f"{ip} osiagalne przez most ({msg})"
    return False, f"Most dodany ({msg}), ale {ip} nadal nie odpowiada."
