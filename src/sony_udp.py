"""Protokol UDP 52380 Sony - odtworzony z deasemblacji RM-IPSetupTool.exe (v1.2.0).

Formaty wiadomosci (VA funkcji w oryginale podane w komentarzach):
  wykrywanie (builder 0x404010, parser 0x427710):
    zadanie :  02 "ENQ:network" FF 03          -> broadcast UDP 52380
    odpowiedz: 02 "INFO:network" FF "MODEL:<...>" FF "SOFTVERSION:<...>" FF
               "MAC:<xx-xx-xx-xx-xx-xx>" FF "IPADR:<ip>" FF "MASK:<maska>" FF
               "GATEWAY:<brama>" FF "NAME:<nazwa>" FF "WRITE:on|off" FF 03
  zapis sieci (builder 0x404120..0x4044f7, parser ACK 0x426760 / NAK 0x426ae0):
    zadanie :  02 "MAC:<mac>" FF "IPADR:<ip>" FF "MASK:<mask>" FF
               "GATEWAY:<gw>" FF "NAME:<nazwa>" FF 03
    odpowiedz: 02 "ACK:\"<mac>\"" FF 03   (albo NAK:"<mac>"...)
  tabela panelu RM-IP (builder 0x418f5e, parser 0x426e60):
    zadanie :  02 "ENQ:camtable<N>" FF 03      N=1..4 (4 strony x 28 = 112)
    odpowiedz: 02 "MAC:<mac_panelu>" FF "INFO:camtable<N>" FF
               "CAM<NNN>:<MAC>:<IP>:<nazwa>" FF ... FF 03   ("CAM002:::" = pusty)
  0x02 = STX, 0x03 = ETX, 0xFF = separator pol. Oryginal parsuje pole przez
  strstr("MODEL:") i czyta wartosc do najblizszego bajtu 0xFF - tak samo tu.

Zaleta nad skanem TCP: broadcast dociera do calego segmentu L2, wiec kamera
z adresem z innej podsieci niz komputer tez odpowie (dokladnie tak dziala
"Auto IP Setup" w narzedziu Sony, ktore w ten sposob naprawia zle IP).
"""
from __future__ import annotations

import re
import select
import socket
import subprocess
import time

SONY_UDP_PORT = 52380
ENQ_NETWORK = b"\x02ENQ:network\xff\x03"
CAMTABLE_PAGES = 4              # ENQ:camtable1..4
CAMTABLE_ENTRIES_PER_PAGE = 28  # 4 strony x 28 = 112 slotow (RM-IP500)
CAMTABLE_SLOTS = CAMTABLE_PAGES * CAMTABLE_ENTRIES_PER_PAGE

_REPLY_KEYS = ("MODEL", "SOFTVERSION", "MAC", "IPADR", "MASK", "GATEWAY", "NAME",
               "WRITE")


def build_request() -> bytes:
    """Ramka zadania - dokladnie to, co wysyla RM-IP Setup Tool."""
    return ENQ_NETWORK


def _field(data: bytes, key: str) -> str:
    """Wartosc pola KEY:... do najblizszego 0xFF (albo konca ramki 0x03)."""
    m = re.search(re.escape(key.encode()) + rb":(.*?)[\xff\x03]", data, re.S)
    if not m:
        m = re.search(re.escape(key.encode()) + rb":(.*)", data, re.S)
    if not m:
        return ""
    return m.group(1).decode("utf-8", "replace").strip("\x00 \t\r\n")


def parse_reply(data: bytes, src_ip: str = "") -> dict | None:
    """Parsuje odpowiedz INFO:network; None gdy to nie nasza odpowiedz."""
    if b"INFO:" not in data or b"network" not in data:
        return None
    fields = {k: _field(data, k) for k in _REPLY_KEYS}
    ip = fields["IPADR"] or src_ip
    if not (fields["MODEL"] or fields["MAC"] or ip):
        return None
    mac = fields["MAC"]
    return {
        "ip": ip,
        "src_ip": src_ip,
        "model": fields["MODEL"],
        "softversion": fields["SOFTVERSION"],
        "mac": mac,
        "mac_norm": mac.replace("-", ":").lower() if mac else "",
        "name": fields["NAME"],
        "mask": fields["MASK"],
        "gateway": fields["GATEWAY"],
        "writable": fields["WRITE"].lower(),   # "on"/"off"/""
    }


