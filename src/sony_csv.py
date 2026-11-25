"""CSV compatible with RM-IP Setup Tool (formats recovered from v1.2.0 disassembly).

Two formats:
  * RM-IP panel table (export 0x41e0d0 / import 0x41e450):
      header ";Group No-Camera No,Camera Name,MAC Address,IP Address,Subnet Mask"
      (a line starting with "; " is skipped on import - that is what the original does)
      rows: "Group<G>-<C>,<name>,<MAC>,<IP>,<mask>", G=1..7, C=1..16;
      mask "255.255.255.0" when the slot is filled (MAC and IP), otherwise empty.
      The original import requires exactly 4 commas per row and 100/112
      data rows - our parsing is tolerant, and the export produces 112.
  * camera list (export 0x411830):
      header "Camera Name,MAC Address,IP Address,Subnet Mask,Gateway address,Version"
      rows: 6 comma-separated fields.
"""

from __future__ import annotations

import re

TABLE_HEADER = ";Group No-Camera No,Camera Name,MAC Address,IP Address,Subnet Mask"
CAMERA_HEADER = "Camera Name,MAC Address,IP Address,Subnet Mask,Gateway address,Version"
DEFAULT_MASK = "255.255.255.0"
GROUPS = 7
PER_GROUP = 16
TOTAL_SLOTS = GROUPS * PER_GROUP  # 112 (RM-IP500); RM-IP10 has 100


def slot_to_group_camera(slot: int) -> tuple[int, int]:
    slot = int(slot)
    if not 1 <= slot <= TOTAL_SLOTS:
        raise ValueError(f"slot {slot} is outside 1..{TOTAL_SLOTS}")
    return (slot - 1) // PER_GROUP + 1, (slot - 1) % PER_GROUP + 1


def group_camera_to_slot(group: int, camera: int) -> int:
    g, c = int(group), int(camera)
    if not 1 <= g <= GROUPS or not 1 <= c <= PER_GROUP:
        raise ValueError(f"group/camera {g}-{c} is outside 1..{GROUPS} / 1..{PER_GROUP}")
    return (g - 1) * PER_GROUP + c


def _clean_cell(value) -> str:
    return str(value or "").replace(",", " ").replace(";", " ").replace("\r", " ").replace("\n", " ").strip()


def table_csv_text(slots: dict, total: int = TOTAL_SLOTS) -> str:
    """Panel table export. slots: {slot: {"name","mac","ip","mask"}}.

    Empty slots get empty fields (like the original), so the file always has
    `total` data rows - the Sony import expects 100 or 112.
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
    """Tolerant table import. Returns {"rows": [...], "warnings": [...]}."""
    rows: list[dict] = []
    warnings: list[str] = []
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            continue  # header/comment - the original skips it too
        fields = [f.strip() for f in line.split(",")]
        if len(fields) != 5:
            warnings.append(f"line {ln}: got {len(fields)} fields instead of 5 (skipped)")
            continue
        m = _GC_RE.match(fields[0]) or _GC_LOOSE_RE.search(fields[0])
        if not m:
            warnings.append(f"line {ln}: cannot read 'Group G-C' from {fields[0]!r}")
            continue
        g, c = int(m.group(1)), int(m.group(2))
        if not 1 <= g <= GROUPS or not 1 <= c <= PER_GROUP:
            warnings.append(f"line {ln}: index {g}-{c} is outside 1-7 / 1-16")
            continue
        rows.append(
            {
                "line": ln,
                "group": g,
                "camera": c,
                "slot": group_camera_to_slot(g, c),
                "name": fields[1],
                "mac": fields[2].upper(),
                "ip": fields[3],
                "mask": fields[4],
            }
        )
    return {"rows": rows, "warnings": warnings}


def camera_csv_text(devices: list[dict]) -> str:
    """Camera list export. devices: dicts with name,mac,ip,mask,gateway,version."""
    lines = [CAMERA_HEADER]
    for d in devices:
        lines.append(",".join(_clean_cell(d.get(k)) for k in ("name", "mac", "ip", "mask", "gateway", "version")))
    return "\r\n".join(lines) + "\r\n"


def parse_camera_csv(text: str) -> dict:
    """Camera list import. Returns {"rows": [...], "warnings": [...]}."""
    rows: list[dict] = []
    warnings: list[str] = []
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.lower().startswith("camera name,"):
            continue
        fields = [f.strip() for f in line.split(",")]
        if len(fields) < 6:
            warnings.append(f"line {ln}: got {len(fields)} fields instead of 6 (skipped)")
            continue
        name, mac, ip, mask, gw, ver = fields[:6]
        rows.append(
            {"line": ln, "name": name, "mac": mac.upper(), "ip": ip, "mask": mask, "gateway": gw, "version": ver}
        )
    return {"rows": rows, "warnings": warnings}
