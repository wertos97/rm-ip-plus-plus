"""Generate assets/icon.icns from assets/icon.svg on macOS."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, "assets", "icon.svg")
ICNS = os.path.join(ROOT, "assets", "icon.icns")
ICONSET_NAMES = {
    16: ["icon_16x16.png"],
    32: ["icon_16x16@2x.png", "icon_32x32.png"],
    64: ["icon_32x32@2x.png"],
    128: ["icon_128x128.png"],
    256: ["icon_128x128@2x.png", "icon_256x256.png"],
    512: ["icon_256x256@2x.png", "icon_512x512.png"],
    1024: ["icon_512x512@2x.png"],
}


def render_image(size: int) -> QImage:
    renderer = QSvgRenderer(SVG)
    if not renderer.isValid():
        raise SystemExit("unparseable SVG: " + SVG)
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return image


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("icon.icns can only be generated on macOS")
    app = QApplication(sys.argv[:1])  # noqa: F841
    temporary = tempfile.mkdtemp(prefix="rmip_icon_")
    try:
        iconset = os.path.join(temporary, "icon.iconset")
        os.makedirs(iconset)
        for size, names in ICONSET_NAMES.items():
            image = render_image(size)
            for name in names:
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "PNG")
                with open(os.path.join(iconset, name), "wb") as file:
                    file.write(bytes(buffer.data()))
                buffer.close()
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", ICNS], check=True)
        print("ok", ICNS, os.path.getsize(ICNS), "bytes")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    main()
