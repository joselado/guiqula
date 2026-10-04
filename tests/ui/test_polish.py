"""Phase 5, part 1 (PLAN.md section 7, design items 8 to 11): the settings
file, light and dark themes, keyboard shortcuts, undo with named steps and
a history, the earlier result back after an undo."""
import pytest
from matplotlib.colors import to_hex
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTableWidget

from guiqula.io import settings
from guiqula.ui import shortcuts, theme
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()
    theme.apply(QApplication.instance(), "light")
    theme.set_text_size("normal")


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)


def bound_actions(window):
    """{shortcut id: [QAction]} of the actions bound through the table."""
    out = {}
    for action in window.findChildren(QAction):
        sid = action.property(shortcuts.ID_PROPERTY)
        if sid:
            out.setdefault(sid, []).append(action)
    return out


def test_every_shortcut_is_bound_once_and_none_is_ambiguous(window):
    bound = bound_actions(window)
    for sid, key_list, context, _ in shortcuts.SHORTCUTS:
        if context in shortcuts.HANDLED_CONTEXTS:
            assert sid not in bound
            continue
        assert len(bound.get(sid, [])) == 1, sid
        action = bound[sid][0]
        assert [s.toString() for s in action.shortcuts()] == \
            [shortcuts.QKeySequence(k).toString() for k in key_list], sid
    keys = {}
    for action in window.findChildren(QAction):
        for sequence in action.shortcuts():
            keys.setdefault(sequence.toString(), []).append(action)
    for key, actions in keys.items():
        if len(actions) == 1:
            continue
        contexts = [a.shortcutContext() for a in actions]
        assert all(c == Qt.ShortcutContext.WidgetShortcut for c in contexts), key
        owners = [a.parent() for a in actions]
        assert len(set(map(id, owners))) == len(owners), key     # one per widget


