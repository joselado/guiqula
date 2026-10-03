#!/usr/bin/env python
"""Make the pictures of the start page and the presets gallery
(src/guiqula/resources/thumbnails/, PLAN.md phase 8, package P1).

One offscreen window in the light theme, driven with tools/drive.py's
machinery, draws each picture as the program draws it:

- lattices/<kind>.png: a new document, New system on that lattice, the
  structure canvas;
- classical/<kind>.png: the same for a classical system (its lattice in the
  supercell New system gives it);
- presets/<name>.png: the preset opened, its selected calculation (the first
  one when it names none) run with the Run button, the plot of the result.

A geometry that is not flat is drawn by matplotlib in the 3D projection from
mplot3d's default angle, whatever is installed, so the set is consistent.
The canvas is drawn at 480x360 without its axes for a lattice (the drawing
cropped to its cell, its sites and bonds, and centred), with them for a
plot, and scaled to 160x120 with Pillow, a palette of at most 128 colours
keeping each file at 1 to 9 kB (52 files, about 200 kB in all). Run it from
the checkout after adding a lattice or a preset (tests/ui/test_start.py
fails until its picture exists):

    python tools/make_thumbnails.py              # all of them
    python tools/make_thumbnails.py kagome_lattice haldane_chern   # some, by name

The workers run in a temporary directory (pyqula writes files to the cwd),
which also holds the autosaves and the settings of the driven window.
"""
import argparse
import importlib.util
import io
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "guiqula" / "resources" / "thumbnails"
SIZE = (160, 120)              # the picture of a card (ui/start.py)
CANVAS = (480, 360)            # the canvas drawn, three times the picture
COLOURS = 128                  # the palette of the PNG files
MARGIN = 0.06                  # around a lattice's drawing, of the picture's size
STRONG = 60                    # a difference from the background (0 to 255) drawn opaque
GROW = 0.15                    # of the opaque drawing's size, kept around it on each side


