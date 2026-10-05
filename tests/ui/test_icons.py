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

from guiqula.ui import icons, marks, theme

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


def ink(qicon, mode=QIcon.Mode.Normal, size=24):
    """The colour of the opaque pixels of an icon, or None when they are not
    all of one colour: at 24 px, the largest rendering on a plain screen,
    Tabler's strokes are 2 px wide and every icon has some (at 16 px they are
    1.3 px wide, mostly antialiased). A stroke crossing itself adds up to
    opaque through rounding, one unit off per channel at most."""
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
    table = dict(re.findall(r"^\| `(\w+)` \| `([\w/-]+)` \| 3\.35\.0 \|$", readme, re.M))
    assert set(table) == set(icons.NAMES)
    for name, path in files.items():
        svg = path.read_text()
        style, _, tabler = table[name].rpartition("/")         # outline unless named
        assert f"icons-tabler-{style or 'outline'} icon-tabler-{tabler}\"" in svg, \
            f"{name}.svg is not Tabler's {table[name]}"
        assert "currentColor" in svg and not re.search(r"#[0-9a-fA-F]{3,6}\b", svg), name
    licence = (icons.DIRECTORY / "LICENSE").read_text()
    assert licence.startswith("MIT License") and "Paweł Kuna" in licence



def test_cancel_is_a_filled_stop_square_not_an_empty_check_box(app):
    """Tabler's outline stop is a hollow rounded square, which at 16 px,
    greyed while nothing runs, reads as the empty check box of the canvas
    bar's 3D switch; Cancel is the filled square, whose middle is ink."""
    for name in THEMES:
        theme.apply(app, name)
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Disabled):
            alpha, _ = pixels(icons.icon("cancel"), 16, mode)
            assert alpha[6:10, 6:10].min() == 255, (name, mode)
            alpha, _ = pixels(icons.icon("run"), 16, mode)        # an outline beside it
            assert alpha[7:9, 7:9].max() < 255, (name, mode)
    theme.apply(app, "light")

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


def test_follow_sets_the_icons_at_the_first_show_and_after_a_change_of_theme(app):
    """A widget out of sight costs nothing: follow() sets its icons when it is
    first shown, and from then on after every change of theme."""
    calls = []
    window = Window(calls)
    icons.follow(window, window.set_icons)
    theme.apply(app, "dark")                       # not shown yet: nothing drawn
    assert calls == [] and window.windowIcon().isNull()
    window.show()
    app.processEvents()
    assert calls == ["dark"] and ink(window.windowIcon()) == theme.COLORS["dark"]["TEXT"]
    window.hide()
    window.show()                                  # the first show only
    assert calls == ["dark"]
    theme.apply(app, "light")
    assert calls == ["dark", "light"]
    shown = Window([])
    shown.show()
    icons.follow(shown, shown.set_icons)           # shown already: at once
    assert shown.calls == ["light"]
    window.close()
    shown.close()


@pytest.fixture(scope="module")
def window(qapp):
    """The window at the small laptop's size on a preset, its controls shown:
    the structure canvas, the k-space tab, a result's view with its status
    row, a form."""
    from guiqula.ui.app import build_main_window
    theme.apply(qapp, "light")
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def shown_everything(window, qtbot):
    from PySide6.QtWidgets import QApplication
    from guiqula.ui.mainwindow import KSPACE_TAB
    qtbot.waitUntil(lambda: window.session.build_is_current("s1"), timeout=120_000)
    window.viewport.setCurrentIndex(KSPACE_TAB)
    window.select("t1")
    window.show_result("c1")
    view = window.plots["c1"]
    view.set_status("stale")                      # the status row, shown
    for _ in range(5):
        QApplication.processEvents()
    return view


# the controls package P8 names (PLAN.md section 7), by objectName, with their icon
WINDOW_ICONS = {"newSystemButton": "new", "addButton": "add", "runButton": "run",
                "cancelButton": "cancel", "autoRerunButton": "follow", "logToggle": "log"}
BAR_ICONS = {"{key}Fit": "fit", "{key}Pan": "pan", "{key}Zoom": "zoom_in",
             "{key}SaveImage": "image"}
