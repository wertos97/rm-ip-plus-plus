"""Generate build/version_info.txt (Windows exe metadata) from src/version.py.

Usage:  python tools/make_version_info.py
"""

from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_PY = os.path.join(ROOT, "src", "version.py")
OUT_DIR = os.path.join(ROOT, "build")
OUT = os.path.join(OUT_DIR, "version_info.txt")

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver},
    prodvers={ver},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'RM IP++'),
        StringStruct('FileDescription', 'Sony IP camera control console'),
        StringStruct('FileVersion', '{ver_str}'),
        StringStruct('InternalName', 'RMIPpp'),
        StringStruct('OriginalFilename', 'RMIPpp.exe'),
        StringStruct('ProductName', 'RM IP++'),
        StringStruct('ProductVersion', '{ver_str}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def read_version() -> str:
    text = open(VERSION_PY, encoding="utf-8").read()
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not m:
        raise SystemExit("no __version__ in src/version.py")
    return m.group(1)


def main() -> None:
    version = read_version()
    parts = [int(x) for x in re.findall(r"\d+", version)]
    while len(parts) < 4:
        parts.append(0)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(ver=tuple(parts[:4]), ver_str=version))
    print(f"version {version} -> {OUT}")


if __name__ == "__main__":
    main()