def local_ipv4s() -> list[str]:
    """Lokalne adresy IPv4: ipconfig + adres wyjscia trasy domyslnej + hostname."""
    ips: list[str] = []
    try:
        out = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for m in re.finditer(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", out.stdout or ""):
            ips.append(m.group(1))
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 53))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except Exception:
        pass
    result: list[str] = []
    for ip in ips:
        if not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", ip):
            continue
        if ip.startswith(("127.", "0.", "255.", "169.254.")):
            continue
        if ip not in result:
            result.append(ip)
    return result


def _open_socks(ips, log=None):
    """Jeden socket UDP na kazdy lokalny IPv4 (+ domyslny) - broadcast wyjdzie
    takze kablem z tymczasowym IP mostu, nie tylko WiFi."""
    socks: list[tuple[socket.socket, str]] = []
    for bind_ip in [""] + [ip for ip in ips if ip not in ("",)]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, 1)  # nie wyjdzie za router
            except Exception:
                pass
            s.bind((bind_ip, 0))
            s.setblocking(False)
            socks.append((s, bind_ip))
        except Exception:
            try:
                s.close()
            except Exception:
                pass
    if log:
        try:
            log(f"UDP {SONY_UDP_PORT}: gniazda z {len(socks)} interfejsow")
        except Exception:
            pass
    return socks


def _broadcast_targets(ips, extra_broadcasts=()):
    targets = ["255.255.255.255"]
    for ip in ips:
        b = ip.rsplit(".", 1)[0] + ".255"          # /24 - tak dziala most w apce
        if b not in targets:
            targets.append(b)
    for b in extra_broadcasts:
        if b and b not in targets:
            targets.append(b)
    return targets


def _send_rounds(socks, targets, payloads, retries=3, gap=0.15):
    """Wysyla kazda wiadomosc z listy do wszystkich celow, `retries` rund."""
    for attempt in range(max(1, retries)):
        for payload in payloads:
            for s, _ip in socks:
                for tgt in targets:
                    try:
                        s.sendto(payload, (tgt, SONY_UDP_PORT))
                    except Exception:
                        pass
            if len(payloads) > 1:
                time.sleep(0.05)
        if attempt + 1 < retries:
            time.sleep(gap)


def _listen(socks, timeout, handler, dedup=None):
    """Zbiera wyniki handler(data, addr) przez `timeout` sekund.
    dedup(item) -> klucz odsiewajacy duplikaty (None = bez odsiewania)."""
    t0 = time.monotonic()
    out = []
    seen = set()
    while True:
        left = timeout - (time.monotonic() - t0)
        if left <= 0:
            break
        try:
            ready, _, _ = select.select([s for s, _ in socks], [], [], min(left, 0.3))
        except Exception:
            break
        if not ready:
            continue
        for s, _ip in socks:
            if s not in ready:
                continue
            while True:
                try:
                    data, addr = s.recvfrom(4096)
                except Exception:
                    break
                try:
                    item = handler(data, addr)
                except Exception:
                    item = None
                if item is None:
                    continue
                if dedup is not None:
                    try:
                        key = dedup(item)
                    except Exception:
                        key = None
                    if key is not None:
                        if key in seen:
                            continue
                        seen.add(key)
                out.append(item)
    return out


def _exchange(payloads, timeout, handler, dedup=None, retries=3,
              extra_broadcasts=(), log=None, local_ips=None):
    """Wspolny przeplyw: gniazda -> rundy broadcastu -> nasluch z odsiewem."""
    ips = list(local_ips) if local_ips is not None else local_ipv4s()
    socks = _open_socks(ips, log)
    if not socks:
        return []
    try:
        targets = _broadcast_targets(ips, extra_broadcasts)
        _send_rounds(socks, targets, payloads, retries=retries)
        return _listen(socks, timeout, handler, dedup=dedup)
    finally:
        for s, _ in socks:
            try:
                s.close()
            except Exception:
                pass


def discover(timeout: float = 2.0, retries: int = 3, extra_broadcasts=(),
             log=None, local_ips=None) -> list[dict]:
    """Broadcastuje ENQ:network (52380) i zbiera odpowiedzi kamer.

    Jeden socket na kazdy lokalny adres IPv4 (+ domyslny) - dzieki temu
    broadcast wychodzi takze kablem z tymczasowym IP mostu, nie tylko WiFi.
    Zwraca liste dictow z parse_reply (posortowana po IP).
    """
    hits = _exchange(
        [build_request()], timeout,
        lambda data, addr: parse_reply(data, addr[0]),
        dedup=lambda c: c["mac_norm"] or c["ip"],
        retries=retries, extra_broadcasts=extra_broadcasts,
        log=log, local_ips=local_ips)
    if log:
        for cam in hits:
            try:
                log(f"UDP: {cam['ip']} {cam['model']} ({cam['name']})")
            except Exception:
                pass
    return sorted(hits, key=lambda c: c["ip"])


