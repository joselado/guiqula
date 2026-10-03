"""What the bug hunts of 2026-09-27 and 2026-09-28 found in the window: a
result that cannot be drawn, a geometry without sites, the brush over
another system, sliders of removed or locked parameters or of an infinite
range, text typed while a build finishes or while a form is rebuilt, the
f(r) panel's own boxes and combos, a row a system does not have, the
selection after an undo. None of them may raise out of a Qt callback
(pytest-qt fails the test then) or stop the window from rebuilding."""
import json

import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from guiqula.core.results import Result
from guiqula.session import Session
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


@pytest.fixture
def still(qapp, no_jobs):
    """A window over a session that runs nothing: for what the forms, the
    outliner and the undo do by themselves."""
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session("honeycomb_zeeman_rashba", jobs=no_jobs)
    window.attach(session)
    yield window, session
    window.close()
    session.close()


def focus(qtbot, widget):
    widget.window().activateWindow()
    widget.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is widget, timeout=5000)


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


def test_a_result_that_cannot_be_drawn_is_exported_without_a_figure(window, qtbot, tmp_path):
    """Export is enabled on such a view, and it failed as a whole ('len()
    of unsized object'), leaving an empty folder: the data, the script and
    the document are written now, and the README says why no figure is."""
    import os
    start = fresh(qtbot, window)
    window.session._keep_result("c1", Result(
        calculation="c1", kind="python", key="old", params={},
        arrays={"mu": np.array(0.0), "n": np.arange(3.0)},
        plot={"kind": "lines", "x": "mu", "y": "n"},
        document=window.session.document.to_json()))
    window.show_result("c1")
    assert window.plots["c1"].export.isEnabled()
    files = window._act("export_bundle", calculation="c1", path=str(tmp_path / "c1"))
    names = ["README.txt", "data.json", "data.npz", "document.json", "script.py"]
    assert sorted(os.path.basename(p) for p in files) == names
    assert sorted(os.listdir(tmp_path / "c1")) == names
    readme = (tmp_path / "c1" / "README.txt").read_text()
    assert "The figure could not be drawn (TypeError: len() of unsized object)" in readme
    assert not errors_since(window, start)


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


def test_a_removal_op_grows_with_one_lookup(window, qtbot, monkeypatch):
    """Extending the trailing Remove atoms op looked every selected site up
    in its positions one at a time, each time hashing all of them (7 s for
    1830 sites of 7200, the window frozen): one lookup does them all now."""
    from guiqula.ui import structure as structure_tools
    fresh(qtbot, window)
    window._do("set_param", entry="op1", name="n", value=[10, 10, 1])      # 200 sites
    settle(qtbot, window)
    window.select_sites(sublattice=1)
    op = window.remove_selected()
    settle(qtbot, window)
    assert window.select_sites(all=True) == 100
    lookups = []
    lookup = structure_tools.nearest_indices
    monkeypatch.setattr(structure_tools, "nearest_indices",
                        lambda *args: lookups.append(args) or lookup(*args))
    assert window.remove_selected() == op
    assert len(window.session.document.find(op)[-1].params["positions"]) == 200
    assert len(lookups) < 20        # not one per site: the selection's updates make a few
    settle(qtbot, window)
    assert window.builds["s1"]["sites"] == 0


def test_the_brush_paints_only_the_system_it_is_drawn_on(window, qtbot):
    fresh(qtbot, window)
    s2 = window._act("add_system", lattice="honeycomb_lattice")
    settle(qtbot, window)
    window.preview_field("t2", "c")                 # a Field of s1
    assert window.structure.paint.isEnabled()
    window.select(s2)                               # the Geometry workspace: its view
    assert not window.structure.paint.isEnabled()
    before = window.session.document.to_json()
    window._paint_stroke([0], True)                 # sites of s2
    assert window.session.document.to_json() == before
    window.select("t2")
    window.set_canvas_view("field")                 # the Field previewed, on its system
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
    added = []
    panel.job_added.connect(added.append)
    running = SimpleNamespace(id="j1", kind="run", label="c1", status="running", error=None,
                              traceback=None, progress=0.5, done=False)
    panel.update_job(running)
    panel.update_job(running)
    panel.update_job(SimpleNamespace(**dict(vars(running), id="b1", kind="build")))
    assert added == ["j1"]                                 # a new row, once; no builds
    for n in range(2, 7):
        panel.update_job(SimpleNamespace(id=f"j{n}", kind="run", label="c1", status="done",
                                         error=None, traceback=None, progress=1.0, done=True))
    assert list(panel.rows) == ["j1", "j5", "j6"]          # the running one stays
    assert added == ["j1", "j2", "j3", "j4", "j5", "j6"]
    assert [panel.table.item(r, 0).text() for r in range(3)] == ["j1", "j5", "j6"]
    panel.update_job(SimpleNamespace(**dict(vars(running), status="done", done=True)))
    assert panel.table.item(panel.rows["j1"], 2).text() == "done"


