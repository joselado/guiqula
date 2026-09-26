"""The phase-3 workspace driven offscreen: the f(r) Field editor and its
preview on the structure, the Hamiltonian view (13.8), the term search,
the mean-field block, result tabs with their readout, the cost guard
(13.12) and the automatic re-run of cheap stale results (PLAN.md section
4, 3.8)."""
import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent
from matplotlib.collections import LineCollection
from matplotlib.quiver import Quiver
from PySide6.QtWidgets import QLineEdit, QPushButton

from guiqula.engine.calculations import run_calculation
from guiqula.ui.app import build_main_window
from guiqula.ui.plots import PlotView
from guiqula.ui.properties import EntryForm, MeanFieldForm


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def settled(window):
    session = window.session
    return not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems)


def settle(qtbot, window, timeout=120_000):
    qtbot.waitUntil(lambda: settled(window), timeout=timeout)


def fresh(qtbot, window):
    window.session.act("load", path="honeycomb_zeeman_rashba")
    window.select("")
    window.set_workspace("geometry")
    settle(qtbot, window)


def finish(editor):
    editor.editingFinished.emit()


def test_field_editor_goes_piecewise_and_back(window, qtbot, shot):
    fresh(qtbot, window)
    session = window.session
    region = session.do("add_region", system="s1", name="upper",
                        select={"kind": "expression", "expr": "y > 0"})
    window.select("t2")
    editor = window.properties.form.editors["c"]
    assert editor.button.text() == "f(r)" and not editor.panel.isVisible()
    editor.button.click()
    assert editor.panel.isVisible() and editor.kind.currentIndex() == 0
    editor.kind.setCurrentIndex(1)
    editor.kind.activated.emit(1)                      # one value per region
    assert session.document.find("t2")[-1].params["c"] == {
        "kind": "piecewise", "default": 0.1, "pieces": []}
    editor = window.properties.form.editors["c"]       # updated in place
    assert editor.edit.isReadOnly() and editor.panel.isVisible()
    editor.add.click()
    assert session.document.find("t2")[-1].params["c"]["pieces"] == [
        {"region": region, "value": 0.1}]
    row = editor.rows[0]
    row.value.setText("0.3*x")
    finish(row.value)
    editor.default.setText("0.05")
    finish(editor.default)
    assert session.document.find("t2")[-1].params["c"] == {
        "kind": "piecewise", "default": 0.05, "pieces": [{"region": region, "value": "0.3*x"}]}
    assert "upper: 0.3*x" in editor.edit.text() and editor.button.font().bold()
    with pytest.raises(Exception, match="used by"):
        session.do("remove", entry=region)             # a piecewise Field uses it
    shot(window, "piecewise")
    editor.rows[0].remove.click()
    assert session.document.find("t2")[-1].params["c"]["pieces"] == []
    editor.kind.setCurrentIndex(0)
    editor.kind.activated.emit(0)                      # back to a number: the default
    assert session.document.find("t2")[-1].params["c"] == 0.05
    for _ in range(6):
        session.undo()
    assert session.document.find("t2")[-1].params["c"] == 0.1


def test_field_preview_draws_the_field(window, qtbot, shot):
    """A vector Field: arrows for the in-plane part, dots for z; typing
    previews the text before it is committed."""
    fresh(qtbot, window)
    session = window.session
    session.do("set_param", entry="t1", name="m", value=[0.1, "0.1*x", "0.3*tanh(x/4)"])
    settle(qtbot, window)
    window.select("t1")
    assert session.act("preview", entry="t1", param="m") == "field"
    assert window.structure.view_box.currentData() == "field"
    ax = window.structure.ax
    assert any(isinstance(a, Quiver) for a in ax.get_children())
    assert "t1 field (mx, my, mz)" in window.structure.caption.text()
    colorbars = [a for a in window.structure.figure.axes if a is not ax]
    assert colorbars and "z (dots)" in colorbars[0].get_ylabel()
    shot(window.structure, "vector_preview")
    with pytest.raises(ValueError, match="no Field 'nope'"):
        session.act("preview", entry="t1", param="nope")
    window.select("t2")
    editor = window.properties.form.editors["c"]
    editor.edit.setText("0.5*x")
    editor.edit.textEdited.emit("0.5*x")               # typing, not committed
    qtbot.waitUntil(lambda: "t2 strength: from" in window.structure.caption.text(),
                    timeout=5000)
    positions = window.builds["s1"]["positions"]
    low, high = 0.5 * positions[:, 0].min(), 0.5 * positions[:, 0].max()
    assert f"from {low:.4g} to {high:.4g}" in window.structure.caption.text()
    assert session.document.find("t2")[-1].params["c"] == 0.1


