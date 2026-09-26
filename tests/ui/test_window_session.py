"""The window driven offscreen through its job panel (PLAN.md section 7, decision 14.2):
run through the Run button, progress, cancel a running job through the job
panel, the worker respawns and the window stays usable."""
import pytest
from PySide6.QtWidgets import QToolButton

from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def wait_for(qtbot, condition, timeout=300_000):
    qtbot.waitUntil(condition, timeout=timeout)


def test_preset_is_shown_and_built(window, qtbot):
    assert window.calc_box.count() == 2
    wait_for(qtbot, lambda: "s1" in window.builds, 120_000)
    assert window.builds["s1"]["mode"] == "spinful" and window.builds["s1"]["sites"] == 8
    texts = [window.outliner.item(t).text(0) for t in ("t1", "t2")]
    assert texts == ["t1  Zeeman / exchange field", "t2  Rashba spin-orbit coupling"]
    assert window.outliner.item("t1").text(1) == "→ spinful"
    assert "8 sites" in window.status_label.text()


def test_run_button_draws_the_result(window, qtbot, shot):
    window.select_calculation("c1")
    window.run_button.click()
    job = window.session.calc_jobs["c1"]
    wait_for(qtbot, lambda: job.done)
    assert job.status == "done", job.error
    wait_for(qtbot, lambda: window.plot.result is not None, 10_000)
    ax = window.plot.figure.axes[0]
    assert ax.collections and "c1 · bands" in ax.get_title()      # coloured scatter
    shot(window, "bands")


def test_cancel_running_job_keeps_window_usable(window, qtbot, shot):
    session = window.session
    s = session.do("add_system", lattice="honeycomb_lattice", name="big flake")
    session.do("add_geometry_op", system=s, kind="supercell", params={"n": [12, 12, 1]})
    big = session.do("add_calculation", system=s, kind="bands", params={"nk": 400, "operator": "sz"})
    batch = session.jobs.workers["batch"][0]
    starts, old_pid = batch.starts, batch.process.pid
    window.select_calculation(big)
    window.run_button.click()
    job = session.calc_jobs[big]
    wait_for(qtbot, lambda: job.status == "running", 120_000)
    button = window.jobs.findChild(QToolButton, f"cancel_{job.id}")
    assert button is not None and button.isEnabled()
    button.click()
    wait_for(qtbot, lambda: job.status == "cancelled", 10_000)
    assert batch.starts == starts + 1 and batch.process.pid != old_pid
    assert "restarted 1x" in window.jobs.workers.text() or "restarted" in window.jobs.workers.text()
    assert not button.isEnabled()
    # the window is still usable: the next calculation runs on the new worker
    window.select_calculation("c2")
    window.run_button.click()
    job2 = session.calc_jobs["c2"]
    wait_for(qtbot, lambda: job2.done)
    assert job2.status == "done", job2.error
    wait_for(qtbot, lambda: window.plot.result is job2.value, 10_000)
    assert window.plot.figure.axes[0].lines
    shot(window, "after_cancel")


def test_undo_and_stale_marking(window, qtbot):
    session = window.session
    window.select_calculation("c1")
    session.do("set_param", entry="t2", name="c", value=0.3)
    assert session.status("c1") == "stale"
    assert "STALE" in window.plot.figure.axes[0].get_title()
    window.undo_action.trigger()
    assert session.status("c1") == "done"
    assert "STALE" not in window.plot.figure.axes[0].get_title()


def test_invalid_entry_is_flagged_in_the_tree(window, qtbot):
    session = window.session
    s = session.do("add_system", lattice="square_lattice", name="square")
    t = session.do("add_term", system=s, kind="sublattice_imbalance")

    def flagged():
        item = window.outliner.item(t)
        return item.text(0).startswith(f"✗ {t}") and "sublattice" in item.text(1)
    wait_for(qtbot, flagged, 120_000)


def test_errors_are_logged_not_raised(window):
    window._act("run_calculation", calculation="no_such_calc")
    assert "ERROR: run_calculation" in window.log.toPlainText()