def test_a_form_rebuilt_while_a_value_is_typed(still, qtbot):
    """A change of the form's signature (a region added by the console)
    while a value is typed: taking the old form out sends the value, and
    the form shows it, not the value before."""
    window, session = still
    window.select("t2")
    edit = window.properties.form.editors["c"].edit
    focus(qtbot, edit)
    edit.selectAll()
    QTest.keyClicks(edit, "0.37")                   # typed, not confirmed yet
    session.do("add_region", system="s1", name="right",
               select={"kind": "expression", "expr": "x > 0"})
    assert session.document.find("t2")[-1].params["c"] == 0.37
    assert window.properties.form.editors["c"].edit.text() == "0.37"
    assert window.properties.form.region.count() == 2        # everywhere, right


def test_undo_of_a_piece_whose_box_has_the_focus(still, qtbot):
    """Hiding the value box of a piece that has the focus finished its edit,
    which sent the old pieces again: the undo of Add a region was taken
    back at once, and removing a piece was three undo steps."""
    window, session = still
    session.do("add_region", system="s1", name="right",
               select={"kind": "expression", "expr": "x > 0"})
    session.do("set_param", entry="t2", name="c",
               value={"kind": "piecewise", "default": 0.1, "pieces": []})
    window.select("t2")

    def stored():
        return session.document.find("t2")[-1].params["c"]

    window.properties.form.editors["c"].add.click()            # Add a region
    box = window.properties.form.editors["c"].rows[0].value
    focus(qtbot, box)
    box.selectAll()
    QTest.keyClicks(box, "0.5")
    QTest.keyClick(box, Qt.Key.Key_Return)
    assert stored()["pieces"] == [{"region": "r1", "value": 0.5}]
    assert QApplication.focusWidget() is box
    window.undo_action.trigger()
    window.undo_action.trigger()                                # and Add a region
    assert stored()["pieces"] == [] and session.dispatcher.can_redo()
    window.redo_action.trigger()
    assert stored()["pieces"] == [{"region": "r1", "value": 0.1}]
    session.do("set_param", entry="t2", name="c", value={
        "kind": "piecewise", "default": 0.1,
        "pieces": [{"region": "r1", "value": 0.2}, {"region": "r1", "value": 0.3}]})
    focus(qtbot, window.properties.form.editors["c"].rows[0].value)
    steps = len(session.dispatcher.history()["undo"])
    window.properties.form.editors["c"].rows[1].remove.click()
    assert stored()["pieces"] == [{"region": "r1", "value": 0.2}]
    assert len(session.dispatcher.history()["undo"]) == steps + 1


def test_picking_the_item_shown_again_changes_nothing(still):
    """The f(r) panel's combos (QComboBox.activated fires for the item
    shown too): the same profile kept its numbers, the same result or array
    its component and scale, the same region was no undo step. Another
    one still starts afresh."""
    window, session = still

    def stored():
        return session.document.find("t2")[-1].params["c"]

    def editor():
        return window.properties.form.editors["c"]

    def pick(box, data=None):
        if data is not None:
            box.setCurrentIndex(box.findData(data))
        box.activated.emit(box.currentIndex())

    profile = {"kind": "profile", "name": "gaussian",
               "params": {"amplitude": 5.0, "x0": 1.0, "y0": 0.0, "width": 3.0}}
    session.do("set_param", entry="t2", name="c", value=profile)
    window.select("t2")
    pick(editor().profile_name)
    assert stored() == profile
    s2 = session.do("add_system", lattice="square_lattice")
    c3 = session.do("add_calculation", system=s2, kind="ldos")
    session._keep_result(c3, Result(
        calculation=c3, kind="ldos", key="k", params={},
        arrays={"m": np.ones((4, 3)), "rho": np.ones(4)},
        plot={"kind": "structure_scalar", "values": "rho"},
        structure={"positions": np.zeros((4, 3))}))
    read = {"kind": "from_result", "calculation": c3, "array": "m", "component": 2,
            "scale": 0.8, "tol": 0.1}
    session.do("set_param", entry="t2", name="c", value=read)
    pick(editor().result_array)
    pick(editor().result_calc)
    assert stored() == read
    pick(editor().result_array, "rho")
    assert stored()["array"] == "rho" and stored()["component"] is None
    session.do("add_region", system="s1", name="right",
               select={"kind": "expression", "expr": "x > 0"})
    session.do("set_param", entry="t2", name="c", value={
        "kind": "piecewise", "default": 0.1, "pieces": [{"region": "r1", "value": 0.2}]})
    steps = len(session.dispatcher.history()["undo"])
    pick(editor().rows[0].region)
    assert len(session.dispatcher.history()["undo"]) == steps


