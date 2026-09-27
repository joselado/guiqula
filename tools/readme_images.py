#!/usr/bin/env python
"""Make the screenshots of README.md (docs/images/*.png) with tools/drive.py.

Each image is a preset opened in the offscreen window, a few commands, a
calculation run with the Run button, and a screenshot: of the whole window
(the picture at the top), or of one figure with the docks hidden, cropped
to its content. Run it from the checkout after a change that shows in them:

    python tools/readme_images.py            # all of them
    python tools/readme_images.py hofstadter # some of them, by name

The workers run in a temporary directory (pyqula writes files to the cwd),
which also holds the autosaves and the settings of the driven windows.
Needs Pillow for the cropping.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"

# code for --python: hide the bottom docks (the picture at the top) or all of them (a
# figure alone), then let the layout settle before the screenshot
SETTLE = ("from PySide6.QtTest import QTest\n"
          "for _ in range(5):\n    app.processEvents(); QTest.qWait(100)\n")
TIDY = ("from PySide6.QtWidgets import QDockWidget\n"
        "for d in window.findChildren(QDockWidget):\n"
        "    if d.windowTitle() in ('Log', 'Console'): d.hide()\n" + SETTLE)
ALONE = ("from PySide6.QtWidgets import QDockWidget\n"
         "for d in window.findChildren(QDockWidget): d.hide()\n" + SETTLE)


def do(**command):
    return ["--do", json.dumps(command)]


def figure(calc, size="1000x640"):
    return ["--size", size, "--python", ALONE, "--widget", f"plotCanvas_{calc}"]


BERRY = do(do="set_param", entry="c3", name="nk", value=80)
GATE = do(do="add_term", system="s1", kind="onsite",
          params={"mu": "0.5*exp(-(x**2+y**2)/6)"}) + do(do="preview", entry="t1", param="mu")

IMAGES = {       # name: preset and driver arguments
    "hero": ["kane_mele_ribbon", *do(do="select", entry="t1"), "--run", "c1",
             "--size", "1400x800", "--python", TIDY],
    "kagome_bands": ["kagome_flat_band", "--run", "c1", *figure("c1")],
    "kagome_dos": ["kagome_flat_band", "--run", "c2", *figure("c2")],
    "haldane_berry": ["haldane_chern", *BERRY, "--run", "c3", *figure("c3", "800x700")],
    "haldane_phase": ["haldane_chern", "--run", "c4", "--timeout", "1800",
                      *figure("c4", "800x700")],
    "kane_mele_bands": ["kane_mele_ribbon", "--run", "c1", *figure("c1")],
    "hofstadter": ["hofstadter_ribbon", "--run", "c1", *figure("c1")],
    "zigzag_magnetization": ["zigzag_ribbon_magnetism", "--run", "c2",
                             *figure("c2", "800x640")],
    "majorana_ldos": ["majorana_wire", "--run", "c1", *figure("c1")],
    "majorana_dos": ["majorana_wire", "--run", "c2", *figure("c2")],
    "aubry_andre_dos": ["aubry_andre", "--run", "c1", *figure("c1")],
    "aubry_andre_ldos": ["aubry_andre", "--run", "c2", *figure("c2")],
    "island_ldos": ["graphene_island", "--run", "c2", *figure("c2", "800x700")],
    "field_gate": ["graphene_island", *GATE, "--size", "800x700", "--python", ALONE,
                   "--widget", "structureCanvas"],
    "triangular": ["triangular_spins", "--run", "c1", *figure("c1", "900x640")],
    "texture_spins": ["texture_exchange", "--run", "c1", *figure("c1")],
}


def crop(path):
    """Cut the white margins of a figure (10 px left), and write it back
    losslessly: a palette only when the image has 256 colours or fewer."""
    from PIL import Image, ImageChops
    image = Image.open(path).convert("RGB")
    if path.stem != "hero":
        mask = ImageChops.difference(image, Image.new("RGB", image.size, "white"))
        box = mask.convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
        if box:
            pad = 10
            image = image.crop((max(box[0] - pad, 0), max(box[1] - pad, 0),
                                min(box[2] + pad, image.width), min(box[3] + pad, image.height)))
    colours = image.getcolors(maxcolors=256)
    if colours is not None:
        image = image.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                               dither=Image.Dither.NONE)
    image.save(path, optimize=True)


def main(names):
    unknown = [n for n in names if n not in IMAGES]
    if unknown:
        print(f"unknown images {unknown}; known: {sorted(IMAGES)}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    failed = []
    with tempfile.TemporaryDirectory() as scratch:
        environment = dict(os.environ, GUIQULA_DATA_DIR=str(Path(scratch) / "data"),
                           GUIQULA_CONFIG_DIR=str(Path(scratch) / "config"))
        for name in names or IMAGES:
            path = OUT / f"{name}.png"
            print(f"{name} ...", flush=True)
            done = subprocess.run([sys.executable, str(ROOT / "tools" / "drive.py"),
                                   *IMAGES[name], "--shot", str(path)],
                                  cwd=scratch, env=environment, capture_output=True,
                                  text=True)
            if done.returncode != 0 or not path.is_file():
                failed.append(name)
                print(done.stderr[-2000:], file=sys.stderr)
                continue
            crop(path)
    if failed:
        print(f"failed: {failed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
