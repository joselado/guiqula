"""The icons of the controls (PLAN.md section 7, phase 8, P8): ui/icons.py
draws the vendored Tabler files in the colours of the active theme, and a
change of theme draws them again."""
import gc
import json
import re

import numpy as np
import pytest
import shiboken6
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPalette
from PySide6.QtWidgets import QGridLayout, QToolButton, QWidget

from guiqula.ui import icons, theme

THEMES = ("light", "dark")


@pytest.fixture
def app(qapp):
    theme.apply(qapp, "light")
    yield qapp
    theme.apply(qapp, "light")          # the other modules expect the light theme


def pixels(qicon, size, mode=QIcon.Mode.Normal):
    """(alpha, rgb) arrays of an icon drawn at a size, on a plain screen."""
    image = qicon.pixmap(QSize(size, size), 1.0, mode).toImage()
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    assert image.width() == image.height() == size
    argb = np.frombuffer(image.constBits(), np.uint32).reshape(size, size).copy()
    return argb >> 24, argb & 0xFFFFFF


def ink(qicon, mode=QIcon.Mode.Normal, size=48):
    """The colour of the opaque pixels of an icon, or None when they are not
    all of one colour: at 48 px every icon has some (at 16 px Tabler's
    strokes are 1.3 px wide, mostly antialiased). A stroke crossing itself
    adds up to opaque through rounding, one unit off per channel at most."""
    alpha, rgb = pixels(qicon, size, mode)
    values, counts = np.unique(rgb[alpha == 255], return_counts=True)
    assert len(values), "no opaque pixel"
    common = int(values[counts.argmax()])
    channels = np.stack([(values >> shift) & 0xFF for shift in (16, 8, 0)], axis=-1).astype(int)
    if (np.abs(channels - channels[counts.argmax()]) > 1).any():
        return None
    return f"#{common:06x}"


def selected(theme_name):
    return theme.PALETTES[theme_name][QPalette.ColorRole.HighlightedText]


def test_every_icon_draws_in_the_colours_of_each_theme(app):
    drawn = {}
    for theme_name in THEMES:
        theme.apply(app, theme_name)
        colors = theme.COLORS[theme_name]
        for name in icons.NAMES:
            qicon = icons.icon(name)
            assert not qicon.isNull(), name
            for size in (16, 20):
                alpha, _ = pixels(qicon, size)
                assert (alpha > 0).sum() >= 8, f"{name} at {size} px is empty"
            drawn[theme_name, name] = ink(qicon)
            assert drawn[theme_name, name] == colors["TEXT"], name
            assert ink(qicon, QIcon.Mode.Disabled) == colors["DISABLED"], name
            assert ink(qicon, QIcon.Mode.Selected) == selected(theme_name), name
    for name in icons.NAMES:
        assert drawn["light", name] != drawn["dark", name], name


def test_a_disabled_button_greys_its_icon_with_its_text(app):
    """The disabled icon is in the colour the palette gives disabled text, so
    that a disabled button reads as one, icon and label alike."""
    for theme_name in THEMES:
        theme.apply(app, theme_name)
        text = app.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText)
        assert ink(icons.icon("run"), QIcon.Mode.Disabled) == text.name()


def test_an_icon_in_another_colour_of_the_theme(app):
    """A failed mark is drawn in the error colour (ui/marks.py's ERROR_STATES)."""
    for theme_name in THEMES:
        theme.apply(app, theme_name)
        failed = icons.icon("failed", "ERROR")
        assert ink(failed) == theme.COLORS[theme_name]["ERROR"]
        assert ink(failed, QIcon.Mode.Disabled) == theme.COLORS[theme_name]["DISABLED"]
        assert failed is not icons.icon("failed")
    for color in ("SUBLATTICE", "PURPLE"):
        with pytest.raises(ValueError, match="ERROR"):
            icons.icon("run", color)


def test_an_unknown_name_is_refused_with_the_names_known():
    with pytest.raises(KeyError) as error:
        icons.icon("play")
    message = str(error.value)
    assert "'play'" in message
    assert all(name in message for name in icons.NAMES)