# ---------------------------------------------------------------------------
# SET sieci kamery (odpowiednik "Auto IP Setup" / WRITE w RM-IP Setup Tool)
# ---------------------------------------------------------------------------

def normalize_mac(mac: str) -> str:
    """'f8:4e:17:de:30:9f' / 'f84e17de309f' -> 'F8-4E-17-DE-30-9F' (format Sony)."""
    hexs = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if len(hexs) != 12:
        raise ValueError(
            f"MAC must have 12 hex digits, e.g. F8-4E-17-DE-30-9F (got {mac!r})")
    return "-".join(hexs[i:i + 2] for i in range(0, 12, 2)).upper()


def is_ipv4(value: str) -> bool:
    m = re.fullmatch(r"\s*(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\s*", value or "")
    return bool(m) and all(0 <= int(g) <= 255 for g in m.groups())


def _clean_top_value(value: str, what: str) -> str:
    s = str(value or "").strip()
    if any(ch in s for ch in "\x00\x02\x03\xff"):
        raise ValueError(f"{what}: illegal control character")
    return s


def build_set_network(mac: str, ip: str, mask: str, gateway: str, name: str) -> bytes:
    """Ramka SET sieci kamery (dokladnie jak 0x404120..0x4044f7 w RM-IPSetupTool).

    02 MAC:<mac> FF IPADR:<ip> FF MASK:<mask> FF GATEWAY:<gw> FF NAME:<name> FF 03
    Wysylana na broadcast - MAC w ramce wybiera kamere, ktora ma to przyjac.
    """
    mac = normalize_mac(mac)
    ip = _clean_top_value(ip, "IP")
    mask = _clean_top_value(mask, "mask")
    gateway = _clean_top_value(gateway, "gateway")
    name = _clean_top_value(name, "name")
    if not is_ipv4(ip):
        raise ValueError(f"IP {ip!r} is not a valid IPv4 address")
    if not is_ipv4(mask):
        raise ValueError(f"mask {mask!r} is not valid")
    if gateway and not is_ipv4(gateway):
        raise ValueError(f"gateway {gateway!r} is not valid")
    if not name:
        raise ValueError("name cannot be empty")
    if len(name) > 16 or any(not (0x20 <= ord(ch) <= 0x7E) for ch in name):
        raise ValueError("name: max 16 printable ASCII characters, no diacritics")
    return (b"\x02MAC:" + mac.encode("ascii") + b"\xffIPADR:" + ip.encode("ascii") +
            b"\xffMASK:" + mask.encode("ascii") + b"\xffGATEWAY:" +
            gateway.encode("ascii") + b"\xffNAME:" + name.encode("ascii") + b"\xff\x03")


def build_camtable_query(page: int = 1) -> bytes:
    """ENQ:camtable<N> - N=1..4; kazda strona to 28 slotow tabeli panelu."""
    if not 1 <= int(page) <= CAMTABLE_PAGES:
        raise ValueError(f"camtable page {page} out of range 1..{CAMTABLE_PAGES}")
    return f"\x02ENQ:camtable{int(page)}\xff\x03".encode("latin-1")


def parse_ack_nak(data: bytes) -> dict | None:
    """ACK:/NAK: z 52380. MAC kamery jest w cudzyslowie (parser 0x426760/0x426ae0)."""
    kind = ""
    if b"NAK:" in data:
        kind = "NAK"
    elif b"ACK:" in data:
        kind = "ACK"
    if not kind:
        return None
    text = data.decode("latin-1", "replace")
    m = re.search(r'"([0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})"', text)
    mac = m.group(1).upper() if m else ""
    if m:
        tail = text[m.end():]
    else:
        i = text.find(kind + ":")
        tail = text[i + len(kind) + 1:] if i >= 0 else ""
    tail = tail.strip("\x00 \t\r\n\xff\x03")
    return {"kind": kind, "mac": mac, "tail": tail, "raw": data}


_CAMTABLE_ENTRY_RE = re.compile(r"^CAM(\d{1,3})(.*)$")


