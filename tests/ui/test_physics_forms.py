"""Forms that read as physics (PLAN.md phase 8, package P6): the kind menu
of a Field shows its kind and opens the panel of that kind only; a
parameter's label attaches a slider over a range taken from its value and
adds a sweep over it; a term without regions says where it acts, with the
link to the Regions menu; the system form speaks of spin, superconductivity,
the hopping range and sparse matrices; the mean field folds the further
neighbours."""
import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QLabel

from guiqula.session import Session
from guiqula.ui.app import build_main_window
from guiqula.ui.forms import FIELD_HELP, FIELD_LINE
from guiqula.ui.properties import sweep_target
from guiqula.ui.sliders import range_from


@pytest.fixture
def still(qapp, no_jobs):
    """A window over a session that runs nothing."""
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session("honeycomb_zeeman_rashba", jobs=no_jobs)
    window.attach(session)
    yield window, session
    window.close()
    session.close()


def test_the_range_of_a_slider_comes_from_the_value():
    assert range_from(0.1) == (0.0, 0.2)
    assert range_from(-0.5) == (-1.0, 0.0)               # ordered
    assert range_from(0.0) == (-1.0, 1.0)                # zero: around it
    assert range_from(0.5, 0.0, 1.0) == (0.0, 1.0)       # a filling stays a filling
    assert range_from(0.8, 0.0, 1.0) == (0.0, 1.0)
    assert range_from(0.0, minimum=0.0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        range_from(float("nan"))


def test_the_kind_menu_shows_the_kind_and_opens_its_panel(still, qtbot):
    window, session = still
    window.select("t2")

    def editor():
        return window.properties.form.editors["c"]

    def stored():
        return session.document.find("t2")[-1].params["c"]

    assert editor().findChild(QComboBox, "fieldKindBox_c") is None      # the combo is gone
    names = [a.objectName() for a in editor().kind_menu.actions()]
    assert names == [f"fieldKind_c_{kind}" for kind in (
        "constant", "expression", "piecewise", "profile", "interpolated", "painted",
        "from_result")]
    assert all(a.toolTip() for a in editor().kind_menu.actions())
    assert editor().button.text() == "f(r)" and editor().kind_actions["constant"].isChecked()
    assert not editor().panel.isVisible()
    menu = editor().button.menu()
    editor().button.click()                         # opens with popup(): the click returns
    qtbot.waitUntil(menu.isVisible)
    menu.close()

    menu.findChild(QAction, "fieldKind_c_expression").trigger()   # a number stays a number
    assert stored() == 0.1
    assert editor().panel.isVisible() and editor().help.isVisible()
    assert editor().help.text() == FIELD_LINE and editor().help.toolTip() == FIELD_HELP
    assert not editor().pieces.isVisible() and not editor().profile_box.isVisible()
    editor().edit.setText("0.1*tanh(x)")
    editor().edit.editingFinished.emit()
    assert stored() == "0.1*tanh(x)" and editor().button.text() == "expression"
    assert editor().button.font().bold() and editor().kind_actions["expression"].isChecked()

    shown = {"profile": "profile_box", "interpolated": "points_box", "painted": "paint_box",
             "piecewise": "pieces"}
    for kind, box in shown.items():
        editor().kind_actions[kind].trigger()
        assert stored()["kind"] == kind and editor().button.text() == kind
        assert editor().panel.isVisible() and getattr(editor(), box).isVisible()
        assert [name for name, other in shown.items()
                if getattr(editor(), other).isVisible()] == [kind], kind
        assert not editor().help.isVisible()

    editor().kind_actions["profile"].trigger()
    editor().kind_actions["expression"].trigger()    # a profile becomes its formula
    assert isinstance(stored(), str) and "exp" in stored()
    assert editor().button.text() == "expression"
    editor().kind_actions["constant"].trigger()
    assert stored() == 0.0 and not editor().panel.isVisible()
    assert editor().button.text() == "f(r)"
    editor().kind_actions["from_result"].trigger()  # nothing to read: said, value kept
    assert stored() == 0.0 and editor().no_results.isVisible()


def test_the_label_menu_attaches_a_slider_and_adds_a_sweep(still):
    window, session = still
    window.select("t2")
    form = window.properties.form
    assert "parameter c" in form.labels["c"].toolTip()
    assert "right-click" in form.labels["c"].toolTip()
    menu = form.label_menu("c")
    assert menu.objectName() == "paramMenu_c"
    assert [a.objectName() for a in menu.actions()] == [
        "lockParam_c", "attachSlider_c", "sweepParam_c", "previewField_c"]
    assert all(a.toolTip() for a in menu.actions())
    menu.findChild(QAction, "attachSlider_c").trigger()
    menu.close()
    assert window.sliders[-1] == {"entry": "t2", "param": "c", "component": None,
                                  "min": 0.0, "max": 0.2}
    assert window.docks["slidersDock"].isVisible()

    window.select("t1")                              # a vector: one item per component
    form = window.properties.form
    menu = form.label_menu("m")
    slider_menu = menu.findChild(type(menu), "attachSliderMenu_m")
    assert [a.objectName() for a in slider_menu.actions()] == [
        "attachSlider_m_x", "attachSlider_m_y", "attachSlider_m_z"]
    z = slider_menu.actions()[2]
    assert not z.isEnabled() and "no number" in z.toolTip()     # an expression: no range
    slider_menu.actions()[0].trigger()                           # zero: -1 to 1
    menu.close()
    assert window.sliders[-1] == {"entry": "t1", "param": "m", "component": 0,
                                  "min": -1.0, "max": 1.0}

    window.select("t2")
    before = [c.id for c in session.document.calculations]
    menu = window.properties.form.label_menu("c")
    menu.findChild(QAction, "sweepParam_c").trigger()
    menu.close()
    sweep = next(c for c in session.document.calculations if c.id not in before)
    assert sweep.kind == "sweep" and sweep.system == "s1" and window.selected == sweep.id
    assert {k: sweep.params[k] for k in ("calculation", "entry", "param", "component",
                                         "start", "stop", "steps")} == {
        "calculation": "c1", "entry": "t2", "param": "c", "component": None,
        "start": 0.0, "stop": 0.2, "steps": 11}
    assert session.plan_calculation(sweep.id).problem is None
    assert window.workspace == "calculate"

    window.select("t2")
    menu = window.properties.form.label_menu("c")
    menu.findChild(QAction, "previewField_c").trigger()
    menu.close()
    assert window.canvas_view == "field" and window.field_preview == ("t2", "c")


def test_a_sweep_needs_a_calculation_to_run(still):
    """A system without a calculation: Sweep this parameter is disabled and
    says what to do, and nothing is added; the slider is still offered."""
    window, session = still
    s2 = session.do("add_system", lattice="square_lattice")
    term = session.do("add_term", system=s2, kind="onsite", params={"mu": 0.2})
    window.select(term)
    form = window.properties.form
    menu = form.label_menu("mu")
    sweep = menu.findChild(QAction, "sweepParam_mu")
    assert not sweep.isEnabled() and "add one first" in sweep.toolTip()
    assert menu.findChild(QAction, "attachSlider_mu").isEnabled()
    menu.close()
    before = len(session.document.calculations)
    assert form.sweep("mu") is None and "has no calculation" in form.error.text()
    assert len(session.document.calculations) == before


def test_the_mean_field_slides_and_sweeps_within_its_bounds(qapp, no_jobs):
    """The filling, bounded by 0 and 1, takes 0 to 1 (not 0 to twice
    0.5... which is the same) and U takes 0 to twice its value; the sweep of
    the filling is a valid one. The further neighbours are folded until one
    is set; unchecking the group sets them to zero in one undo step."""
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session("honeycomb_hubbard", jobs=no_jobs)
    window.attach(session)
    try:
        window.select("s1/meanfield")
        form = window.properties.form
        assert form.slider_range("U") == (0.0, 2 * session.document.system("s1").hamiltonian
                                          .meanfield.params["U"])
        session.do("set_meanfield", system="s1", params={"filling": 0.8})
        form = window.properties.form
        assert form.slider_range("filling") == (0.0, 1.0)
        sweep = form.sweep("filling")
        assert session.plan_calculation(sweep).problem is None
        assert session.document.calculation(sweep).params["stop"] == 1.0

        window.select("s1/meanfield")
        form = window.properties.form
        group = form.further
        assert group.objectName() == "furtherNeighbours" and group.text() == "further neighbours"
        assert not group.isChecked() and not form.further_rows.isVisible()
        assert set(form.editors) >= {"V2", "V3", "J2", "J3"}
        assert form.editors["V2"].parentWidget() is form.further_rows
        assert form.rows.indexOf(form.labels["J1"]) < form.rows.indexOf(group) < \
            form.rows.indexOf(form.labels["fix"])          # after the first neighbours
        group.setChecked(True)                       # unfolds, changes nothing
        assert form.further_rows.isVisible()
        form.editors["V2"].edit.setText("0.2")
        form.editors["V2"].edit.editingFinished.emit()
        assert session.document.system("s1").hamiltonian.meanfield.params["V2"] == 0.2
        steps = len(session.dispatcher.history()["undo"])
        group.setChecked(False)                      # zero, folded, one step
        params = session.document.system("s1").hamiltonian.meanfield.params
        assert params["V2"] == 0.0 and not form.further_rows.isVisible()
        assert len(session.dispatcher.history()["undo"]) == steps + 1
        session.undo()
        form = window.properties.form
        assert form.further.isChecked() and form.further_rows.isVisible()
        assert form.editors["V2"].value() == 0.2
    finally:
        window.close()
        session.close()


def test_the_region_link_appears_only_without_regions(still, qtbot):
    window, session = still
    window.select("t2")
    form = window.properties.form
    assert form.region is None
    link = form.findChild(QLabel, "regionLink")
    assert link is not None and "acts everywhere" in link.text()
    assert "restrict to a region" in link.text() and link.toolTip()
    link.linkActivated.emit("#regions")              # the Regions menu of s1 (P2's "+")
    qtbot.waitUntil(window.regions_menu.isVisible)
    assert window.regions_system == "s1"
    window.regions_menu.close()
    session.do("add_region", system="s1", name="right",
               select={"kind": "expression", "expr": "x > 0"})
    window.select("t2")
    form = window.properties.form
    assert form.findChild(QLabel, "regionLink") is None
    assert form.region is not None and form.region.objectName() == "regionBox"
    assert form.rows.labelForField(form.region).text() == "region"


def test_the_system_form_speaks_the_physics(still):
    window, session = still
    window.select("s1")
    form = window.properties.form
    labels = {name: form.findChild(QLabel, f"constructionLabel_{name}").text()
              for name in ("has_spin", "nambu", "tij", "is_sparse")}
    assert labels == {"has_spin": "spin", "nambu": "superconducting (Nambu)",
                      "tij": "hopping range (neighbours)",
                      "is_sparse": "sparse matrices (large systems)"}
    spin = form.has_spin
    assert isinstance(spin, QComboBox) and spin.objectName() == "construction_has_spin"
    assert [spin.itemText(i) for i in range(spin.count())] == ["spinless", "spinful"]
    assert spin.currentText() == "spinful"
    for widget, words in ((spin, ("has_spin", "Zeeman", "whatever is chosen here")),
                          (form.nambu, ("nambu", "pairing", "without one")),
                          (form.tij, ("tij", "second-neighbour")),
                          (form.sparse, ("is_sparse", "sparse"))):
        assert all(w in widget.toolTip() for w in words), widget.objectName()
    spin.setCurrentIndex(0)
    spin.activated.emit(0)
    assert session.document.system("s1").hamiltonian.construction.has_spin is False
    session.undo()
    assert window.properties.form.has_spin.currentText() == "spinful"
    form = window.properties.form
    form.tij.setText("1, x")
    form.tij.editingFinished.emit()
    assert form.error.text().startswith("hopping range:")


def test_the_kind_buttons_of_a_vector_line_up(still, qtbot):
    """The components' boxes line up whatever kind each button says: the
    buttons are as wide as the widest, and narrow again with it."""
    window, session = still
    window.select("t1")                          # mz is an expression, mx and my numbers

    def widths():
        editor = window.properties.form.editors["m"]
        return [c.button.width() for c in editor.components], \
            [c.edit.width() for c in editor.components]

    buttons, boxes = widths()
    assert window.properties.form.editors["m"].components[2].button.text() == "expression"
    assert len(set(buttons)) == 1 and len(set(boxes)) == 1, (buttons, boxes)
    session.do("set_param", entry="t1", name="m", value=[0.0, 0.0, 0.3])
    qtbot.waitUntil(lambda: widths()[0][2] < buttons[2])     # f(r) everywhere: narrow again
    narrow, boxes = widths()
    assert len(set(narrow)) == 1 and len(set(boxes)) == 1, (narrow, boxes)


def test_the_numbers_of_a_sweep_are_neither_slid_nor_swept(still):
    """A sweep's own range is read by no calculation, so its label menu
    offers the lock only, and Form.sweep and attach_slider refuse."""
    window, session = still
    window.select("t2")
    sweep = window.properties.form.sweep("c")
    form = window.properties.form
    assert form.item_id == sweep
    menu = form.label_menu("start")
    assert [a.objectName() for a in menu.actions()] == ["lockParam_start"]
    menu.close()
    assert "parameter start; right-click to lock it" in form.labels["start"].toolTip()
    before = len(session.document.calculations)
    assert form.sweep("start") is None and "no calculation reads" in form.error.text()
    assert form.attach_slider("stop") is None and window.sliders == []
    assert len(session.document.calculations) == before


def test_a_sweep_runs_a_calculation_that_gives_numbers(qapp, no_jobs):
    """Nothing has run yet: the sweep runs the gap, which is declared to
    give numbers, rather than the band structure listed first; where no
    calculation is known to give one, the tooltip says so."""
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session("graphene_basics", jobs=no_jobs)
    window.attach(session)
    try:
        kinds = {c.id: c.kind for c in session.document.calculations}
        assert kinds["c1"] == "bands" and kinds["c3"] == "gap"
        assert sweep_target(session, "s1", "t1") == "c3"
        window.select("t1")
        menu = window.properties.form.label_menu("mass")
        tip = menu.findChild(QAction, "sweepParam_mass").toolTip()
        assert "each running c3 and collecting the numbers it gives" in tip
        menu.close()
        sweep = window.properties.form.sweep("mass")
        assert session.document.calculation(sweep).params["calculation"] == "c3"
        assert session.plan_calculation(sweep).problem is None
    finally:
        window.close()
        session.close()

    window = build_main_window()
    window.show()
    session = Session("honeycomb_zeeman_rashba", jobs=no_jobs)
    window.attach(session)
    try:
        window.select("t2")                      # a band structure and a DOS: no number yet
        menu = window.properties.form.label_menu("c")
        tip = menu.findChild(QAction, "sweepParam_c").toolTip()
        assert "each running c1, which has given no number to collect so far" in tip
        menu.close()
    finally:
        window.close()
        session.close()