def test_canvas_keys_and_the_shortcuts_dialog(window, qtbot):
    settle(qtbot, window)
    canvas = window.structure.canvas
    window.activateWindow()
    canvas.setFocus()
    qtbot.waitUntil(lambda: canvas.hasFocus(), timeout=5000)
    QTest.keyClick(canvas, Qt.Key.Key_B)
    assert window.structure.tool == "box"
    QTest.keyClick(canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert len(window.structure.selected()) == 8
    QTest.keyClick(canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.ShiftModifier)
    assert len(window.structure.selected()) == 0
    QTest.keyClick(canvas, Qt.Key.Key_P)
    assert window.structure.tool == "pick"
    assert window.focus_search() == "geometry_op"         # the Add menu of the workspace
    window.palette_menus["geometry_op"].hide()
    window.set_workspace("hamiltonian")
    assert window.focus_search() == "term"
    window.palette_menus["term"].hide()
    window.set_workspace("geometry")
    dialog = window.show_shortcuts()
    rows = shortcuts.rows()
    table = dialog.findChild(QTableWidget, "shortcutsTable")
    assert table.rowCount() == len(rows)
    assert table.item(0, 1).text() == rows[0][1]
    dialog.close()


def test_undo_names_its_step_and_the_history_goes_back(window, qtbot):
    session = window.session
    session.act("load", path="honeycomb_zeeman_rashba")
    settle(qtbot, window)
    assert not window.undo_action.isEnabled() and window.undo_action.text() == "&Undo"
    session.do("set_param", entry="t1", name="m", value=[0, 0, 0.4])
    session.do("set_enabled", entry="t2", enabled=False)
    new = session.do("add_term", system="s1", kind="haldane")
    assert window.undo_action.text() == "&Undo add term haldane coupling"
    window.select("c1")
    window._fill_history()
    texts = [a.text() for a in window.history_menu.actions()]
    assert texts == ["undo: add term haldane coupling", "undo: disable t2", "undo: set m of t1"]
    window.history_menu.actions()[1].trigger()          # back to before "disable t2"
    assert session.document.find("t2")[-1].enabled and window.selected == "t2"
    assert window.outliner.current_id() == "t2" and window.current_tab() == "c1"
    assert window.redo_action.text() == "&Redo disable t2"
    window._fill_history()
    assert [a.text() for a in window.history_menu.actions() if a.text()] == \
        ["redo: add term haldane coupling", "redo: disable t2", "undo: set m of t1"]
    window.redo_action.trigger()
    window.redo_action.trigger()
    assert window.selected == new
    window.undo_action.trigger()                         # the entry is gone: its system
    assert window.selected == "s1"
    history = session.act("history")
    assert history["redo"] == ["add term haldane coupling"]
    assert session.act("undo", steps=2)["undo"] == []


def colour_at(image, x, y):
    return QColor(image.pixel(x, y)).name()


def test_dark_theme_and_back(window, qtbot, shot):
    session = window.session
    session.act("load", path="honeycomb_zeeman_rashba")
    settle(qtbot, window)
    job = session.run_calculation("c1", wait=True, timeout=600)
    assert job.status == "done", job.error
    window.select("t1")
    window.show_result("c1")
    qtbot.waitUntil(lambda: window.plots["c1"].result is not None, timeout=10_000)
    assert window.session.act("theme", name="dark") == "dark"
    app = QApplication.instance()
    assert app.palette().color(QPalette.ColorRole.Window).name() == "#2b2b2b"
    assert window.theme_actions["dark"].isChecked()
    figure = window.structure.figure
    assert to_hex(figure.get_facecolor()) == theme.COLORS["dark"]["FIGURE"]
    ax = window.structure.ax
    assert to_hex(ax.get_facecolor()) == theme.COLORS["dark"]["AXES"]
    labels = ax.get_xticklabels()
    assert labels and to_hex(labels[0].get_color()) == theme.COLORS["dark"]["TEXT"]
    view = window.plots["c1"]
    assert to_hex(view.figure.get_facecolor()) == theme.COLORS["dark"]["FIGURE"]
    assert to_hex(view.ax.title.get_color()) == theme.COLORS["dark"]["TEXT"]
    window.message("an error, in the status bar", error=True)
    message = window.status_message
    assert message.palette().color(QPalette.ColorRole.WindowText).name() == \
        theme.COLORS["dark"]["ERROR"]
    window.viewport.setCurrentIndex(0)
    image = window.structure.canvas.grab().toImage()
    assert colour_at(image, 3, 3) == theme.COLORS["dark"]["FIGURE"]
    shot(window, "dark")
    window.viewport.setCurrentWidget(view)
    shot(view, "dark_bands")
    window.set_theme("light")
    assert message.palette().color(QPalette.ColorRole.WindowText).name() == \
        theme.COLORS["light"]["ERROR"]
    window.message("a message")
    assert message.palette().color(QPalette.ColorRole.WindowText).name() == \
        theme.COLORS["light"]["TEXT"]
    assert app.palette().color(QPalette.ColorRole.Window).name() == "#efefef"
    assert to_hex(window.structure.figure.get_facecolor()) == "#ffffff"
    assert to_hex(view.figure.get_facecolor()) == "#ffffff"
    assert window.theme_choice == "light"
    assert theme.resolve("system") in ("light", "dark")
    with pytest.raises(ValueError):
        theme.resolve("purple")


def formula_ink(window, entry="addTerm_zeeman"):
    """The colour of most opaque pixels of the formula in a palette entry's
    tooltip."""
    import base64
    import re
    from collections import Counter
    from PySide6.QtGui import QImage
    tooltip = next(a for a in window.palette_menu("term").actions()
                   if a.objectName() == entry).toolTip()
    image = QImage.fromData(base64.b64decode(re.search(r'base64,([^"]+)"', tooltip).group(1)),
                            "PNG")
    pixels = (image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height()))
    return Counter(p.name() for p in pixels if p.alpha() > 250).most_common(1)[0][0]


