#!/usr/bin/env python
"""Render guiqula's icon (src/guiqula/resources/guiqula.svg) to the files
the program and the installers use:

- guiqula.png (256 px): the window icon and the Linux desktop entry's;
- guiqula.ico (16 to 256 px): Windows (the Start menu shortcut, the
  PyInstaller bundle, the installer);
- guiqula.icns (128 to 1024 px): the macOS app bundles;

all in src/guiqula/resources, next to the SVG (``guiqula desktop`` uses
them from the installed package).

Qt draws the SVG; the ICO and ICNS containers are written here (both hold
PNG images), since Qt's writers for them are not in every PySide6 build.
Run it after changing the SVG:  python tools/make_icons.py
"""
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

SVG = REPO / "src" / "guiqula" / "resources" / "guiqula.svg"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS_TYPES = {128: b"ic07", 256: b"ic08", 512: b"ic09", 1024: b"ic10"}


def renderer():
    from guiqula import env
    env.configure_qt(offscreen=True)
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    app = QGuiApplication.instance() or QGuiApplication([])
    svg = QSvgRenderer(str(SVG))

    def png(size):
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        svg.render(painter, QRectF(0, 0, size, size))
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(data.data())
    png.app = app
    return png


def ico(images):
    """An ICO file of PNG images {size: bytes}."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in sorted(images.items()):
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data),
                               offset + len(blobs))
        blobs += data
    return header + entries + blobs


def icns(images):
    """An ICNS file of PNG images {size: bytes}."""
    body = b"".join(ICNS_TYPES[size] + struct.pack(">I", 8 + len(data)) + data
                    for size, data in sorted(images.items()))
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def main():
    png = renderer()
    resources = SVG.parent
    (resources / "guiqula.png").write_bytes(png(256))
    (resources / "guiqula.ico").write_bytes(ico({s: png(s) for s in ICO_SIZES}))
    (resources / "guiqula.icns").write_bytes(icns({s: png(s) for s in ICNS_TYPES}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
