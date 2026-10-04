"""Run where the result is (PLAN.md section 7, phase 8, package P4): Run names
the calculation it acts on, which is chosen in the outliner or by its tab and
nowhere else; its menu runs another one or every stale result; a
calculation's form ends with its estimate and a button that runs it, runs it
again when stale and cancels it while it runs."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton

from guiqula.ui.app import build_main_window
from guiqula.ui.properties import EntryForm


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)


def click_tab(window, calc):
    bar = window.viewport.tabBar()
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton,
                     pos=bar.tabRect(window.viewport.indexOf(window.plots[calc])).center())


def test_run_names_the_calculation_of_the_outliner_or_the_tab(window, qtbot):
    run = window.run_button
    assert window.findChild(QComboBox, "calculationBox") is None    # one place to choose
    assert window.selected == "" and window.current_tab() == "structure"
    assert run.text() == "Run c1 · bands" and run.isEnabled()        # nothing chosen: the first
    window.select("c2")                                              # the outliner
    assert window.current_tab() == "c2" and run.text() == "Run c2 · dos"
    assert "c2, density of states on s1" in run.toolTip().lower() and run.toolTip().endswith("(F5)")
    assert window._fill_run_menu() == ["runCalc_c1", "runStaleAction"]   # the others
    assert window.run_menu.actions()[0].text() == "Run c1 · bands"
    window.select("t1")                    # a term shows the structure: Run the first again
    assert window.current_tab() == "structure" and run.text() == "Run c1 · bands"
    window.show_result("c2")               # the tab shown, the term still selected
    assert window.selected == "t1" and window.selected_calculation() == "c2"
    assert run.text() == "Run c2 · dos"
    window.viewport.setCurrentIndex(0)
    assert run.text() == "Run c1 · bands"
    # a click on a result tab while another calculation is selected selects the tab's, so
    # the outliner and the tab never name two calculations
    window.select("c1")
    click_tab(window, "c2")
    assert window.selected == "c2" and window.outliner.current_id() == "c2"
    form = window.properties.form
    assert isinstance(form, EntryForm) and form.item_id == "c2" and run.text() == "Run c2 · dos"
    # while a term is selected, a click on a tab keeps the term and its form
    window.select("t1")
    click_tab(window, "c1")
    assert window.selected == "t1" and window.current_tab() == "c1"
    assert run.text() == "Run c1 · bands" and window.properties.form.item_id == "t1"
    # select_calculation (tools/drive.py --run) selects it in the outliner
    assert window.select_calculation("c2") == "c2" and window.selected == "c2"
    assert window.workspace == "calculate" and run.text() == "Run c2 · dos"
    with pytest.raises(KeyError):
        window.select_calculation("t1")
    with pytest.raises(Exception, match="no calculation 'nope'"):
        window.session.act("run", calculation="nope")
    settle(qtbot, window)
    assert "c2: under a second" in window.status_label.text()      # the same one


def test_the_outliner_follows_the_tab_the_user_shows(window):
    viewport, run = window.viewport, window.run_button
    for calc in list(window.plots):
        window.close_result(calc)
    window.select("c1")
    window.result_view("c2")                                    # c1's tab, then c2's
    assert window.current_tab() == "c1"
    # Ctrl+Tab and Ctrl+Shift+Tab choose a result as a click does: the outliner follows
    QTest.keyClick(viewport, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
    assert window.current_tab() == "c2" and window.selected == "c2"
    assert window.outliner.current_id() == "c2" and run.text() == "Run c2 · dos"
    QTest.keyClick(viewport, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.ShiftModifier)
    assert window.current_tab() == "c1" and window.selected == "c1"
    QTest.keyClick(viewport, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.ShiftModifier)
    assert window.current_tab() == "kspace" and window.selected == "c1"   # not a result
    assert run.text() == "Run c1 · bands"
    window.show_result("c2")                     # a pick's target shows another result
    assert window.selected == "c2" and window.properties.form.item_id == "c2"
    # the neighbour Qt shows when the tab shown goes away was chosen by nobody
    window.select("c1")
    assert window.toggle_detached("c1") is True             # c2's tab is shown in its place
    assert window.current_tab() == "c2" and window.selected == "c1"
    assert run.text() == "Run c1 · bands"
    click_tab(window, "c2")                     # a click on it, although it is shown, does
    assert window.selected == "c2"
    assert window.toggle_detached("c1") is False            # back in its tab, which is shown
    assert window.current_tab() == "c1" and window.selected == "c1"
    window.close_result("c1")                   # c2's tab for a moment, then the structure
    assert window.current_tab() == "structure" and window.selected == "c1"
    assert run.text() == "Run c1 · bands"


def test_the_estimate_line_says_why_there_is_none(window, qtbot):
    session = window.session
    settle(qtbot, window)
    calc = session.do("add_calculation", system="s1", kind="python")
    try:
        window.select(calc)
        estimate = window.properties.findChild(QLabel, "formEstimate")
        assert estimate.text() == "no estimate, so Run does not ask first"     # no cost
        session.act("trust", enabled=False)
        estimate = window.properties.findChild(QLabel, "formEstimate")
        assert estimate.text().startswith("invalid: Python code") and "trusted" in estimate.text()
    finally:
        session.act("trust")
        session.do("remove", entry=calc)
    system = session.do("add_system", lattice="honeycomb_lattice")
    calc = session.do("add_calculation", system=system, kind="bands")
    try:
        window.select(calc)                     # before its system is built
        estimate = window.properties.findChild(QLabel, "formEstimate")
        assert estimate.text() == f"estimate: once {system} is built"
        settle(qtbot, window)
        assert estimate.text() == "estimate: under a second"
    finally:
        session.do("remove", entry=calc)
        session.do("remove", entry=system)


def test_f5_and_the_run_action_run_the_selected_calculation(window, qtbot):
    session = window.session
    window.select("c1")
    action = window.findChild(QAction, "runAction")
    action.trigger()                                                  # F5
    job = session.calc_jobs["c1"]
    assert "c2" not in session.calc_jobs or session.calc_jobs["c2"].done
    qtbot.waitUntil(lambda: job.done, timeout=300_000)
    assert job.status == "done", job.error
    window.select("t1")
    window.viewport.setCurrentIndex(0)
    summary = session.act("run", calculation="c2")                     # the form's route
    assert summary["label"] == "c2" and session.calc_jobs["c2"].id == summary["id"]
    qtbot.waitUntil(lambda: session.calc_jobs["c2"].done, timeout=300_000)
    assert session.calc_jobs["c2"].status == "done", session.calc_jobs["c2"].error


def test_run_every_stale_result_runs_exactly_the_stale_ones(window, qtbot):
    session = window.session
    for calc in ("c1", "c2"):
        if session.status(calc) != "done":
            session.run_calculation(calc, wait=True, timeout=600)
    gap = session.do("add_calculation", system="s1", kind="gap")      # no result: not stale
    try:
        session.do("set_param", entry="c2", name="delta", value=0.1)  # c2's key alone
        assert [session.status(c) for c in ("c1", "c2", gap)] == ["done", "stale", "none"]
        before = {c: session.calc_jobs[c] for c in ("c1", "c2")}
        window._fill_run_menu()
        assert window.run_stale_action.isEnabled()
        window.run_stale_action.trigger()
        assert session.calc_jobs["c1"] is before["c1"] and gap not in session.calc_jobs
        job = session.calc_jobs["c2"]
        assert job is not before["c2"]
        qtbot.waitUntil(lambda: job.done, timeout=300_000)
        assert job.status == "done" and session.status("c2") == "done"
        assert session.act("run_stale") == []                           # nothing left
    finally:
        session.do("remove", entry=gap)


def test_the_form_runs_runs_again_and_cancels(window, qtbot):
    session = window.session
    calc = session.do("add_calculation", system="s1", kind="dos",
                      params={"ne": 40, "nk": 4, "emin": -1, "emax": 1})
    try:
        settle(qtbot, window)
        window.select(calc)
        form = window.properties.form
        button = window.properties.findChild(QPushButton, "formRun")
        estimate = window.properties.findChild(QLabel, "formEstimate")
        # the row is the form's, shown under it in the panel's footer, out of the scrolled
        # area, so that Run stays in sight however long the form is (package P8)
        assert form.run_button is button and form.run_estimate is estimate
        footer = window.properties.footer
        assert button.parentWidget() is form.run_row and form.run_row.parentWidget() is footer
        assert footer.isVisible() and not window.properties.scroll.isAncestorOf(button)
        assert button.text() == "Run" and estimate.text() == "estimate: under a second"
        assert button.toolTip().endswith("(F5)")
        button.click()                                 # Run
        job = session.calc_jobs[calc]
        assert button.text() == "Cancel" and button.toolTip().endswith("(Esc)")
        assert estimate.text().startswith(("queued", "running"))
        assert window.cancel_button.isEnabled()
        button.click()                                 # Cancel
        qtbot.waitUntil(lambda: job.done, timeout=10_000)
        assert job.status == "cancelled" and button.text() == "Run"
        assert not window.cancel_button.isEnabled()
        button.click()                                 # Run, to the end
        job = session.calc_jobs[calc]
        qtbot.waitUntil(lambda: job.done, timeout=300_000)
        assert job.status == "done", job.error
        assert window.properties.form is form and button.text() == "Run"
        session.do("set_param", entry=calc, name="delta", value=0.1)
        assert session.status(calc) == "stale"
        button = window.properties.findChild(QPushButton, "formRun")
        assert button.text() == "Run again" and "changed" in button.toolTip()
        button.click()
        job = session.calc_jobs[calc]
        qtbot.waitUntil(lambda: job.done, timeout=300_000)
        assert job.status == "done" and button.text() == "Run"
        # a term's form has no Run
        window.select("t1")
        assert window.properties.findChild(QPushButton, "formRun") is None
        assert not window.properties.footer.isVisible()
    finally:
        session.do("remove", entry=calc)