def test_formulas_in_the_palettes_follow_the_theme(window):
    """The formula images of the palettes' tooltips were drawn once, in the
    theme of the moment: near-black on the dark theme's tooltips."""
    assert formula_ink(window) == theme.COLORS["light"]["TEXT"]
    window.set_theme("dark")
    try:
        assert formula_ink(window) == theme.COLORS["dark"]["TEXT"]
    finally:
        window.set_theme("light")
    assert formula_ink(window) == theme.COLORS["light"]["TEXT"]


def test_the_settings_of_the_interactive_window(qapp, qtbot, tmp_path, no_jobs):
    """The program's window (use_settings) keeps the theme, always trust
    and the recent files; a driven window leaves the file alone."""
    from guiqula.session import Session
    settings.put("theme", "dark")
    settings.put("recent", [])
    window = build_main_window(use_settings=True)
    try:
        assert theme.name == "dark" and window.theme_actions["dark"].isChecked()
        window.attach(Session("honeycomb_zeeman_rashba", jobs=no_jobs))
        assert formula_ink(window) == theme.COLORS["dark"]["TEXT"]    # built light, then dark
        window.set_theme("light")
        assert settings.get("theme") == "light"
        window.set_plot_text("large")
        assert settings.get("plot_text") == "large" and theme.text_size == "large"
        window.set_plot_text("normal")
        window.set_ui_text("large")
        assert settings.get("ui_text") == "large" and theme.ui_text == "large"
        window.set_ui_text("normal")
        assert settings.get("ui_text") == "normal"
        window.session.act("save", path=str(tmp_path / "a.guiqula"))
        window.session.act("load", path="haldane_chern")               # a preset: not listed
        window._fill_recent()
        assert [a.toolTip() for a in window.recent_menu.actions()] == \
            [str((tmp_path / "a.guiqula").resolve())]
        window.set_always_trust(True)
        assert settings.get("always_trust") and window.session.always_trust
        window.set_always_trust(False)
        window.show()
        window.set_log(True)
    finally:
        window.close()                               # shown: its arrangement is kept
        window.session.close()
    layout = settings.get("layout")
    assert set(layout) == {"state", "geometry"}
    driven = build_main_window()
    try:
        driven.set_theme("dark")
        assert settings.get("theme") == "light"
        driven.set_theme("light")
        driven.set_plot_text("large")
        assert settings.get("plot_text") == "normal"
        driven.set_plot_text("normal")
        driven.set_ui_text("large")
        assert settings.get("ui_text") == "normal"
        driven.set_ui_text("normal")
        assert driven.docks["logDock"].isHidden()     # the stored arrangement is not read
        driven.show()
    finally:
        driven.close()
    assert settings.get("layout") == layout          # nor written
    again = build_main_window(use_settings=True)
    try:
        assert not again.docks["logDock"].isHidden() and again.log_toggle.isChecked()
    finally:
        again.close()
    settings.put("layout", {})


def test_every_toolbar_control_and_palette_entry_has_a_tooltip(window):
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QLineEdit, QTabBar, QToolBar
    from guiqula.registry import base as registry
    missing = []
    for bar in window.findChildren(QToolBar):
        widgets = [w for kind in (QAbstractButton, QComboBox, QLineEdit)
                   for w in bar.findChildren(kind)]
        for widget in widgets:
            if widget.objectName().startswith("qt_") or widget.parent() is not bar \
                    and not isinstance(widget.parent(), QToolBar):
                continue
            if not widget.toolTip():
                missing.append(widget.objectName() or widget.text())
    assert not missing
    # the canvas bars are groups of toolbars, walked above (P3); Fit names its keys
    walked = {bar.objectName() for bar in window.findChildren(QToolBar)}
    assert {"structureBar_navigation", "structureBar_tools", "structureBar_selection",
            "kspaceBar_pathTools"} <= walked
    assert shortcuts.text("fit") in window.structure.bar.fit_button.toolTip()
    tabs = window.findChild(QTabBar, "workspaceTabs")
    assert all("Ctrl+" in tabs.tabToolTip(i) for i in range(tabs.count()))
    menu = window.palette_menu("term")                  # the Hamiltonian's Add menu
    assert menu.toolTipsVisible() and menu.search.toolTip()
    zeeman = next(a for a in menu.actions() if a.objectName() == "addTerm_zeeman")
    assert zeeman.toolTip().startswith("<b>Zeeman") and "data:image/png;base64" in \
        zeeman.toolTip() and "spinful" in zeeman.toolTip()
    spec = registry.get("term", "zeeman")
    assert spec.doc in zeeman.toolTip()