STRUCTURE_ICONS = {"tool_pick": "pick", "tool_box": "box", "tool_lasso": "lasso",
                   "selectSitesButton": "select", "regionFromSelectionButton": "region",
                   "calculateOnSelectionButton": "calculation",
                   "removeSelectedButton": "remove", "canvasViewLabel": "show",
                   "view3dBox": "3d", "paintTool": "paint", "structureSceneReset": "fit",
                   "structureSceneView": "view", "structureSceneSave": "image"}
PLOT_ICONS = {"fit_c1": "fit", "pan_c1": "pan", "zoom_c1": "zoom_in", "saveImage_c1": "image",
              "pickTool_c1": "pick", "boxTool_c1": "box", "lassoTool_c1": "lasso",
              "overlay_c1": "overlay", "export_c1": "export", "saveData_c1": "data",
              "detach_c1": "detach", "plotRun_c1": "run", "plotCancel_c1": "cancel"}


def drawn(widget):
    """The icon a control shows (a label's pixmap as an icon)."""
    from PySide6.QtWidgets import QLabel
    if isinstance(widget, QLabel):
        return QIcon(widget.pixmap())
    return widget.icon()


def same(widget, name, color="TEXT"):
    """Whether a control shows the icon of a name: a button's ink, a label's
    pixmap (drawn at 16 px)."""
    from PySide6.QtWidgets import QLabel
    if isinstance(widget, QLabel):
        expected = icons.icon(name, color).pixmap(icons.size(), widget.devicePixelRatioF())
        return widget.pixmap().toImage() == expected.toImage()
    return ink(widget.icon()) == ink(icons.icon(name, color))


def test_every_control_the_package_names_carries_an_icon(window, qtbot):
    from PySide6.QtWidgets import QWidget
    from guiqula.ui import outliner as tree
    view = shown_everything(window, qtbot)
    names = dict(WINDOW_ICONS)
    for key in ("structure", "kspace"):
        names.update({name.format(key=key): icon for name, icon in BAR_ICONS.items()})
    names.update(STRUCTURE_ICONS)
    names.update(PLOT_ICONS)
    missing = [name for name in names
               if window.findChild(QWidget, name) is None or drawn(
                   window.findChild(QWidget, name)).isNull()]
    assert not missing
    for name, icon in names.items():               # the icon named, in the theme's text
        assert same(window.findChild(QWidget, name), icon), name
    # the text of the bars' controls stays, as the start of their tooltip
    fit = window.findChild(QWidget, "structureFit")
    assert fit.text() == "Fit" and fit.toolTip().startswith("Fit: ")
    assert fit.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    box = window.structure.box_3d                  # a check box shows its icon alone
    assert box.text() == "" and box.toolTip().startswith("3D: ") and \
        box.accessibleName() == "3D"
    assert window.findChild(QWidget, "canvasViewLabel").accessibleName() == "Show"
    for name in ("newSystemButton", "addButton", "runButton", "logToggle"):   # beside
        assert window.findChild(QWidget, name).toolButtonStyle() == \
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon, name
    assert window.cancel_button.toolTip().startswith("Cancel: ") and \
        window.auto_rerun_button.toolTip().startswith("Follow: ")
    assert same(view.status.mark, "stale")                     # the status row's mark
    assert view.status.text.full.startswith(marks.STALE) and \
        not view.status.text.text().startswith(marks.STALE)    # drawn as the icon beside
    view.set_status("done")
    form = window.properties.form                  # t1's form and its ?
    assert ink(form.help_button.icon()) == ink(icons.icon("help"))
    tabs = window.viewport
    assert not tabs.tabIcon(0).isNull() and not tabs.tabIcon(1).isNull()
    # the outliner: the kind of each row, and its marks drawn as icons
    kinds = {item_id: window.outliner.item(item_id).data(0, tree.KIND_ROLE)
             for item_id in ("s1", "s1/base", "op1", "t1", "s1/meanfield", "c1",
                             "s1/geometry")}
    assert kinds == {"s1": "structure", "s1/base": "lattice", "op1": "op", "t1": "term",
                     "s1/meanfield": "meanfield", "c1": "calculation", "s1/geometry": None}
    assert tree.status_parts(f"{marks.DONE} 1") == [("done", ""), (None, "1")]
    assert tree.status_parts(marks.FAILED, "invalid") == [("invalid", "")]
    assert tree.status_parts(marks.FAILED, "failed") == [("failed", "")]
    assert tree.status_parts("70%", "running") == [("running", "70%")]
    assert tree.status_parts(f"m {marks.LOCKED}") == [(None, "m"), ("locked", "")]
    assert tree.status_parts("spinful") == [(None, "spinful")]


