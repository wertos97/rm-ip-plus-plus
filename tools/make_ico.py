"""Generuje assets/icon.ico z assets/icon.svg (rozmiary 16..256, wpisy PNG).

Uruchomienie:  python tools/make_ico.py
"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, "assets", "icon.svg")
ICO = os.path.join(ROOT, "assets", "icon.ico")
SIZES = (16, 32, 48, 64, 128, 256)


def render_png(size):
    r = QSvgRenderer(SVG)
    if not r.isValid():
        raise SystemExit("unparseable SVG: " + SVG)
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    r.render(p)
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def main():
    app = QApplication(sys.argv[:1])  # noqa: F841
    entries = [(s, render_png(s)) for s in SIZES]
    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    offset = 6 + 16 * len(entries)
    for size, png in entries:
        b = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    for _, png in entries:
        out += png
    with open(ICO, "wb") as fh:
        fh.write(out)
    print("ok", ICO, len(out), "bytes,", len(entries), "sizes")


if __name__ == "__main__":
    main()
