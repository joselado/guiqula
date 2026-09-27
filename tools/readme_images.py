#!/usr/bin/env python
"""Make the screenshots of README.md (docs/images/*.png) with tools/drive.py.

Each image is the whole window: a preset opened offscreen, an entry
selected (its form in the Properties dock), calculations run with the Run
button (the last one's result in front), with the Log and Console docks
hidden to leave the room to the plot. Run it from the checkout after a
change that shows in them:

    python tools/readme_images.py            # all of them
    python tools/readme_images.py hofstadter # some of them, by name

The workers run in a temporary directory (pyqula writes files to the cwd),
which also holds the autosaves and the settings of the driven windows.
Needs Pillow to write the images compactly.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
SIZE = "1400x800"

# code for --python: hide the bottom docks, then let the layout settle before the screenshot
TIDY = ("from PySide6.QtWidgets import QDockWidget\n"
        "from PySide6.QtTest import QTest\n"
        "for d in window.findChildren(QDockWidget):\n"
        "    if d.windowTitle() in ('Log', 'Console'): d.hide()\n"
        "for _ in range(5):\n    app.processEvents(); QTest.qWait(100)\n")


def do(**command):
    return ["--do", json.dumps(command)]


def window(preset, select, *runs, commands=(), timeout=None):
    """Arguments of drive.py: the preset, commands, the entry selected, the
    calculations run (the last one's result in front)."""
    arguments = [preset, *commands, *do(do="select", entry=select)]
    for calc in runs:
        arguments += ["--run", calc]
    if timeout:
        arguments += ["--timeout", str(timeout)]
    return arguments + ["--size", SIZE, "--python", TIDY]


GATE = do(do="add_term", system="s1", kind="onsite", params={"mu": "0.5*exp(-(x**2+y**2)/6)"})

IMAGES = {       # name: driver arguments
    "hero": window("kane_mele_ribbon", "t1", "c1"),
    "kagome": window("kagome_flat_band", "c1", "c2", "c1"),
    "haldane": window("haldane_chern", "c4", "c4", timeout=1800),
    "kane_mele": window("kane_mele_ribbon", "c2", "c2"),
    "hofstadter": window("hofstadter_ribbon", "t1", "c1"),
    "zigzag": window("zigzag_ribbon_magnetism", "s1/meanfield", "c1", "c2"),
    "majorana": window("majorana_wire", "t3", "c2", "c1"),
    "aubry_andre": window("aubry_andre", "t1", "c2", "c1"),
    "island": window("graphene_island", "op1", "c1", "c2"),
    "island_gate": window("graphene_island", "t1", commands=GATE + do(do="preview", entry="t1",
                                                                      param="mu")),
    "triangular": window("triangular_spins", "t1", "c1"),
    "texture": window("texture_exchange", "t2", "c1"),
}


def compact(path):
    """Write the image back losslessly and optimized (a palette only when it
    has 256 colours or fewer)."""
    from PIL import Image
    image = Image.open(path).convert("RGB")
    if image.getcolors(maxcolors=256) is not None:
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
            compact(path)
    if failed:
        print(f"failed: {failed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
