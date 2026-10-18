"""Generate assets/icon.ico from assets/icon.svg.

Small sizes are stored as BMP (DIB) entries - Windows shell/taskbar does not
render PNG-compressed entries below 256 px reliably. 128/256 keep PNG.

Usage:  python tools/make_ico.py
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
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_image(size: int) -> QImage:
    r = QSvgRenderer(SVG)
    if not r.isValid():
        raise SystemExit("unparseable SVG: " + SVG)
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    r.render(p)
    p.end()
    return img


def png_entry(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def bmp_entry(img: QImage) -> bytes:
    """32-bit BMP (DIB) entry: BITMAPINFOHEADER + BGRA rows + empty AND mask."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    size = img.width()
    xor = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            c = img.pixelColor(x, y)
            xor += bytes((c.blue(), c.green(), c.red(), c.alpha()))
    mask_row = ((size + 31) // 32) * 4
    and_mask = bytearray(mask_row * size)  # zeros = opaque (alpha channel rules)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         len(xor) + len(and_mask), 0, 0, 0, 0)
    return header + bytes(xor) + bytes(and_mask)


def main():
    app = QApplication(sys.argv[:1])  # noqa: F841
    entries = []
    for size in SIZES:
        img = render_image(size)
        data = png_entry(img) if size >= 128 else bmp_entry(img)
        entries.append((size, data))
    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    offset = 6 + 16 * len(entries)
    for size, data in entries:
        b = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in entries:
        out += data
    with open(ICO, "wb") as fh:
        fh.write(out)
    kinds = ", ".join(f"{s}{'p' if s >= 128 else 'b'}" for s, _ in entries)
    print("ok", ICO, len(out), "bytes,", len(entries), f"sizes ({kinds})")


if __name__ == "__main__":
    main()
