"""What the bug hunt of 2026-09-27 found in the window: a result that
cannot be drawn, a geometry without sites, the brush over another system,
sliders of removed or locked parameters, text typed while a build
finishes. None of them may raise out of a Qt callback (pytest-qt fails the
test then) or stop the window from rebuilding."""
import numpy as np
import pytest

from guiqula.core.results import Result
from guiqula.ui.app import build_main_window


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


def fresh(qtbot, window, name="honeycomb_zeeman_rashba"):
    window.open_document(name)
    settle(qtbot, window)
    return len(window.log.toPlainText())


def errors_since(window, start):
    return [line for line in window.log.toPlainText()[start:].splitlines()
            if line.startswith(("ERROR", "UNEXPECTED"))]


def test_a_result_that_cannot_be_drawn_says_why(window, qtbot):
    start = fresh(qtbot, window)
    window.session._keep_result("c1", Result(
        calculation="c1", kind="python", key="old", params={},
        arrays={"mu": np.array(0.0), "n": np.arange(3.0)},
        plot={"kind": "lines", "x": "mu", "y": "n"}))
    window.show_result("c1")
    assert window.plots["c1"].caption.text().startswith("this result cannot be drawn")
    ok, _ = window._do("set_param", entry="t2", name="c", value=0.2)
    assert ok                                   # the edit is not reported as failed
    settle(qtbot, window)                       # and the geometry is built again
    assert window.session.build_is_current("s1") and not errors_since(window, start)


def test_a_geometry_without_sites(window, qtbot):
    start = fresh(qtbot, window)
    s2 = window._act("add_system", lattice="diamond_lattice")
    term = window._act("add_term", system=s2, kind="onsite")
    window.select(s2)
    settle(qtbot, window)
    window.select_sites(all=True)
    window.remove_selected()
    settle(qtbot, window)
    assert window.builds[s2]["sites"] == 0 and "0 sites" in window.structure.caption.text()
    window.set_canvas_view("hamiltonian")
    settle(qtbot, window)
    qtbot.waitUntil(lambda: window.builds[s2].get("view"), timeout=120_000)
    window.preview_field(term, "mu")
    assert "no sites" in window.structure.caption.text()
    window.undo()                               # the sites come back
    settle(qtbot, window)
    assert window.builds[s2]["sites"] > 0 and window.redo_action.isEnabled()
    assert not errors_since(window, start)
    window.set_canvas_view("structure")


def test_the_brush_paints_only_the_system_it_is_drawn_on(window, qtbot):
    fresh(qtbot, window)
    s2 = window._act("add_system", lattice="honeycomb_lattice")
    settle(qtbot, window)
    window.preview_field("t2", "c")                 # a Field of s1
    assert window.structure.paint.isEnabled()
    window.select(s2)
    assert not window.structure.paint.isEnabled()
    before = window.session.document.to_json()
    window._paint_stroke([0], True)                 # sites of s2
    assert window.session.document.to_json() == before
    window.select("t2")
    assert window.structure.paint.isEnabled()
    window.set_canvas_view("structure")


def test_sliders_of_removed_or_locked_parameters(window, qtbot):
    fresh(qtbot, window)
    window.add_slider("t2", "c", None, 0.0, 1.0)
    window._do("remove", entry="t2")
    assert window.sliders == []
    window._slider_moved(0, 0.5, False)             # a stale index: reported, not raised
    start = fresh(qtbot, window, "graphene_basics")
    assert window._act("slider", entry="c2", param="delta", minimum=0.01,
                       maximum=0.2) is None         # c2 is locked
    assert window.sliders == [] and "locked" in errors_since(window, start)[-1]


def test_text_being_typed_survives_a_finished_build(window, qtbot):
    fresh(qtbot, window)
    window.select("t1")
    editor = window.properties.form.editors["m"].components[1].edit
    assert window._do("set_param", entry="t1", name="m", value=[0.1, 0.0, 0.3])[0]
    editor.setText("0.5")                           # typed, not confirmed yet
    settle(qtbot, window)                           # the rebuild of the first edit ends
    assert editor.text() == "0.5"
    job = window.session.run_calculation("c1")
    qtbot.waitUntil(lambda: job.done, timeout=300_000)
    qtbot.wait(200)
    assert editor.text() == "0.5"


def test_neighbour_hoppings_that_are_not_finite_are_refused_in_the_system_form(window, qtbot):
    """"nan" typed into the System form's neighbour hoppings was stored: the
    edit was reported as failed although applied, the form raised out of
    its slot (a crash report) and the system could no longer be built."""
    start = fresh(qtbot, window)
    window.select("s1")
    form = window.properties.form
    for text in ("nan", "1, inf", "1e999"):
        form.tij.setText(text)
        form.tij.editingFinished.emit()
        assert "must be finite numbers" in form.error.text()
        assert window.session.document.system("s1").hamiltonian.construction.tij == [1.0]
        assert form.tij.text() == "1"                     # the form shows the stored value
    assert not window.session.dispatcher.can_undo()
    settle(qtbot, window)
    assert window.session.build_is_current("s1")
    assert [line for line in errors_since(window, start) if "UNEXPECTED" in line] == []


def test_the_jobs_panel_keeps_the_newest_finished_rows(qapp, monkeypatch):
    from types import SimpleNamespace
    from guiqula.ui import jobpanel
    monkeypatch.setattr(jobpanel, "ROWS_KEPT", 3)
    panel = jobpanel.JobPanel()
    running = SimpleNamespace(id="j1", kind="run", label="c1", status="running", error=None,
                              traceback=None, progress=0.5, done=False)
    panel.update_job(running)
    for n in range(2, 7):
        panel.update_job(SimpleNamespace(id=f"j{n}", kind="run", label="c1", status="done",
                                         error=None, traceback=None, progress=1.0, done=True))
    assert list(panel.rows) == ["j1", "j5", "j6"]          # the running one stays
    assert [panel.table.item(r, 0).text() for r in range(3)] == ["j1", "j5", "j6"]
    panel.update_job(SimpleNamespace(**dict(vars(running), status="done", done=True)))
    assert panel.table.item(panel.rows["j1"], 2).text() == "done"