def test_a_number_the_field_panel_cannot_read_is_refused(still):
    """The f(r) panel's own boxes (a profile's numbers, the control points,
    painted's elsewhere, a result's scale) said nothing about text that is
    not a number, and kept showing it: the form says what is wrong, and the
    box shows the stored value again, as the main editors do."""
    window, session = still
    window.select("t2")

    def editor():
        return window.properties.form.editors["c"]

    def error():
        return window.properties.form.error.text()

    def stored():
        return session.document.find("t2")[-1].params["c"]

    session.do("set_param", entry="t2", name="c",
               value={"kind": "profile", "name": "gaussian", "params": {}})
    box = editor().profile_edits["amplitude"][1]
    box.setText("wide")
    box.editingFinished.emit()
    assert error() == "c: amplitude: 'wide' is not a number"
    assert box.text() == "1" and stored()["params"]["amplitude"] == 1.0
    session.do("set_param", entry="t2", name="c",
               value={"kind": "interpolated", "points": [[0.0, 0.0, 0.0]], "length": 2.0})
    editor().points.setPlainText("0, 0, 1\n3, oops, 2")
    editor().findChild(type(editor().add), "fieldPointsApply_c").click()
    assert error() == "c: points: 'oops' is not a number"
    assert editor().points.toPlainText() == "0, 0, 0"
    assert stored()["points"] == [[0.0, 0.0, 0.0]]
    session.do("set_param", entry="t2", name="c",
               value={"kind": "painted", "sites": [], "tol": 0.1, "default": 0.0})
    editor().paint_default.setText("zero")
    editor().paint_default.editingFinished.emit()
    assert error() == "c: elsewhere: 'zero' is not a number"
    assert editor().paint_default.text() == "0" and stored()["default"] == 0.0
    editor().paint_default.setText("0.25")               # a number still goes through
    editor().paint_default.editingFinished.emit()
    assert error() == "" and stored()["default"] == 0.25


def test_a_row_the_system_does_not_have(still, tmp_path):
    """s1/model on a quantum system (s2/meanfield on a classical one) is
    refused, not an AttributeError that left it selected and saved; a file
    whose ui block names such a row opens, with its trust bar."""
    window, session = still
    window.select("t1")
    with pytest.raises(ValueError, match="nothing called 's1/model'"):
        window.select("s1/model")
    assert window.selected == "t1"
    s2 = session.do("add_system", lattice="square_lattice", kind="ising")
    with pytest.raises(ValueError, match="nothing called"):
        window.select(f"{s2}/meanfield")
    with pytest.raises(ValueError, match="classical system: it has no mean field"):
        window.preview_field(f"{s2}/meanfield", "U")
    window.select(f"{s2}/model")                        # the rows it has
    window.select("s1/meanfield")
    session.do("add_term", system="s1", kind="python")  # a file with it opens untrusted
    path = tmp_path / "pseudo.json"
    session.act("save", path=str(path))
    data = json.loads(path.read_text())
    data.setdefault("ui", {})["selected"] = "s1/model"
    path.write_text(json.dumps(data))
    start = len(window.log.toPlainText())
    window.open_document(path)
    assert not [line for line in errors_since(window, start) if line.startswith("ERROR: load")]
    assert session.path == path and window.selected == ""
    assert not session.trusted and session.code_entries() and window.trust_bar.isVisible()


def test_undo_keeps_the_form_of_the_mean_field_or_the_model(still):
    window, session = still
    window.select("s1/meanfield")
    session.do("set_meanfield", system="s1", params={"U": 2.5})
    window.undo_action.trigger()
    assert window.selected == "s1/meanfield"
    assert type(window.properties.form).__name__ == "MeanFieldForm"
    window.open_document("ising_ferromagnet")
    window.select("s1/model")
    session.do("set_model", system="s1", params={"m": 0.7})
    window.undo_action.trigger()
    window.redo_action.trigger()
    assert window.selected == "s1/model"
    assert type(window.properties.form).__name__ == "ModelForm"