def load_drive():
    """tools/drive.py as a module: its sys.path insert, settle()."""
    spec = importlib.util.spec_from_file_location("drive", ROOT / "tools" / "drive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait(app, seconds=0.5):
    """Let the window settle: timers, deferred drawings, the centring."""
    from PySide6.QtTest import QTest
    for _ in range(max(1, int(seconds / 0.05))):
        app.processEvents()
        QTest.qWait(50)


def to_image(widget):
    """The widget grabbed, as a Pillow image."""
    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    widget.grab().save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGB")


def crop_to_drawing(image):
    """The drawing of a lattice framed at 4:3 with a margin: the frame holds
    what is drawn opaque (the cell, its sites and bonds) and a little of the
    faint neighbours around it, which in 3D spread far from the cell."""
    from PIL import Image, ImageChops
    background = image.getpixel((0, 0))
    difference = ImageChops.difference(image, Image.new("RGB", image.size, background))
    difference = difference.convert("L")
    drawn = difference.getbbox()
    if drawn is None:
        return image
    strong = difference.point(lambda v: 255 if v > STRONG else 0).getbbox() or drawn
    left, top, right, bottom = strong
    grow_x, grow_y = GROW * (right - left), GROW * (bottom - top)
    left, top = max(drawn[0], left - grow_x), max(drawn[1], top - grow_y)
    right, bottom = min(drawn[2], right + grow_x), min(drawn[3], bottom + grow_y)
    box = tuple(int(round(v)) for v in (left, top, right, bottom))
    width, height = box[2] - box[0], box[3] - box[1]
    ratio = SIZE[0] / SIZE[1]
    frame_w = max(width, height * ratio) * (1 + 2 * MARGIN)
    frame_h = frame_w / ratio
    frame = Image.new("RGB", (int(round(frame_w)), int(round(frame_h))), background)
    frame.paste(image.crop(box), ((frame.width - width) // 2, (frame.height - height) // 2))
    return frame


def save(image, path):
    """Scaled to the picture's size, with a small palette, optimized."""
    from PIL import Image
    image = image.resize(SIZE, Image.Resampling.LANCZOS)
    image = image.quantize(colors=COLOURS, method=Image.Quantize.MEDIANCUT,
                           dither=Image.Dither.NONE)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return path.stat().st_size


def lattice_picture(app, window, drive, kind, classical=False, timeout=300):
    window.session.act("new")
    if classical:
        window.new_classical_system(kind)
    else:
        window.new_system(kind)
    window.select("")
    drive.settle(app, window, window.session, timeout, builds_only=True)
    wait(app)
    structure = window.structure
    if structure.build is None:
        raise RuntimeError(window.session.build_errors.get(window.current_system())
                           or "the system was not built")
    structure.canvas.setFixedSize(*CANVAS)
    wait(app)
    for ax in structure.figure.axes:
        ax.set_axis_off()
        for collection in ax.collections:     # the selection, empty: drawn at the corner
            if len(collection.get_offsets()) == 0:
                collection.set_visible(False)
    structure.canvas.draw()
    app.processEvents()
    return crop_to_drawing(to_image(structure.canvas))


def preset_picture(app, window, drive, name, timeout=900):
    from PySide6.QtWidgets import QPushButton
    session = window.session
    session.act("load", path=name)
    drive.settle(app, window, session, timeout, builds_only=True)
    document = session.document
    calc = (document.ui or {}).get("calculation") or document.calculations[0].id
    window.select_calculation(calc)
    window.run_button.click()
    if calc not in session.calc_jobs and window.cost_bar.isVisible():
        window.cost_bar.findChild(QPushButton, "runAnywayButton").click()
    job = session.calc_jobs.get(calc)
    if job is None:
        raise RuntimeError(f"{calc} did not start")
    deadline = time.monotonic() + timeout
    while not job.done and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    if job.status != "done":
        raise RuntimeError(f"{calc}: {job.status}")
    drive.settle(app, window, session, timeout)
    view = window.plots[calc]
    window.show_result(calc)
    view.canvas.setFixedSize(*CANVAS)
    wait(app, 1.0)
    return to_image(view.canvas)


def jobs(names):
    """(folder, name, kind of picture) of every picture, or of the ones named."""
    from guiqula.io import project
    from guiqula.registry import base as registry
    from guiqula.ui.mainwindow import CLASSICAL_STARTS
    every = ([("lattices", e.kind, "lattice") for e in registry.entries("lattice")]
             + [("classical", kind, "classical") for kind in CLASSICAL_STARTS]
             + [("presets", name, "preset") for name in project.presets()])
    if not names:
        return every
    unknown = set(names) - {name for _, name, _ in every}
    if unknown:
        raise SystemExit(f"unknown names {sorted(unknown)}; known: "
                         f"{sorted(name for _, name, _ in every)}")
    return [job for job in every if job[1] in names]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("names", nargs="*", help="lattice kinds, classical kinds or presets")
    parser.add_argument("--timeout", type=float, default=900, help="seconds per picture")
    args = parser.parse_args(argv)
    scratch = tempfile.mkdtemp(prefix="guiqula-thumbnails-")
    os.environ["GUIQULA_DATA_DIR"] = str(Path(scratch) / "data")
    os.environ["GUIQULA_CONFIG_DIR"] = str(Path(scratch) / "config")
    os.chdir(scratch)
    drive = load_drive()
    drive.env.configure_qt(offscreen=True)
    from guiqula.ui.app import build_main_window, create_application
    app = create_application()
    window = build_main_window()
    window.resize(1600, 1000)
    window.show()
    app.processEvents()
    window.set_theme("light")
    window.set_renderer_3d("matplotlib", remember=False)
    window.set_projection("auto")
    window.start_session(None)
    failed = []
    try:
        for folder, name, kind in jobs(args.names):
            started = time.monotonic()
            try:
                if kind == "preset":
                    image = preset_picture(app, window, drive, name, args.timeout)
                else:
                    image = lattice_picture(app, window, drive, name, kind == "classical",
                                            args.timeout)
                size = save(image, OUT / folder / f"{name}.png")
            except Exception as error:
                failed.append(name)
                print(f"{folder}/{name}: FAILED: {error}", flush=True)
                continue
            finally:
                window.structure.canvas.setMinimumSize(0, 0)
                window.structure.canvas.setMaximumSize(16777215, 16777215)
            print(f"{folder}/{name}.png: {size / 1024:.1f} kB, "
                  f"{time.monotonic() - started:.1f} s", flush=True)
    finally:
        window.close()
        app.processEvents()
    if failed:
        print(f"failed: {failed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
