"""The bars of the drawings and the status row of a plot (PLAN.md phase 8,
package P3): every bar fits at 1200 px on every preset, wrapping onto lines
instead of hiding its tools behind a chevron; the structure bar holds the
selection tools; a stale result says so above its plot and Run again
computes it, a running one shows its progress and Cancel stops it, a failed
one says why; the k-space tab is there only for a system with a periodic
direction."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QFrame, QToolBar, QToolButton, QWidget

from guiqula.io import project
from guiqula.ui import marks, pyvista_view, shortcuts, theme
from guiqula.ui.app import build_main_window
from guiqula.ui.canvasbar import CanvasBar
from guiqula.ui.mainwindow import KSPACE_TAB, STRUCTURE_TAB

FAIL = "raise ValueError('no band here')"
SLOW = "import time\ntime.sleep(60)\narrays = {'x': np.arange(3.0), 'y': np.arange(3.0)}"
QUICK = "arrays = {'x': np.arange(3.0), 'y': np.arange(3.0)}"


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)
    for _ in range(5):
        QApplication.processEvents()
        qtbot.wait(20)


def load(qtbot, window, name):
    window.session.act("load", path=name)
    settle(qtbot, window)


def assert_fits(bar):
    """No group of a bar shows its chevron, and each lies inside the bar."""
    QApplication.processEvents()
    assert bar.isVisible(), bar.objectName()
    assert bar.overflows() == [], (bar.objectName(), bar.overflows())
    for item in bar.flow.items:            # the groups with something shown
        if bar.flow.shown(item):
            assert bar.rect().contains(item.widget().geometry()), (
                bar.objectName(), item.widget().objectName())


def test_the_bars_wrap_and_never_overflow_at_1200_px(window, qtbot):
    """On every preset at 1200x800 the structure bar, the k-space bar (for a
    periodic system) and a result's bar fit, on more than one line where
    they must; matplotlib's toolbar is there, hidden, as the canvas's."""
    structure = window.structure
    assert structure.canvas.toolbar is structure.toolbar and structure.toolbar.isHidden()
    assert structure.toolbar.objectName() == "structureToolbar"
    assert [a.text() for a in structure.toolbar.actions() if a.text()] == \
        ["Home", "Pan", "Zoom", "Save"]               # no Back, Forward, Subplots, Customize
    assert isinstance(structure.bar, CanvasBar) and structure.bar.objectName() == "structureBar"
    assert [n for n in structure.bar.controls() if "Button" in n or n.startswith(
        ("structure", "tool_"))] == ["structureFit", "structurePan", "structureZoom",
                                     "tool_pick", "tool_box", "tool_lasso",
                                     "selectSitesButton", "regionFromSelectionButton",
                                     "calculateOnSelectionButton", "removeSelectedButton",
                                     "structureSaveImage"]
    for name in project.presets():
        load(qtbot, window, name)
        window.viewport.setCurrentIndex(STRUCTURE_TAB)
        assert_fits(structure.bar)
        assert len(structure.bar.lines()) > 1            # the viewport is about 480 px wide
        if window.viewport.isTabVisible(KSPACE_TAB):
            window.viewport.setCurrentIndex(KSPACE_TAB)
            assert_fits(window.kspace_view.bar)
        calc = window.session.document.calculations[0].id
        window.show_result(calc)
        assert_fits(window.plots[calc].bar)
    load(qtbot, window, "honeycomb_zeeman_rashba")
    window.viewport.setCurrentIndex(STRUCTURE_TAB)
    window.session.act("preview", entry="t1", param="m")       # the brush joins the bar
    assert structure.bar.groups["paint"].isVisible()
    assert_fits(structure.bar)
    window.set_canvas_view("structure")
    assert not structure.bar.groups["paint"].isVisible()
    if pyvista_view.available():                         # the scene's controls, in the bar
        window.session.act("renderer_3d", name="pyvista")
        window.session.act("projection", name="3d")
        if structure.in_scene:                           # pyvista could draw here
            controls = structure.bar.controls()
            assert controls[:2] == ["structureSceneReset", "structureSceneView"]
            assert controls[-1] == "structureSceneSave" and "structureFit" not in controls
            assert_fits(structure.bar)
        window.session.act("projection", name="auto")
        window.session.act("renderer_3d", name="matplotlib")
        assert structure.bar.controls()[0] == "structureFit"
    job = window.session.run_calculation("c1", wait=True, timeout=600)
    assert job.status == "done", job.error
    window.show_result("c1")
    view = window.plots["c1"]
    qtbot.waitUntil(lambda: view.result is job.value, timeout=10_000)
    assert view.bar.objectName() == "plotBar_c1" and view.toolbar.isHidden()
    assert view.canvas.toolbar is view.toolbar
    assert view.bar.controls() == ["fit_c1", "pan_c1", "zoom_c1", "pickTool_c1", "overlay_c1",
                                   "style_c1", "export_c1", "saveData_c1", "detach_c1",
                                   "saveImage_c1"]
    assert_fits(view.bar)


def test_pan_and_zoom_are_the_bars_and_fit_shows_it_all(window, qtbot):
    """Pan and Zoom turn matplotlib's modes on and off and show which is on;
    a pick tool turns them off; Fit brings the plot back as it was drawn."""
    load(qtbot, window, "honeycomb_zeeman_rashba")
    job = window.session.run_calculation("c2", wait=True, timeout=600)
    assert job.status == "done", job.error
    window.show_result("c2")
    view = window.plots["c2"]
    qtbot.waitUntil(lambda: view.result is job.value, timeout=10_000)
    bar = view.bar
    bar.pan_button.click()
    assert bar.mode() == "pan/zoom" and bar.pan_button.isChecked()
    bar.zoom_button.click()
    assert bar.mode() == "zoom rect" and bar.zoom_button.isChecked()
    assert not bar.pan_button.isChecked()
    view.pick_tools["pick"].click()                     # a pick tool takes the clicks back
    assert bar.mode() == "" and not bar.zoom_button.isChecked()
    bar.pan_button.click()                              # and pan unchecks the pick tool
    assert not view.pick_tools["pick"].isChecked()
    bar.pan_button.click()
    assert bar.mode() == ""
    limits = view.ax.get_xlim()
    view.toolbar.push_current()                         # as a pan does at its first press
    view.ax.set_xlim(limits[0] + 1.0, limits[1] - 1.0)
    bar.fit_button.click()
    assert np.allclose(view.ax.get_xlim(), limits)


def test_the_status_row_says_stale_and_run_again_recomputes(window, qtbot):
    session = window.session
    load(qtbot, window, "honeycomb_zeeman_rashba")
    window.show_result("c1")
    view = window.plots["c1"]
    row = view.findChild(QFrame, "plotStatus_c1")
    assert row is view.status and not row.isVisibleTo(view)      # no result: the caption says
    assert "no result yet" in view.caption.text()
    first = session.run_calculation("c1", wait=True, timeout=600).value
    qtbot.waitUntil(lambda: view.result is first, timeout=10_000)
    index = window.viewport.indexOf(view)
    assert not row.isVisibleTo(view) and window.viewport.tabText(index) == "c1 bands"
    ax = view.ax
    session.do("set_param", entry="t1", name="m", value=[0, 0, 0.3])
    assert row.isVisibleTo(view) and row.state == "stale"
    assert row.text.full == f"{marks.STALE} stale: the model changed since this was computed"
    assert window.viewport.tabText(index) == f"c1 bands {marks.STALE}"
    assert "STALE" not in view.ax.get_title() and view.ax is ax       # not drawn again
    run = view.findChild(QToolButton, "plotRun_c1")
    assert run.isVisibleTo(view) and run.text() == "Run again"
    assert not view.findChild(QToolButton, "plotCancel_c1").isVisibleTo(view)
    assert not view.findChild(QWidget, "plotProgress_c1").isVisibleTo(view)
    run.click()                                          # the window's run_guarded
    qtbot.waitUntil(lambda: session.result("c1") is not first and session.status("c1") == "done",
                    timeout=300_000)
    qtbot.waitUntil(lambda: view.result is session.result("c1"), timeout=10_000)
    assert not row.isVisibleTo(view) and window.viewport.tabText(index) == "c1 bands"
    session.undo()                       # m as it was: the earlier result back, current
    assert session.status("c1") == "done" and not row.isVisibleTo(view)


def test_the_status_row_shows_progress_and_cancel_stops_the_job(window, qtbot):
    session = window.session
    load(qtbot, window, "graphene_island")
    slow = session.do("add_calculation", system="s1", kind="python", params={"code": SLOW})
    window.show_result(slow)
    view = window.plots[slow]
    row, index = view.status, window.viewport.indexOf(view)
    job = session.run_calculation(slow)
    assert row.state in ("queued", "running") and row.isVisibleTo(view)   # at once
    qtbot.waitUntil(lambda: job.status == "running", timeout=120_000)
    qtbot.waitUntil(lambda: row.state == "running", timeout=5000)
    progress = view.findChild(QWidget, f"plotProgress_{slow}")
    cancel = view.findChild(QToolButton, f"plotCancel_{slow}")
    assert progress.isVisibleTo(view) and cancel.isVisibleTo(view)
    assert not view.findChild(QToolButton, f"plotRun_{slow}").isVisibleTo(view)
    assert row.text.full == marks.mark("running")
    job.progress = 0.4                                   # a report of the worker
    window._job_changed(job)
    assert progress.value() == 40
    assert window.viewport.tabText(index) == f"{slow} python 40%"
    cancel.click()                                       # the job's cancel
    qtbot.waitUntil(lambda: job.status == "cancelled", timeout=10_000)
    qtbot.waitUntil(lambda: not row.isVisibleTo(view), timeout=5000)
    assert window.viewport.tabText(index) == f"{slow} python"


def test_a_failed_run_says_why_and_over_an_earlier_result_reads_stale(window, qtbot):
    """A run that fails with no result kept reads failed, with the first line
    of the error, in the row, the tab, the tree and the form; one that fails
    over an earlier result reads stale there, as Session.status says, with
    Run again and the earlier result drawn, and the failure is in the Jobs
    panel (decision 121, answered with its alternative)."""
    session = window.session
    load(qtbot, window, "graphene_island")
    calc = session.do("add_calculation", system="s1", kind="python", params={"code": FAIL})
    window.show_result(calc)
    view = window.plots[calc]
    row, index = view.status, window.viewport.indexOf(view)
    job = session.run_calculation(calc, wait=True, timeout=300)
    assert job.status == "failed" and session.status(calc) == "failed"     # nothing kept
    qtbot.waitUntil(lambda: row.state == "failed", timeout=5000)
    assert row.isVisibleTo(view) and row.text.full.startswith(f"{marks.FAILED} failed: ")
    # the line shows the final exception, the engine's chain staying in the tooltip
    assert row.text.shown == "failed: ValueError: no band here (line 1 of the code)"
    assert row.text.toolTip().startswith(f"{marks.FAILED} failed: CalculationError")
    assert "no band here" in row.text.toolTip()
    assert view.findChild(QToolButton, f"plotRun_{calc}").isVisibleTo(view)
    assert window.viewport.tabText(index) == f"{calc} python {marks.FAILED}"
    assert window.viewport.tabBar().tabTextColor(index).name() == theme.ERROR
    assert "no band here" in window.viewport.tabToolTip(index)
    assert window.outliner.item(calc).text(1) == marks.FAILED   # the tree reads it the same
    window.select(calc)                                  # and the form (P8)
    assert window.properties.form.status.text() == \
        "result: failed, ValueError: no band here (line 1 of the code)"
    window.toggle_detached(calc)                         # its window's title says it too
    assert window.plot_windows[calc].windowTitle() == f"Result {calc} python {marks.FAILED}"
    window.toggle_detached(calc)
    index = window.viewport.indexOf(view)
    session.do("set_param", entry=calc, name="code", value=QUICK)
    first = session.run_calculation(calc, wait=True, timeout=300)
    assert first.status == "done", first.error
    qtbot.waitUntil(lambda: view.result is first.value, timeout=10_000)
    session.do("set_param", entry=calc, name="code", value=FAIL)
    job = session.run_calculation(calc, wait=True, timeout=300)
    assert job.status == "failed" and session.status(calc) == "stale"   # the earlier result
    qtbot.waitUntil(lambda: row.state == "stale", timeout=5000)
    assert row.isVisibleTo(view) and row.text.full.startswith(f"{marks.STALE} stale")
    assert view.findChild(QToolButton, f"plotRun_{calc}").isVisibleTo(view)
    assert window.viewport.tabText(index) == f"{calc} python {marks.STALE}"
    assert window.viewport.tabBar().tabTextColor(index).name() != theme.ERROR
    assert window.outliner.item(calc).text(1) == marks.STALE
    window.select(calc)
    assert window.properties.form.status.text() == "result: stale"
    assert view.result is first.value                    # the earlier result stays drawn
    table = window.jobs.table                            # the failure is in the Jobs panel
    status = table.item(window.jobs.rows[job.id], 2)
    assert status.text().startswith("failed: ") and "no band here" in status.text()
    session.undo()                       # the code that ran: the earlier result is current
    assert session.status(calc) == "done"
    qtbot.waitUntil(lambda: not row.isVisibleTo(view), timeout=5000)
    assert window.viewport.tabText(index) == f"{calc} python"
    assert window.outliner.item(calc).text(1) == marks.DONE
    assert window.properties.form.status.text() == "result: done"
    assert window.viewport.tabToolTip(index) == ""


def test_the_kspace_tab_is_there_only_for_a_periodic_system(window, qtbot):
    load(qtbot, window, "honeycomb_zeeman_rashba")
    assert window.viewport.isTabVisible(KSPACE_TAB)
    window.viewport.setCurrentIndex(KSPACE_TAB)
    load(qtbot, window, "graphene_island")               # 0D: no Brillouin zone
    assert not window.viewport.isTabVisible(KSPACE_TAB)
    assert window.current_tab() == "structure"           # not the tab next to it
    window.show_result("c1")
    visible = [window.viewport.tabText(i) for i in range(window.viewport.count())
               if window.viewport.isTabVisible(i)]
    assert visible == ["Structure", "c1 dos"]
    load(qtbot, window, "honeycomb_zeeman_rashba")
    assert window.viewport.isTabVisible(KSPACE_TAB)
    session = window.session                             # the selected system decides
    island = session.do("add_system", lattice="honeycomb_lattice")
    session.do("add_geometry_op", system=island, kind="island", params={"n": 2.0})
    window.select(island)
    settle(qtbot, window)
    assert window.current_system() == island and not window.viewport.isTabVisible(KSPACE_TAB)
    window.select("s1")
    settle(qtbot, window)
    assert window.viewport.isTabVisible(KSPACE_TAB)
    session.act("new")                                   # no system, no Brillouin zone
    settle(qtbot, window)
    assert not window.viewport.isTabVisible(KSPACE_TAB)


def test_every_bar_control_has_a_tooltip(window, qtbot):
    load(qtbot, window, "honeycomb_zeeman_rashba")
    window.show_result("c1")
    missing = []
    for bar in [window.structure.bar, window.kspace_view.bar, window.plots["c1"].bar]:
        for group in bar.findChildren(QToolBar):
            if group is bar.toolbar:
                continue
            for widget in group.findChildren(QWidget):
                if widget.objectName().startswith("qt_") or \
                        type(widget).__name__ in ("QLabel", "QWidget", "QFrame") or \
                        widget.parent() is not group:
                    continue
                if not widget.toolTip():
                    missing.append(widget.objectName())
    row = window.plots["c1"].status                       # and the status row's
    missing += [w.objectName() for w in (row.run, row.cancel, row.progress) if not w.toolTip()]
    assert not missing
    assert shortcuts.text("run") in row.run.toolTip()
    assert shortcuts.text("cancel") in row.cancel.toolTip()