def parse_camtable_entry(part: str) -> dict | None:
    """Jeden wpis 'CAM<NNN>:<MAC>:<IP>:<nazwa>' (pusty: 'CAM002:::')."""
    m = _CAMTABLE_ENTRY_RE.match(part.strip())
    if not m:
        return None
    slot = int(m.group(1))
    rest = m.group(2)
    if rest.startswith(":"):
        rest = rest[1:]
    fields = rest.split(":", 2)
    while len(fields) < 3:
        fields.append("")
    mac, ip, name = (f.strip() for f in fields[:3])
    return {"slot": slot, "mac": mac.upper(), "ip": ip, "name": name}


def parse_camtable_reply(data: bytes, src_ip: str = "") -> dict | None:
    """Odpowiedz panelu: 02 MAC:<mac_panelu> FF INFO:camtable<N> FF CAM###:... FF 03"""
    if b"INFO:camtable" not in data:
        return None
    m = re.search(rb"INFO:camtable(\d+)", data)
    page = int(m.group(1)) if m else 0
    pm = re.search(rb"MAC:([0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})", data)
    panel_mac = pm.group(1).decode("ascii").upper() if pm else ""
    entries = []
    for part in re.split(r"[\xff\x03]", data.decode("latin-1", "replace")):
        e = parse_camtable_entry(part)
        if e:
            entries.append(e)
    if not entries and not panel_mac:
        return None
    return {"page": page, "panel_mac": panel_mac, "src_ip": src_ip,
            "entries": entries, "raw": data}


def set_camera_network(mac: str, ip: str, mask: str, gateway: str = "", name: str = "",
                       timeout: float = 4.0, retries: int = 3,
                       extra_broadcasts=(), log=None, local_ips=None) -> dict:
    """Wysyla SET sieci (broadcast) i czeka na ACK/NAK od kamery o danym MAC.

    UWAGA: kamera zmienia adres od razu po ACK - jesli nowy IP jest w innej
    podsieci niz komputer, do dalszej pracy potrzebny bedzie most/temp IP.
    Zwraca {"ok", "kind": ACK/NAK/timeout, ...}.
    """
    payload = build_set_network(mac, ip, mask, gateway, name)
    target_mac = normalize_mac(mac)

    def _on_packet(data, addr):
        info = parse_ack_nak(data)
        if not info:
            return None
        info["src_ip"] = addr[0]
        return info

    replies = _exchange([payload], timeout, _on_packet,
                        dedup=lambda r: (r["kind"], r["mac"], r["src_ip"]),
                        retries=retries, extra_broadcasts=extra_broadcasts,
                        log=log, local_ips=local_ips)
    acks = [r for r in replies if r["kind"] == "ACK"]
    naks = [r for r in replies if r["kind"] == "NAK"]
    base = {"ip": ip, "mask": mask, "gateway": gateway, "name": name,
            "target_mac": target_mac, "replies": replies}
    pick_ack = next((r for r in acks if r["mac"] and r["mac"] == target_mac), None)
    other_ack = next((r for r in acks if not r["mac"]), None)
    if pick_ack or other_ack:
        r = pick_ack or other_ack
        return {**base, "ok": True, "kind": "ACK", "reply_mac": r["mac"],
                "src_ip": r["src_ip"], "raw": r["raw"]}
    if naks:
        r = naks[0]
        return {**base, "ok": False, "kind": "NAK", "reply_mac": r["mac"],
                "src_ip": r["src_ip"], "tail": r["tail"], "raw": r["raw"]}
    return {**base, "ok": False, "kind": "timeout"}


def query_camtable(pages=(1, 2, 3, 4), timeout: float = 5.0, retries: int = 3,
                   extra_broadcasts=(), log=None, local_ips=None) -> dict:
    """Pyta panel RM-IP o tabele kamer (4 strony po 28 slotow).

    Zwraca {"pages": [parse_camtable_reply...], "misc": [ACK/NAK...], "raw": [bajty...]}
    """
    payloads = [build_camtable_query(p) for p in pages]

    def _on_packet(data, addr):
        info = parse_camtable_reply(data, addr[0])
        if info:
            return ("page", info)
        ack = parse_ack_nak(data)
        if ack:
            ack["src_ip"] = addr[0]
            return ("misc", ack)
        return None

    items = _exchange(
        payloads, timeout, _on_packet,
        dedup=lambda it: (it[0], it[1].get("src_ip", ""),
                          it[1].get("page", ""), it[1].get("kind", "")),
        retries=retries, extra_broadcasts=extra_broadcasts,
        log=log, local_ips=local_ips)
    out: dict = {"pages": [], "misc": [], "raw": []}
    for tag, info in items:
        if tag == "page":
            out["pages"].append(info)
        else:
            out["misc"].append(info)
        out["raw"].append(info.get("raw", b""))
    return out