def test_hamiltonian_view(window, qtbot, shot):
    fresh(qtbot, window)
    session = window.session
    session.do("add_term", system="s1", kind="haldane", params={"t": 0.1})
    session.do("add_term", system="s1", kind="onsite", params={"mu": "0.2*x"})
    settle(qtbot, window)
    assert window.builds["s1"]["hamiltonian"] is None       # not computed while not shown
    window.set_workspace("hamiltonian")
    assert window.canvas_view == "hamiltonian"
    qtbot.waitUntil(lambda: window.builds["s1"]["hamiltonian"] is not None, timeout=60_000)
    view = window.builds["s1"]["hamiltonian"]
    assert len(view["hoppings"]) > len(window.builds["s1"]["bonds"])   # second neighbours
    ax = window.structure.ax
    bonds = [c for c in ax.collections if isinstance(c, LineCollection) and c.get_zorder() == 3]
    widths = np.concatenate([c.get_linewidths() for c in bonds])
    assert widths.max() > 2 * widths.min()             # |t| sets the width
    labels = [a.get_ylabel() or a.get_xlabel() for a in window.structure.figure.axes if a is not ax]
    assert "onsite energy" in labels and "hopping phase" in labels
    assert "|t| up to" in window.structure.caption.text()
    shot(window.structure, "hamiltonian_view")
    session.act("canvas_view", name="structure")
    assert window.structure.view_box.currentData() == "structure"


def test_term_search(window, qtbot):
    fresh(qtbot, window)
    window.set_workspace("hamiltonian")
    search = window.findChild(QLineEdit, "termSearch")
    search.setText("kane")
    search.returnPressed.emit()
    assert window.session.document.find(window.selected)[-1].kind == "kane_mele"
    assert isinstance(window.properties.form, EntryForm)
    qtbot.waitUntil(lambda: search.text() == "", timeout=2000)
    search.setText("superconduct")                        # the group matches too
    search.returnPressed.emit()
    assert window.session.document.find(window.selected)[-1].kind == "swave"
    count = len(window.session.document.system("s1").hamiltonian.terms)
    search.setText("no such physics")
    search.returnPressed.emit()
    assert len(window.session.document.system("s1").hamiltonian.terms) == count
    assert "no term matches" in window.log.toPlainText()


def test_meanfield_block(window, qtbot, shot):
    fresh(qtbot, window)
    session = window.session
    window.set_workspace("hamiltonian")
    window.findChild(QPushButton, "meanfieldButton").click()
    form = window.properties.form
    assert window.selected == "s1/meanfield" and isinstance(form, MeanFieldForm)
    assert window.outliner.item("s1/meanfield").text(1) == "off"
    form.enabled.setChecked(True)
    assert session.document.system("s1").hamiltonian.meanfield.enabled
    form = window.properties.form
    form.editors["U"].edit.setText("2.5")
    finish(form.editors["U"].edit)
    assert session.document.system("s1").hamiltonian.meanfield.params["U"] == 2.5
    temperature = form.editors["T"].edit                   # empty: the engine's default
    assert temperature.text() == "" and temperature.placeholderText() == "default"
    temperature.setText("1e-4")
    finish(temperature)
    assert session.document.system("s1").hamiltonian.meanfield.params["T"] == 1e-4
    temperature = window.properties.form.editors["T"].edit
    temperature.setText("")
    finish(temperature)
    assert session.document.system("s1").hamiltonian.meanfield.params["T"] is None
    solvers = window.properties.form.editors["solver"].combo
    assert {"newton", "linear_mixing"} <= {solvers.itemText(i) for i in range(solvers.count())}
    form = window.properties.form
    assert "runs with every calculation" in form.status.text()
    assert window.outliner.item("s1/meanfield").text(1) == "runs with the calculations"
    settle(qtbot, window)
    assert window.builds["s1"]["reports"][-1]["status"] == "deferred"   # not while editing
    window.select_calculation("c1")
    job = session.run_calculation("c1")
    qtbot.waitUntil(lambda: job.done, timeout=300_000)
    assert job.status == "done", job.error
    assert job.value.meanfield["total_energy"] < 0
    qtbot.waitUntil(lambda: window.outliner.item("s1/meanfield").text(1).startswith("E = "),
                    timeout=10_000)
    shot(window, "meanfield")
    item = window.outliner.item("s1/meanfield")          # its checkbox turns it off
    item.setCheckState(0, item.checkState(0).__class__.Unchecked)
    qtbot.waitUntil(lambda: not session.document.system("s1").hamiltonian.meanfield.enabled,
                    timeout=5000)


