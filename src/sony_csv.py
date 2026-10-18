"""CSV zgodne z RM-IP Setup Tool (formaty odtworzone z deasemblacji v1.2.0).

Dwa formaty:
  * tabela panelu RM-IP (export 0x41e0d0 / import 0x41e450):
      naglowek ";Group No-Camera No,Camera Name,MAC Address,IP Address,Subnet Mask"
      (linia zaczynajaca sie "; " jest pomijana przy imporcie - tak robi oryginal)
      wiersze: "Group<G>-<C>,<nazwa>,<MAC>,<IP>,<maska>", G=1..7, C=1..16;
      maska "255.255.255.0" gdy slot wypelniony (MAC i IP), inaczej pole puste.
      Oryginalny import wymaga dokladnie 4 przecinkow na wiersz oraz 100/112
      wierszy danych - nasze parsowanie jest tolerancyjne, a eksport daje 112.
  * lista kamer (export 0x411830):
      naglowek "Camera Name,MAC Address,IP Address,Subnet Mask,Gateway address,Version"
      wiersze: 6 pol rozdzielonych przecinkami.
"""
from __future__ import annotations

import re

TABLE_HEADER = ";Group No-Camera No,Camera Name,MAC Address,IP Address,Subnet Mask"
CAMERA_HEADER = "Camera Name,MAC Address,IP Address,Subnet Mask,Gateway address,Version"
DEFAULT_MASK = "255.255.255.0"
GROUPS = 7
PER_GROUP = 16
TOTAL_SLOTS = GROUPS * PER_GROUP     # 112 (RM-IP500); RM-IP10 ma 100


def slot_to_group_camera(slot: int) -> tuple[int, int]:
    slot = int(slot)
    if not 1 <= slot <= TOTAL_SLOTS:
        raise ValueError(f"slot {slot} spoza zakresu 1..{TOTAL_SLOTS}")
    return (slot - 1) // PER_GROUP + 1, (slot - 1) % PER_GROUP + 1


def group_camera_to_slot(group: int, camera: int) -> int:
    g, c = int(group), int(camera)
    if not 1 <= g <= GROUPS or not 1 <= c <= PER_GROUP:
        raise ValueError(f"grupa/kamera {g}-{c} poza zakresem 1..{GROUPS} / 1..{PER_GROUP}")
    return (g - 1) * PER_GROUP + c


def _clean_cell(value) -> str:
    return (str(value or "")
            .replace(",", " ").replace(";", " ")
            .replace("\r", " ").replace("\n", " ").strip())


def table_csv_text(slots: dict, total: int = TOTAL_SLOTS) -> str:
    """Eksport tabeli panelu. slots: {slot: {"name","mac","ip","mask"}}.

    Puste sloty dostaja puste pola (tak jak oryginal), wiec plik ma zawsze
    `total` wierszy danych - import Sony oczekuje 100 albo 112.
    """
    lines = [TABLE_HEADER]
    for slot in range(1, min(int(total), TOTAL_SLOTS) + 1):
        g, c = slot_to_group_camera(slot)
        e = slots.get(slot) or slots.get(str(slot)) or {}
        mac = _clean_cell(e.get("mac"))
        ip = _clean_cell(e.get("ip"))
        filled = bool(mac and ip)
        mask = _clean_cell(e.get("mask")) or (DEFAULT_MASK if filled else "")
        lines.append(f"Group{g}-{c},{_clean_cell(e.get('name'))},{mac},{ip},{mask}")
    return "\r\n".join(lines) + "\r\n"


_GC_RE = re.compile(r"^Group\s*(\d+)\s*-\s*(\d+)$", re.I)
_GC_LOOSE_RE = re.compile(r"(\d+)\D+(\d+)")


def parse_table_csv(text: str) -> dict:
    """Tolerancyjny import tabeli. Zwraca {"rows": [...], "warnings": [...]}."""
    rows: list[dict] = []
    warnings: list[str] = []
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            continue                       # naglowek/komentarz - oryginal tez pomija
        fields = [f.strip() for f in line.split(",")]
        if len(fields) != 5:
            warnings.append(f"wiersz {ln}: {len(fields)} pol zamiast 5 (pomijam)")
            continue
        m = _GC_RE.match(fields[0]) or _GC_LOOSE_RE.search(fields[0])
        if not m:
            warnings.append(f"wiersz {ln}: nie umiem odczytac 'Group G-C' z {fields[0]!r}")
            continue
        g, c = int(m.group(1)), int(m.group(2))
        if not 1 <= g <= GROUPS or not 1 <= c <= PER_GROUP:
            warnings.append(f"wiersz {ln}: indeks {g}-{c} poza zakresem 1-7 / 1-16")
            continue
        rows.append({"line": ln, "group": g, "camera": c,
                     "slot": group_camera_to_slot(g, c),
                     "name": fields[1], "mac": fields[2].upper(),
                     "ip": fields[3], "mask": fields[4]})
    return {"rows": rows, "warnings": warnings}


def camera_csv_text(devices: list[dict]) -> str:
    """Eksport listy kamer. devices: dicts z name,mac,ip,mask,gateway,version."""
    lines = [CAMERA_HEADER]
    for d in devices:
        lines.append(",".join(_clean_cell(d.get(k)) for k in
                              ("name", "mac", "ip", "mask", "gateway", "version")))
    return "\r\n".join(lines) + "\r\n"


def parse_camera_csv(text: str) -> dict:
    """Import listy kamer. Zwraca {"rows": [...], "warnings": [...]}."""
    rows: list[dict] = []
    warnings: list[str] = []
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.lower().startswith("camera name,"):
            continue
        fields = [f.strip() for f in line.split(",")]
        if len(fields) < 6:
            warnings.append(f"wiersz {ln}: {len(fields)} pol zamiast 6 (pomijam)")
            continue
        name, mac, ip, mask, gw, ver = fields[:6]
        rows.append({"line": ln, "name": name, "mac": mac.upper(), "ip": ip,
                     "mask": mask, "gateway": gw, "version": ver})
    return {"rows": rows, "warnings": warnings}