def test_locks_in_the_forms_and_the_outliner(window, qtbot):
    """A teaching preset: its locked parameters are disabled and say so; a
    parameter's label locks it; the outliner's context menu locks an entry;
    Edit > Unlock everything lifts them (design item 12)."""
    session = window.session
    session.act("load", path="ssh_chain")
    settle(qtbot, window)
    assert "s1/geometry" in session.document.locks
    window.select("op1")                       # the supercell of the finite chain
    form = window.properties.form
    assert not form.editors["n"].isEnabled() and form.labels["n"].text().endswith("(locked)")
    assert "s2/geometry" in form.labels["n"].toolTip()
    assert not form.enabled.isEnabled()
    assert "locked" in window.outliner.item("s2/geometry").text(1)
    window.select("t1")                        # the modulation is free
    form = window.properties.form
    assert form.editors["s"].isEnabled() and form.enabled.isEnabled()
    menu = form.label_menu("s")
    assert [a.text() for a in menu.actions()] == ["Lock this parameter", "Attach a slider",
                                                   "Sweep this parameter",
                                                   "Preview on the canvas"]
    assert menu.actions()[0].objectName() == "lockParam_s"
    menu.actions()[0].trigger()
    menu.close()
    assert "t1.s" in session.document.locks
    form = window.properties.form
    assert not form.editors["s"].isEnabled() and form.enabled.isEnabled()
    assert "s locked" in window.outliner.item("t1").text(1)
    ok, message = window._do("set_param", entry="t1", name="s", value=1.0)
    assert not ok and "t1.s is locked" in message
    window.outliner.command.emit("lock", {"target": "c1"})
    assert "c1" in session.document.locks
    assert window.unlock_action.isEnabled()
    window.unlock_action.trigger()
    assert session.document.locks == [] and not window.unlock_action.isEnabled()
    assert window.properties.form.editors["s"].isEnabled()
    window.undo()
    assert "t1.s" in session.document.locks


def test_export_figure_data_and_script(window, qtbot, tmp_path, run_python):
    """One folder per result: the figure on white even in the dark theme,
    the arrays, a table of the curves, the script reproducing them, the
    document (design item 12)."""
    import json
    import numpy as np
    from PIL import Image
    session = window.session
    session.act("load", path="honeycomb_zeeman_rashba")
    settle(qtbot, window)
    job = session.run_calculation("c1", wait=True, timeout=600)
    assert job.status == "done", job.error
    window.set_theme("dark")
    try:
        files = session.act("export_bundle", calculation="c1", path=str(tmp_path / "c1_bands"))
    finally:
        window.set_theme("light")
    names = sorted(p.split("/")[-1] for p in files)
    assert names == ["README.txt", "data.csv", "data.json", "data.npz", "document.json",
                     "figure.pdf", "figure.png", "script.py"]
    folder = tmp_path / "c1_bands"
    image = np.asarray(Image.open(folder / "figure.png").convert("RGB"))
    assert tuple(image[2, 2]) == (255, 255, 255)                 # white, not the dark theme
    table = np.loadtxt(folder / "data.csv", delimiter=",", skiprows=1)
    energies = job.value.arrays["energies"]
    assert table.shape == (len(energies), 1 + energies.shape[1])
    assert np.allclose(table[:, 1:], energies)
    assert json.loads((folder / "document.json").read_text())["systems"][0]["id"] == "s1"
    run = run_python("import guiqula\n" + (folder / "script.py").read_text()   # finds pyqula
                     + f"\nnp.save({str(tmp_path / 'e.npy')!r}, np.asarray(energies))")
    assert run.returncode == 0, run.stderr
    assert np.allclose(np.load(tmp_path / "e.npy"), energies, atol=1e-8)
    assert "c1: bands" in (folder / "README.txt").read_text()