def test_a_slider_needs_a_finite_range(still):
    """The Sliders dock took -inf..inf: the add was reported as failed (a
    NaN), yet the slider stayed, without a row, and was saved."""
    window, session = still
    panel = window.sliders_panel
    panel.entry.setText("t2")
    panel.param.setText("c")
    panel.minimum.setText("-inf")
    panel.maximum.setText("inf")
    panel.findChild(QPushButton, "addSliderButton").click()
    assert window.log.toPlainText().splitlines()[-1] == \
        "ERROR: slider: the range needs finite numbers"
    for low, high in ((0.0, np.inf), (-1e308, 1e308)):
        assert window._act("slider", entry="t2", param="c", minimum=low, maximum=high) is None
    assert window.sliders == [] and panel.rows == [] and "sliders" not in window.view_state()
    assert window._act("slider", entry="t2", param="c", minimum=0.0, maximum=0.5) == 0


def dab(view, point):
    """One click of the brush at a point of the canvas."""
    x, y = view.ax.transData.transform(point)
    for kind in ("button_press_event", "button_release_event"):
        MouseEvent(kind, view.canvas, x, y, 1)._process()


def test_a_brush_that_is_not_a_number_paints_nothing(window, qtbot):
    """'0,5' or 'abc' in the brush's boxes painted 1.0 (a radius 0.6)
    without a word; now the stroke paints nothing and the log says why,
    once."""
    start = fresh(qtbot, window)
    window.preview_field("t2", "c")
    settle(qtbot, window)
    view = window.structure
    view.paint.setChecked(True)
    view.canvas.draw()
    before = window.session.document.to_json()
    for value, radius in (("0,5", "0.3"), ("0.5", "x")):
        view.brush_value.setText(value)
        view.brush_radius.setText(radius)
        dab(view, window.builds["s1"]["positions"][0, :2])
    assert window.session.document.to_json() == before
    assert errors_since(window, start) == [
        "ERROR: paint: the brush value '0,5' is not a number",
        "ERROR: paint: the brush radius 'x' is not a number"]
    view.brush_radius.setText("0.3")
    dab(view, window.builds["s1"]["positions"][0, :2])          # a number paints again
    assert window.session.document.find("t2")[4].params["c"]["sites"][0][3] == 0.5
    view.brush_value.setText("1")
    view.brush_radius.setText("0.6")
    window.set_canvas_view("structure")


def test_a_field_that_is_not_finite_somewhere(window, qtbot):
    """sqrt(x) is NaN where x < 0 and 1/(x+0.5) infinite at x = -0.5: the
    preview painted every atom black ('from nan to nan', or a colour bar of
    -0.1 to 0.1). The finite sites keep their colours on the scale of the
    finite values; the others are grey, and the caption counts them."""
    from matplotlib.colors import to_hex
    from guiqula.ui import structure as structure_tools, theme
    fresh(qtbot, window)
    window.preview_field("t2", "c")
    view = window.structure
    x = window.builds["s1"]["positions"][:, 0]
    for expression, finite in (("sqrt(x)", np.sqrt(np.clip(x, 0, None))),
                               ("1/(x+0.5)", 1 / (x + 0.5 + 1e-300))):
        bad = x < 0 if expression == "sqrt(x)" else np.isclose(x, -0.5)
        count = f"{int(bad.sum())} site{'s' if bad.sum() > 1 else ''} not finite (grey)"
        window._do("set_param", entry="t2", name="c", value=expression)
        settle(qtbot, window)
        qtbot.waitUntil(lambda: count in view.caption.text())
        good = finite[~bad]
        assert f"from {good.min():.4g} to {good.max():.4g}" in view.caption.text()
        atoms = next(c for c in view.ax.collections
                     if isinstance(c, structure_tools.DataCircles) and c.get_zorder() == 4)
        colours = [to_hex(c) for c in atoms.get_facecolors()]
        assert [c == theme.MUTED for c in colours] == bad.tolist()
        assert len(set(colours)) > 2                           # the finite ones differ
        bar = view.figure.axes[1]                               # on the finite scale
        assert np.allclose(sorted(np.abs(bar.get_ylim())), [np.abs(good).max()] * 2)
    window.set_canvas_view("structure")
