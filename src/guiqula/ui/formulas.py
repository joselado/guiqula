"""Formulas of registry entries as images (the maintainer's answer to the
phase-2 review, 2026-09-26: formulas are shown rendered, not as LaTeX
source). matplotlib's mathtext renders them: no LaTeX installation and no
web engine needed, and matplotlib is in the UI process already. Images are
cached per formula, colour and resolution; the first one costs about a
second (fonts), later ones a few milliseconds."""
import io
from functools import lru_cache

import matplotlib
from matplotlib import mathtext
from PySide6.QtGui import QPixmap

DPI = 130


class FormulaError(ValueError):
    """mathtext cannot parse the formula."""


@lru_cache(maxsize=256)
def png(tex, color="#1e1e1e", dpi=DPI):
    """PNG bytes of a formula (without the $ delimiters), transparent."""
    buffer = io.BytesIO()
    try:
        with matplotlib.rc_context({"savefig.transparent": True}):
            mathtext.math_to_image(f"${tex}$", buffer, dpi=dpi, format="png", color=color)
    except ValueError as error:
        raise FormulaError(f"{tex!r}: {str(error).splitlines()[0]}") from None
    return buffer.getvalue()


def pixmap(tex, color="#1e1e1e", ratio=1.0):
    """A QPixmap of the formula, sharp on a screen with this pixel ratio."""
    image = QPixmap()
    image.loadFromData(png(tex, color, int(round(DPI * ratio))), "PNG")
    image.setDevicePixelRatio(ratio)
    return image