def test_values_on_a_chain_are_a_curve_against_x(qapp):
    """The LDOS of a long chain would be dots too small to colour: on a
    chain a result on the atoms is drawn as a curve against x."""
    import numpy as np
    from matplotlib.figure import Figure
    from guiqula.core.results import Result
    from guiqula.ui import plots
    x = np.arange(10, dtype=float) - 4.5
    structure = {"positions": np.column_stack([x, np.zeros(10), np.zeros(10)]),
                 "lattice": np.eye(3), "dimensionality": 0, "sublattice": None,
                 "bonds": np.array([[i, i + 1] for i in range(9)]),
                 "image_bonds": np.zeros((0, 5), dtype=int)}
    values = np.exp(-np.abs(x))
    result = Result(calculation="c9", kind="ldos", key="k", params={},
                    arrays={"ldos": values},
                    plot={"kind": "structure_scalar", "values": "ldos", "clabel": "LDOS"},
                    reports=[], mode="spinless", structure=structure)
    ax, points = plots.draw(Figure(), result)
    assert np.allclose(ax.lines[0].get_ydata(), values[np.argsort(x)])
    assert ax.get_ylabel() == "LDOS" and ax.get_xlabel() == "x"
    view = plots.PlotView("c9")
    view.show_result(result)
    assert view.readout_text(9) == "site 9 at x = 4.5 · LDOS 0.011109"
    structure["positions"][3, 1] = 0.5                    # not a chain: on the atoms
    ax, points = plots.draw(Figure(), result)
    assert not ax.lines and ax.get_ylabel() == "y"


def test_a_large_geometry_on_the_canvas(qapp):
    """Phase 5, part 3: 20,000 sites are drawn, selected and redrawn
    quickly; an unchanged drawing is not redone (only its caption)."""
    import time
    import numpy as np
    from guiqula.ui.structure import StructureView
    x, y = np.meshgrid(np.arange(160.0), np.arange(125.0) * 0.9)
    positions = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)])     # 20,000
    right = np.arange(len(positions)).reshape(125, 160)
    bonds = np.column_stack([right[:, :-1].ravel(), right[:, 1:].ravel()])
    build = {"positions": positions, "lattice": np.diag([160.0, 112.5, 1.0]),
             "dimensionality": 0, "sublattice": None, "bonds": bonds,
             "image_bonds": np.zeros((0, 5), dtype=int)}
    view = StructureView()
    view.resize(900, 700)
    start = time.perf_counter()
    view.show_structure("s1", build, "first")
    view.canvas.draw()
    first = time.perf_counter() - start
    ax = view.ax
    start = time.perf_counter()
    view.show_structure("s1", build, "updating…")
    assert view.ax is ax and view.caption.text() == "updating…"       # not redrawn
    assert time.perf_counter() - start < 0.2
    start = time.perf_counter()
    assert view.select(range(len(positions))) == len(positions)
    view.select(range(0, len(positions), 3), "toggle")
    view.canvas.draw()
    assert time.perf_counter() - start < 3.0
    assert first < 5.0
    view.show_structure("s1", build, "a region", highlight=np.arange(len(positions)) < 10)
    assert view.ax is not ax                                          # something changed


# ---- the look (2026-09-29): plot text, check boxes, centred axes
def margins(view):
    """(left, right) in pixels between a view's axes box and the edges of
    its figure."""
    position, width = view.ax.get_position(), view.figure.bbox.width
    return position.x0 * width, (1.0 - position.x1) * width