class Window(QWidget):
    """What a window does with the icons: it sets them again after a change
    of theme, and records the theme it set them in."""

    def __init__(self, calls):
        super().__init__()
        self.calls = calls

    def set_icons(self):
        self.calls.append(theme.name)
        self.setWindowIcon(icons.icon("run"))     # raises once Qt deleted the window


def test_a_change_of_theme_empties_the_cache_and_calls_back(app):
    first = icons.icon("run")
    assert icons.icon("run") is first                    # cached
    calls = []
    window = Window(calls)
    remove = icons.on_theme_change(window.set_icons)
    try:
        theme.apply(app, "dark")
        assert calls == ["dark"]
        assert icons.icon("run") is not first            # the cache was emptied
        assert ink(window.windowIcon()) == theme.COLORS["dark"]["TEXT"]
        theme.apply(app, "light")
        assert calls == ["dark", "light"]
        assert ink(window.windowIcon()) == theme.COLORS["light"]["TEXT"]
        remove()
        theme.apply(app, "dark")
        assert calls == ["dark", "light"]                # removed
    finally:
        remove()


def test_a_closed_window_is_dropped_not_called(app):
    """A window collected by Python, or deleted by Qt while its Python object
    lives on, neither stays alive through its callback nor breaks the next
    change of theme."""
    collected, deleted, kept = [], [], []
    window = Window(collected)
    icons.on_theme_change(window.set_icons)
    del window
    gc.collect()
    window = Window(deleted)
    icons.on_theme_change(window.set_icons)
    shiboken6.delete(window)
    alive = Window(kept)
    remove = icons.on_theme_change(alive.set_icons)
    try:
        theme.apply(app, "dark")              # the deleted window raises inside: dropped
        theme.apply(app, "light")
        assert collected == [] and deleted == ["dark"] and kept == ["dark", "light"]
    finally:
        remove()


def test_the_files_the_names_the_table_and_the_licence_agree():
    assert len(set(icons.NAMES)) == len(icons.NAMES)
    files = {path.stem: path for path in icons.DIRECTORY.glob("*.svg")}
    assert set(files) == set(icons.NAMES)        # every file is a name and the reverse
    readme = (icons.DIRECTORY / "README.md").read_text()
    table = dict(re.findall(r"^\| `(\w+)` \| `([\w-]+)` \| 3\.35\.0 \|$", readme, re.M))
    assert set(table) == set(icons.NAMES)
    for name, path in files.items():
        svg = path.read_text()
        assert f"icon-tabler-{table[name]}\"" in svg, f"{name}.svg is not Tabler's {table[name]}"
        assert "currentColor" in svg and not re.search(r"#[0-9a-fA-F]{3,6}\b", svg), name
    licence = (icons.DIRECTORY / "LICENSE").read_text()
    assert licence.startswith("MIT License") and "Paweł Kuna" in licence


def test_importing_the_icons_draws_nothing(run_python):
    """The icons are read and drawn at the first icon() call, never at the
    import of the window's modules (tests/ui/test_startup.py's budget)."""
    result = run_python(
        "import json, sys\n"
        "from guiqula import env\n"
        "env.configure_qt(offscreen=True)\n"
        "from guiqula.ui import icons, theme\n"
        "print(json.dumps(['PySide6.QtSvg' in sys.modules, len(icons._cache)]))\n")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [False, 0]


def sheet(names, size=20):
    """Every icon on a tool button with its name under it, enabled in the
    first of each pair of columns and disabled in the second."""
    page = QWidget()
    grid = QGridLayout(page)
    columns = 5
    for index, name in enumerate(names):
        for enabled in (True, False):
            button = QToolButton()
            button.setIcon(icons.icon(name))
            button.setIconSize(QSize(size, size))
            button.setText(name)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setEnabled(enabled)
            grid.addWidget(button, index // columns, 2 * (index % columns) + (not enabled))
    return page


def test_a_sheet_of_every_icon_in_both_themes(app, shot):
    """The contact sheet to read by eye: ui_dump/<this test>/icons_light.png
    and icons_dark.png, every icon at 20 px, enabled and disabled."""
    for theme_name in THEMES:
        theme.apply(app, theme_name)
        page = sheet(icons.NAMES)
        page.show()
        for _ in range(3):
            app.processEvents()
        assert shot(page, f"icons_{theme_name}").stat().st_size > 0
        page.close()
        page.deleteLater()
