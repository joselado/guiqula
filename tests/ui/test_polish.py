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
    assert window.focus_search() == "opSearch"
    window.set_workspace("hamiltonian")
    assert window.focus_search() == "termSearch"
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
    window.viewport.setCurrentIndex(0)
    image = window.structure.canvas.grab().toImage()
    assert colour_at(image, 3, 3) == theme.COLORS["dark"]["FIGURE"]
    shot(window, "dark")
    window.viewport.setCurrentWidget(view)
    shot(view, "dark_bands")
    window.set_theme("light")
    assert app.palette().color(QPalette.ColorRole.Window).name() == "#efefef"
    assert to_hex(window.structure.figure.get_facecolor()) == "#ffffff"
    assert to_hex(view.figure.get_facecolor()) == "#ffffff"
    assert window.theme_choice == "light"
    assert theme.resolve("system") in ("light", "dark")
    with pytest.raises(ValueError):
        theme.resolve("purple")


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
        window.set_theme("light")
        assert settings.get("theme") == "light"
        window.session.act("save", path=str(tmp_path / "a.guiqula"))
        window.session.act("load", path="haldane_chern")               # a preset: not listed
        window._fill_recent()
        assert [a.toolTip() for a in window.recent_menu.actions()] == \
            [str((tmp_path / "a.guiqula").resolve())]
        window.set_always_trust(True)
        assert settings.get("always_trust") and window.session.always_trust
        window.set_always_trust(False)
    finally:
        window.close()
        window.session.close()
    driven = build_main_window()
    try:
        driven.set_theme("dark")
        assert settings.get("theme") == "light"
        driven.set_theme("light")
    finally:
        driven.close()


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
    tabs = window.findChild(QTabBar, "workspaceTabs")
    assert all("Ctrl+" in tabs.tabToolTip(i) for i in range(tabs.count()))
    menu = window.term_button.menu()
    assert menu.toolTipsVisible()
    zeeman = next(a for a in menu.actions() if a.objectName() == "addTerm_zeeman")
    assert zeeman.toolTip().startswith("<b>Zeeman") and "data:image/png;base64" in \
        zeeman.toolTip() and "spinful" in zeeman.toolTip()
    spec = registry.get("term", "zeeman")
    assert spec.doc in zeeman.toolTip()