def test_result_tabs_readout_and_detach(window, qtbot, shot):
    fresh(qtbot, window)
    session = window.session
    window.select("c2")
    assert window.current_tab() == "c2" and isinstance(window.plot, PlotView)
    assert "no result yet" in window.plot.caption.text()
    session.run_calculation("c2", wait=True, timeout=300)
    qtbot.waitUntil(lambda: window.plots["c2"].result is not None, timeout=10_000)
    view = window.plots["c2"]
    assert view.objectName() == "plot_c2" and view.save_data.isEnabled()
    x, y = view.points[0][10], view.points[1][10]
    px, py = view.ax.transData.transform((x, y))
    MouseEvent("motion_notify_event", view.canvas, px, py)._process()
    i = view.point_near(int(px), int(py))       # events carry whole pixels; points are close
    assert abs(i - 10) <= 2 and view.readout.text() == view.readout_text(i)
    assert view.readout.text().startswith(f"energy {view.points[0][i]:.6g} · DOS ")
    session.do("set_param", entry="t2", name="c", value=0.2)
    index = window.viewport.indexOf(view)
    assert window.viewport.tabText(index) == "c2 dos (stale)"
    assert window.toggle_detached("c2") is True             # into a floating dock
    assert window.viewport.indexOf(view) < 0 and window.plot_docks["c2"].isFloating()
    assert view.detach.text() == "Attach"
    shot(window.plot_docks["c2"], "detached")
    view.detach.click()                                     # Attach
    assert "c2" not in window.plot_docks and window.viewport.indexOf(view) > 0
    window.viewport.tabCloseRequested.emit(window.viewport.indexOf(view))
    assert "c2" not in window.plots and window.current_tab() == "structure"
    window.select("c1")
    session.do("remove", entry="c1")                        # its tab goes with it
    assert "c1" not in window.plots


def test_cost_guard_asks_before_a_long_run(window, qtbot):
    fresh(qtbot, window)
    session = window.session
    s = session.do("add_system", lattice="honeycomb_lattice", name="large")
    session.do("add_geometry_op", system=s, kind="supercell", params={"n": [30, 30, 1]})
    calc = session.do("add_calculation", system=s, kind="bands", params={"nk": 300})
    settle(qtbot, window)
    window.select_calculation(calc)
    estimate = session.estimate(calc)
    assert estimate["dimension"] == 3600 and estimate["seconds"] > 60
    assert f"{calc}: about" in window.status_label.text()
    window.run_button.click()
    assert window.cost_bar.isVisible() and "Run it anyway?" in window.cost_bar.label.text()
    assert calc not in session.calc_jobs                   # nothing started
    window.cost_bar.button("costCancelButton").click()
    assert not window.cost_bar.isVisible() and calc not in session.calc_jobs
    window.outliner.command.emit("run_calculation", {"calculation": calc})   # its context menu
    assert window.cost_bar.isVisible() and calc not in session.calc_jobs
    window.select_calculation("c1")                       # the bar still means the large one
    window.cost_bar.button("runAnywayButton").click()
    job = session.calc_jobs[calc]
    assert "c1" not in session.calc_jobs
    assert not window.cost_bar.isVisible()
    session.cancel(job.id)
    qtbot.waitUntil(lambda: job.done, timeout=10_000)
    assert job.status == "cancelled"


def test_geometry_change_reruns_bands_with_the_same_terms(window, qtbot, shot):
    """Phase 3 acceptance: change the geometry after setting the terms; the
    bands, re-run on the new geometry (here automatically, as the opt-in
    auto re-run does for cheap results), apply the same terms to it."""
    fresh(qtbot, window)
    session = window.session
    window.select("c1")
    first = session.run_calculation("c1", wait=True, timeout=300).value
    assert first.arrays["energies"].shape[1] == 16          # 8 sites, spinful
    assert session.act("auto_rerun", enabled=True) is True
    session.do("set_param", entry="op1", name="n", value=[3, 3, 1])
    assert session.status("c1") == "stale"
    qtbot.waitUntil(lambda: session.result("c1") is not first and
                    not session.is_stale("c1"), timeout=300_000)
    second = session.result("c1")
    assert second.arrays["energies"].shape[1] == 36         # 18 sites, spinful
    assert [r["status"] for r in second.reports if r["stage"] == "term"] == ["ok", "ok"]
    direct = run_calculation(session.document, "c1")         # the same terms, by the engine
    assert np.allclose(second.arrays["energies"], direct.arrays["energies"], atol=1e-12)
    qtbot.waitUntil(lambda: window.plot.result is second, timeout=10_000)
    assert "STALE" not in window.plot.ax.get_title()
    shot(window, "rerun_on_new_geometry")
    session.act("auto_rerun", enabled=False)
    session.do("set_param", entry="op1", name="n", value=[2, 2, 1])
    settle(qtbot, window)
    assert session.status("c1") == "stale"                  # off: waits for Run
    assert window.view_state().get("auto_rerun") is None