def test_plot_text_is_a_setting_every_drawing_follows(window, qtbot):
    """View > Plot text: the labels, the ticks and the titles of every
    drawing take one of three sizes, and the axes sit in the middle of
    their panel whatever the y label, the ticks and a colour bar take on
    each side."""
    session = window.session
    session.act("load", path="honeycomb_zeeman_rashba")
    settle(qtbot, window)
    job = session.run_calculation("c1", wait=True, timeout=600)
    assert job.status == "done", job.error
    window.show_result("c1")
    qtbot.waitUntil(lambda: window.plots["c1"].result is not None, timeout=10_000)
    view = window.plots["c1"]
    assert settings.CHOICES["plot_text"] == theme.TEXT_SIZES
    assert theme.text_size == "normal" and window.text_actions["normal"].isChecked()
    base = theme.FONT_POINTS["normal"]
    assert view.ax.xaxis.label.get_size() == pytest.approx(1.2 * base)     # "large"
    assert view.ax.get_xticklabels()[0].get_size() == base
    assert view.ax.title.get_size() == base
    left, right = margins(view)                      # a colour bar right, the y label left
    assert abs(left - right) < 3, (left, right)
    qtbot.waitUntil(lambda: abs(margins(window.structure)[0] - margins(window.structure)[1]) < 3,
                    timeout=10_000)
    assert abs(margins(window.kspace_view)[0] - margins(window.kspace_view)[1]) < 3
    assert session.act("plot_text", name="large") == "large"
    assert window.text_actions["large"].isChecked()
    assert view.ax.xaxis.label.get_size() == pytest.approx(1.2 * theme.FONT_POINTS["large"])
    assert window.structure.ax.get_xticklabels()[0].get_size() == theme.FONT_POINTS["large"]
    left, right = margins(view)
    assert abs(left - right) < 3, (left, right)
    with pytest.raises(ValueError):
        theme.set_text_size("huge")
    session.act("plot_text", name="normal")
    assert view.ax.xaxis.label.get_size() == pytest.approx(1.2 * base)
    assert theme.font_points("large") == pytest.approx(1.2 * base)
    assert QApplication.instance().font().pointSizeF() >= theme.UI_POINTS["normal"]


def box_contrast(widget, x0, x1, y):
    """The strongest contrast between the pixels of a row of a widget (x0
    to x1, at height y) and its background at x0: a check box's border
    drawn there stands out, a missing one does not."""
    image = widget.grab().toImage()
    back = QColor(image.pixel(x0, y))
    contrasts = [sum(abs(a - b) for a, b in zip(QColor(image.pixel(x, y)).getRgb()[:3],
                                                back.getRgb()[:3])) for x in range(x0, x1)]
    return max(contrasts)


def test_check_boxes_show_a_box_in_both_themes(window, qtbot):
    """Fusion's box is drawn with a border derived from the window colour,
    invisible in the dark theme: theme.CheckStyle draws a bordered box, in
    the forms and in the outliner alike."""
    from PySide6.QtWidgets import QCheckBox
    window.select("s1")
    for name in ("light", "dark"):
        window.set_theme(name)                   # rebuilds the form and the outliner
        qtbot.wait(50)
        box = window.properties.form.nambu       # an unchecked QCheckBox of the system form
        assert isinstance(box, QCheckBox) and not box.isChecked()
        assert box_contrast(box, 0, 18, box.height() // 2) > 300, name
        item = window.outliner.item("t1")        # a checked item of the outliner
        cell = window.outliner.visualItemRect(item)
        view = window.outliner.viewport()
        assert box_contrast(view, cell.x(), cell.x() + 22, cell.center().y()) > 250, name
    window.set_theme("light")


def test_the_forms_and_the_outliner_read_as_they_should(window):
    outliner = window.outliner
    assert [outliner.headerItem().text(i) for i in (0, 1)] == ["Entry", "Status"]
    # the Status column as wide as its longest text, the Entry column the rest (P7)
    assert outliner.columnWidth(1) == outliner.status_width()
    assert outliner.columnWidth(0) + outliner.columnWidth(1) == outliner.viewport().width()
    window.select("t1")
    form = window.properties.form
    assert form.enabled.text() == "enabled"            # in the title's row, not a labelled row
    assert form.rows.labelForField(form.enabled) is None
    assert form.heading.indexOf(form.enabled) == form.heading.indexOf(form.title) + 1
