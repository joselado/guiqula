"""The panels (PLAN.md phase 8, package P5): Properties alone at the top of
the right column and Help, Sliders and Jobs tabbed below it, so that F1
never hides the form it explains; the bottom area (Log, Console) hidden
until the status bar's Log toggle shows it, the last message in the status
bar; no dock floats; View > Panels and View > Reset layout; the arrangement
and the window size kept in the settings by the program's window only; View
> Interface text, normal or large."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QDockWidget, QMenu, QToolButton

from guiqula.io import settings
from guiqula.ui import mainwindow, theme
from guiqula.ui.app import build_main_window

RIGHT = Qt.DockWidgetArea.RightDockWidgetArea
FEATURES = QDockWidget.DockWidgetFeature.DockWidgetClosable \
    | QDockWidget.DockWidgetFeature.DockWidgetMovable


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("GUIQULA_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"


def settle(qtbot, rounds=5):
    for _ in range(rounds):
        QApplication.processEvents()
        qtbot.wait(30)


def shown(window, size=(1200, 800), **options):
    window.resize(*size)
    window.show()
    return window


def in_front(window, name):
    dock = window.docks[name]
    return not dock.isHidden() and not dock.visibleRegion().isEmpty()


def assert_default(window):
    docks = window.docks
    assert [n for n, d in docks.items() if d.isHidden()] == ["logDock", "consoleDock"]
    assert all(window.dockWidgetArea(docks[n]) == RIGHT
               for n in ("propertiesDock", "helpDock", "slidersDock", "jobsDock"))
    assert window.dockWidgetArea(docks["outlinerDock"]) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.tabifiedDockWidgets(docks["propertiesDock"]) == []      # alone at the top
    assert {d.objectName() for d in window.tabifiedDockWidgets(docks["helpDock"])} == \
        {"slidersDock", "jobsDock"}
    assert in_front(window, "propertiesDock") and in_front(window, "helpDock")
    assert not window.log_toggle.isChecked()


def test_the_default_arrangement(qtbot, shot):
    window = shown(build_main_window())
    qtbot.addWidget(window)
    settle(qtbot)
    assert_default(window)
    docks = window.docks
    assert all(d.features() == FEATURES for d in docks.values())          # nothing floats
    share = docks["propertiesDock"].height() / (docks["propertiesDock"].height()
                                                 + docks["helpDock"].height())
    assert 0.55 < share < 0.68, share
    tabs = [bar for bar in window.findChildren(mainwindow.QTabBar)
            if bar.count() == 3 and bar.tabText(0) == "Help"]
    assert len(tabs) == 1 and [tabs[0].tabText(i) for i in range(3)] == ["Help", "Sliders",
                                                                         "Jobs"]
    menu = window.findChild(QMenu, "panelsMenu")
    assert [a.text() for a in menu.actions()] == ["Outliner", "Properties", "Help", "Sliders",
                                                  "Jobs", "Log", "Console"]
    assert menu.toolTipsVisible()                                         # each says what it is
    assert all(a.toolTip().startswith(f"show or hide {a.text()}: ") for a in menu.actions())
    assert "(F1)" in window.docks["helpDock"].toggleViewAction().toolTip()
    assert window.findChild(type(window.undo_action), "resetLayoutAction") is not None
    assert "F1" in window.help_panel.browser.placeholderText()            # what to do next
    shot(window, "default")


def test_the_log_toggle_shows_the_bottom_area(qtbot):
    window = shown(build_main_window())
    qtbot.addWidget(window)
    settle(qtbot)
    log, console = window.docks["logDock"], window.docks["consoleDock"]
    toggle = window.findChild(QToolButton, "logToggle")
    assert toggle.toolTip() and toggle.text() == "Log"
    status = window.statusBar()
    assert toggle.parent() is not None and toggle.geometry().right() > \
        window.status_message.geometry().right() > window.status_label.geometry().right()
    toggle.click()
    settle(qtbot)
    assert toggle.isChecked() and not log.isHidden() and not console.isHidden()
    assert in_front(window, "logDock") and window.dockWidgetArea(log) == \
        Qt.DockWidgetArea.BottomDockWidgetArea
    assert in_front(window, "propertiesDock") and in_front(window, "helpDock")
    log.toggleViewAction().trigger()             # closed from View > Panels: the Console stays
    assert toggle.isChecked()
    console.close()                              # its close button
    settle(qtbot)
    assert not toggle.isChecked()
    assert window.set_log(True) and not log.isHidden() and not console.isHidden()
    assert not window.set_log(False) and log.isHidden() and console.isHidden()
    assert window.show_panel("Console") == "consoleDock" and toggle.isChecked()
    window.show_panel("consoleDock", shown=False)
    assert not toggle.isChecked()
    with pytest.raises(ValueError, match="unknown panel"):
        window.show_panel("nope")
    # the last message, after the summary; an error in the error colour, the log keeps all
    window.message("first line\nsecond line", error=True)
    assert window.status_message.message == "first line\nsecond line"
    assert window.status_message.text() == "first line" and window.status_message.error
    assert "ERROR: first line" in window.log.toPlainText()
    colour = window.status_message.palette().color(QPalette.ColorRole.WindowText).name()
    assert colour == theme.ERROR
    window.message("x" * 3000)                    # elided, and the window does not widen
    settle(qtbot)
    assert not window.status_message.error and window.width() == 1200
    assert len(window.status_message.text()) < 3000 and window.status_message.toolTip() == \
        "x" * 3000
    assert status.isVisible()


def test_reset_layout_restores_the_default(qtbot):
    window = shown(build_main_window())
    qtbot.addWidget(window)
    settle(qtbot)
    docks = window.docks
    window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, docks["propertiesDock"])
    window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, docks["jobsDock"])
    docks["helpDock"].close()
    window.set_log(True)
    settle(qtbot)
    assert window.dockWidgetArea(docks["propertiesDock"]) != RIGHT
    shown_panels = window.reset_layout()
    settle(qtbot)
    assert shown_panels == ["outlinerDock", "propertiesDock", "helpDock", "slidersDock",
                            "jobsDock"]
    assert_default(window)
    assert window.size().width() == 1200                     # the window keeps its size


def test_the_layout_setting_round_trips(qtbot, config):
    window = shown(build_main_window(use_settings=True), size=(1000, 700))
    settle(qtbot)
    assert settings.get("layout") == {}                      # nothing stored yet
    assert_default(window)
    window.set_log(True)
    window.docks["helpDock"].close()
    window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, window.docks["jobsDock"])
    settle(qtbot)
    window.close()
    stored = settings.get("layout")
    assert set(stored) == {"state", "geometry"}
    again = build_main_window(use_settings=True)              # restored before it is shown
    try:
        # the height as it was, and not the default size; the width too on a desktop, but
        # the offscreen screen is 800 pixels wide and restoreGeometry fits the window in it
        assert again.height() == 700 and again.width() < 1280
        again.show()
        settle(qtbot)
        assert again.docks["helpDock"].isHidden() and not again.docks["logDock"].isHidden()
        assert again.log_toggle.isChecked()
        assert again.dockWidgetArea(again.docks["jobsDock"]) == \
            Qt.DockWidgetArea.LeftDockWidgetArea
        assert [bar.objectName() for bar in again.findChildren(mainwindow.QToolBar)
                if bar.parent() is again and bar.isVisible()] == \
            ["workspaceToolbar", "runToolbar"]
        again.reset_layout()
        settle(qtbot)
        assert_default(again)
    finally:
        again.close()
    assert set(settings.get("layout")) == {"state", "geometry"}
    # a driven window (tests, tools/drive.py) neither reads nor writes it
    driven = shown(build_main_window(), size=(900, 600))
    settle(qtbot)
    assert_default(driven)
    before = settings.get("layout")
    driven.set_log(True)
    driven.close()
    assert settings.get("layout") == before
    # an arrangement of another version (P2 rewrites the toolbars): the default
    other = shown(build_main_window(), size=(900, 600))
    other.set_log(True)
    settle(qtbot)
    state = bytes(other.saveState(mainwindow.LAYOUT_VERSION + 1).toBase64()).decode("ascii")
    other.close()
    settings.put("layout", dict(settings.get("layout"), state=state))
    fallback = build_main_window(use_settings=True)
    try:
        fallback.show()
        settle(qtbot)
        assert_default(fallback)
    finally:
        fallback.setVisible(False)            # closed hidden: the setting stays as it is
        fallback.close()
    assert settings.get("layout")["state"] == state
    with pytest.raises(settings.SettingsError):
        settings.put("layout", {"state": 1})
    settings.save(dict(settings._stored(), layout="broken"))
    assert settings.load()["layout"] == {}


def test_the_interface_text_setting(qtbot, config):
    app = QApplication.instance()
    normal = app.font().pointSizeF()
    assert theme.ui_text == "normal" and normal >= theme.UI_POINTS["normal"]
    window = build_main_window(use_settings=True)
    try:
        assert window.ui_text_actions["normal"].isChecked()
        assert window.set_ui_text("large") == "large"
        assert app.font().pointSizeF() == normal + theme.UI_POINTS["large"] \
            - theme.UI_POINTS["normal"]
        assert window.ui_text_actions["large"].isChecked() and settings.get("ui_text") == \
            "large"
        assert f"font-size: {app.font().pointSizeF() + 2:g}pt" in app.styleSheet()
        menu = window.findChild(QMenu, "uiTextMenu")
        assert [a.objectName() for a in menu.actions()] == ["ui_text_normal", "ui_text_large"]
        assert all(a.toolTip() for a in menu.actions())
        theme.set_ui_text("normal")
        again = build_main_window(use_settings=True)           # the next start reads it
        try:
            assert theme.ui_text == "large" and again.ui_text_actions["large"].isChecked()
            assert app.font().pointSizeF() > normal
        finally:
            again.close()
        with pytest.raises(ValueError):
            window.set_ui_text("huge")
        window.set_ui_text("normal")
        assert app.font().pointSizeF() == normal and settings.get("ui_text") == "normal"
    finally:
        theme.set_ui_text("normal")
        theme.apply_text(app)
        window.close()
    driven = build_main_window()
    try:
        driven.set_ui_text("large")
        assert settings.get("ui_text") == "normal"
    finally:
        driven.set_ui_text("normal")
        driven.close()
    assert app.font().pointSizeF() == normal


def title_ink(dock):
    """The height in pixels of the text of a dock's title (its rows that
    carry ink), however tall the title bar is."""
    top = dock.widget().geometry().top()
    image = dock.grab(QRect(0, 0, 100, top)).toImage()
    background = dock.palette().color(QPalette.ColorRole.Window).lightness()
    rows = [y for y in range(image.height())
            if any(abs(image.pixelColor(x, y).lightness() - background) > 60
                   for x in range(2, image.width()))]
    return rows[-1] - rows[0] + 1 if rows else 0


def test_the_panel_titles_follow_the_interface_text(qtbot):
    """Qt draws a dock's title in the font it had when it was made; the
    panels draw it in their font, so large interface text reaches them."""
    window = shown(build_main_window())
    qtbot.addWidget(window)
    settle(qtbot)
    dock = window.docks["outlinerDock"]
    assert isinstance(dock, mainwindow.Dock)
    normal = title_ink(dock)
    assert normal > 0
    try:
        window.set_ui_text("large")
        settle(qtbot)
        assert title_ink(dock) > normal
        assert title_ink(window.docks["helpDock"]) > normal
    finally:
        window.set_ui_text("normal")
    settle(qtbot)
    assert title_ink(dock) == normal


def test_jobs_come_forward_unless_help_shows_an_item_or_sliders_are_used(qtbot, no_jobs):
    from guiqula.session import Session
    window = shown(build_main_window())
    qtbot.addWidget(window)
    window.attach(Session("honeycomb_zeeman_rashba", jobs=no_jobs))
    settle(qtbot)
    count = iter(range(1, 100))

    def new_job():
        job = SimpleNamespace(id=f"j{next(count)}", kind="run", label="c1", status="queued",
                              error=None, traceback=None, progress=0.0, done=False)
        window.jobs.update_job(job)
        settle(qtbot, 2)

    window.select("t1")
    window.show_help()                                        # F1: t1's help, under its form
    settle(qtbot)
    assert in_front(window, "helpDock") and in_front(window, "propertiesDock")
    new_job()                                                 # Run at once, at an edit of t1
    assert in_front(window, "helpDock") and not in_front(window, "jobsDock")
    window.docks["slidersDock"].raise_()                      # a slider moved: it stays
    new_job()
    assert in_front(window, "slidersDock") and not in_front(window, "jobsDock")
    window.help(guide="guiqula")                              # a guide, not an item
    settle(qtbot)
    assert in_front(window, "helpDock")
    new_job()
    assert in_front(window, "jobsDock")
    window.session.close()


def test_f1_keeps_the_form_in_sight(qtbot, no_jobs, shot):
    """The acceptance of the package: at 1200x800, t1 selected and F1, the
    form and the help at once, the three components of the Zeeman field
    in sight without a scroll."""
    from guiqula.session import Session
    window = shown(build_main_window())
    qtbot.addWidget(window)
    window.attach(Session("honeycomb_zeeman_rashba", jobs=no_jobs))
    window.select("t1")
    window.show_help()
    settle(qtbot, 10)
    assert window.help_panel.title.text() == "Zeeman / exchange field"
    assert in_front(window, "helpDock") and in_front(window, "propertiesDock")
    assert not window.properties.verticalScrollBar().isVisible()
    edits = [component.edit for component in window.properties.form.editors["m"].components]
    assert len(edits) == 3
    for edit in edits:
        assert edit.visibleRegion().boundingRect().height() == edit.height()
    shot(window, "f1_1200x800")
    window.session.close()


def test_the_workers_line_does_not_widen_the_right_column(qtbot):
    """The Jobs panel's line of the workers wraps: on one line, three workers
    (interactive, batch, console) took about 770 px, which the column of
    Properties, Help and Jobs took from the canvas, squeezing it to about 180
    px, where matplotlib gave up its constrained layout."""
    from guiqula.ui.jobpanel import JobPanel
    panel = JobPanel()
    qtbot.addWidget(panel)
    panel.update_workers([{"role": role, "pid": 3207362, "alive": True, "job": None,
                           "ready": True, "starts": 2}
                          for role in ("interactive", "batch", "console")])
    assert len(panel.workers.text()) > 120
    assert panel.minimumSizeHint().width() < 300