def test_the_menus_get_their_icons_when_they_first_open(window):
    from PySide6.QtWidgets import QApplication, QMenu
    menu = next(m for m in window.findChildren(QMenu) if m.title() == "&File")
    new = next(a for a in menu.actions() if a.text() == "&New")
    menu.popup(window.mapToGlobal(window.rect().center()))
    QApplication.processEvents()
    menu.hide()
    assert ink(new.icon()) == ink(icons.icon("new"))



def test_a_checkable_menu_entry_keeps_its_check_box(window):
    """Fusion draws a checkable menu entry that has an icon without its check
    box, its state a faint frame around the icon: Re-run cheap results
    automatically lost its box beside Run calculations at once."""
    from PySide6.QtWidgets import QApplication, QMenu
    menus = [m for m in window.findChildren(QMenu)
             if m.title() in ("&File", "&Edit", "&View", "&Run", "&Help")]
    for menu in menus:                                  # their icons, set at the first opening
        menu.popup(window.mapToGlobal(window.rect().center()))
        QApplication.processEvents()
        menu.hide()
    checkable = [a for m in menus for a in m.actions() if a.isCheckable()]
    assert window.auto_rerun_action in checkable
    assert [a.text() for a in checkable if not a.icon().isNull()] == []
    assert any(not a.icon().isNull() for m in menus for a in m.actions())


def test_the_run_buttons_menu_has_its_icons(window, qtbot, qapp):
    """The other calculations to run and Run every stale result, in the
    active theme each time the menu opens."""
    shown_everything(window, qtbot)
    try:
        for name in THEMES:
            window.set_theme(name)
            listed = window._fill_run_menu()
            actions = {a.objectName(): a for a in window.run_menu.actions()}
            assert "runStaleAction" in listed and any(n.startswith("runCalc_") for n in listed)
            assert ink(actions["runStaleAction"].icon()) == ink(icons.icon("run_stale")) == \
                theme.COLORS[name]["TEXT"]
            for key in listed:
                if key.startswith("runCalc_"):
                    assert ink(actions[key].icon()) == theme.COLORS[name]["TEXT"], key
    finally:
        window.set_theme("light")

def test_the_icons_change_with_the_theme(window, qtbot, qapp):
    shown_everything(window, qtbot)
    controls = [window.run_button, window.structure.bar.fit_button, window.plots["c1"].export,
                window.properties.form.help_button]
    try:
        for name in THEMES:
            window.set_theme(name)
            for control in controls:
                assert ink(control.icon()) == theme.COLORS[name]["TEXT"], control.objectName()
            assert ink(window.run_button.icon(), QIcon.Mode.Disabled) == \
                theme.COLORS[name]["DISABLED"]
    finally:
        window.set_theme("light")


def test_the_icons_grow_with_the_interface_text(window, qtbot, qapp):
    """At large interface text the controls' icons are 20 px, drawn at that
    size, and 16 px again at normal text, set again as at a change of theme."""
    shown_everything(window, qtbot)
    view = window.plots["c1"]
    controls = [window.run_button, window.structure.bar.fit_button, view.export,
                view.status.run, window.properties.form.help_button]
    try:
        for name, side in (("large", icons.LARGE), ("normal", icons.SIZE)):
            window.set_ui_text(name, remember=False)
            qtbot.waitUntil(lambda: window.run_button.iconSize().width() == side)
            controls[-1] = window.properties.form.help_button        # the form made again
            for control in controls:
                assert control.iconSize().width() == side, (name, control.objectName())
            assert view.status.mark.width() == side
            assert side in [s.width() for s in window.run_button.icon().availableSizes()]
            assert ink(window.run_button.icon()) == theme.COLORS["light"]["TEXT"]
    finally:
        window.set_ui_text("normal", remember=False)


def test_the_start_page_and_its_buttons(qapp):
    from guiqula.ui.app import build_main_window
    theme.apply(qapp, "light")
    window = build_main_window()
    window.show()
    qapp.processEvents()
    page = window.start_page
    assert ink(page.open_button.icon()) == ink(icons.icon("open"))
    assert ink(page.search_icon.icon()) == ink(icons.icon("search"))
    assert "+ of the Hamiltonian row" in page.footer.text()       # not "in the workspace"
    window.close()
