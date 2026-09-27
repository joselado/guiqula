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

from guiqula.ui import theme

DPI = 130


class FormulaError(ValueError):
    """mathtext cannot parse the formula."""


def png(tex, color=None, dpi=DPI):
    """PNG bytes of a formula (without the $ delimiters), transparent, in
    the text colour of the active theme unless a colour is given."""
    return _png(tex, color or theme.TEXT, dpi)


@lru_cache(maxsize=512)
def _png(tex, color, dpi):
    buffer = io.BytesIO()
    try:
        with matplotlib.rc_context({"savefig.transparent": True}):
            mathtext.math_to_image(f"${tex}$", buffer, dpi=dpi, format="png", color=color)
    except ValueError as error:
        raise FormulaError(f"{tex!r}: {str(error).splitlines()[0]}") from None
    return buffer.getvalue()


def pixmap(tex, color=None, ratio=1.0):
    """A QPixmap of the formula, sharp on a screen with this pixel ratio."""
    image = QPixmap()
    image.loadFromData(png(tex, color, int(round(DPI * ratio))), "PNG")
    image.setDevicePixelRatio(ratio)
    return image


def html(tex, color=None):
    """The formula as an inline image for Qt rich text (a tooltip); its
    source in code when mathtext cannot draw it."""
    import base64
    import html as html_tools
    try:
        data = base64.b64encode(png(tex, color)).decode()
    except FormulaError:
        return f"<code>{html_tools.escape(tex)}</code>"
    return f'<img src="data:image/png;base64,{data}">'


def entry_tooltip(spec, color=None):
    """Rich text for a registry entry (palettes): its label, its one-line
    doc, its formula as an image and what it needs."""
    import html as html_tools
    parts = [f"<b>{html_tools.escape(spec.label)}</b>"]
    if spec.doc:
        parts.append(html_tools.escape(spec.doc))
    if spec.formula:
        parts.append(html(spec.formula, color))
    needs = spec.requires if not callable(spec.requires) else ()
    if needs:
        parts.append(f"<i>makes the Hamiltonian {' and '.join(needs)}</i>"
                     .replace("spin", "spinful").replace("nambu", "Nambu"))
    if spec.runs_code:
        parts.append("<i>Python code: runs only in a trusted document</i>")
    if spec.plugin:
        parts.append(f"<i>from the plugin {html_tools.escape(spec.plugin)}</i>")
    return "<br>".join(parts)
