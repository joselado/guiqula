"""Classical systems in the window (decision 13.5): made from the Geometry
toolbar, a Model branch in the outliner with a form for its set-up, the
palettes offering the terms and calculations of the kind of the current
system, and a result drawn on the structure."""
import pytest
from PySide6.QtGui import QAction

from guiqula.ui.app import build_main_window
from guiqula.ui.properties import ModelForm


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


def menu_kinds(window, family, prefix):
    menu = window.palette_menu(family)
    return {a.objectName()[len(prefix) + 1:] for a in menu.actions()
            if a.objectName().startswith(prefix + "_") and a.isVisible()}


def test_a_classical_system_in_the_window(window, qtbot, shot):
    session = window.session
    settle(qtbot, window)
    assert "zeeman" in menu_kinds(window, "term", "addTerm")
    menu = window.palette_menu("lattice")                  # New system, its last section
    next(a for a in menu.actions() if a.objectName() == "newClassical_ising").trigger()
    system = window.selected
    assert session.document.system(system).kind == "ising"
    assert window.workspace_tabs.tabText(1) == "Model"
    terms = menu_kinds(window, "term", "addTerm")
    assert terms == {"ising_interaction", "ising_field", "python"}
    assert menu_kinds(window, "calculation", "addCalc") == {"anneal_ising", "python", "sweep"}
    assert not window.palette_menu("term").findChild(QAction, "addMeanfield").isVisible()
    window.palette_menu("term").search.setText("interaction")
    window.palette_menu("term").search.returnPressed.emit()
    term = window.selected
    assert session.document.find(term)[-1].kind == "ising_interaction"
    window.select(f"{system}/model")
    assert isinstance(window.properties.form, ModelForm)
    window.properties.form.editors["m"].edit.setText("1")
    window.properties.form.editors["m"].edit.editingFinished.emit()
    assert session.document.system(system).model.params["m"] == 1.0
    settle(qtbot, window)
    build = window.builds[system]
    assert build["sites"] == 64 and build["mode"] == "Ising"
    assert window.outliner.item(f"{system}/model") is not None
    calc = window.add_calculation("anneal_ising")
    session.do("set_params", entry=calc, params={"ntries": 500, "temperatures": 2})
    session.run_calculation(calc, wait=True, timeout=300)
    window.show_result(calc)
    qtbot.waitUntil(lambda: window.plots[calc].result is not None, timeout=10_000)
    assert window.plots[calc].result.plot["kind"] == "structure_scalar"
    shot(window, "ising")
    window.select(system)                                  # the Geometry workspace
    window.set_canvas_view("hamiltonian")
    assert "classical system has no Hamiltonian" in window.structure.caption.text()
    window.set_canvas_view("structure")
    window.select("s1")                                    # back to the quantum system
    assert window.workspace_tabs.tabText(1) == "Hamiltonian"
    assert "zeeman" in menu_kinds(window, "term", "addTerm")


def test_a_texture_feeds_an_exchange_field(window, qtbot, shot):
    """The Field editor reads a result of another system (from_result):
    the classical texture becomes the exchange field of the electrons."""
    session = window.session
    session.act("new")
    spins = window.new_classical_system("classical_spin")
    session.do("add_term", system=spins, kind="heisenberg", params={"J1": -1.0})
    session.do("add_term", system=spins, kind="spin_field", params={"b": ["0.5*tanh(x)", 0, 0.2]})
    texture = session.do("add_calculation", system=spins, kind="minimize_spins",
                         params={"tries": 2})
    electrons = session.do("add_system", lattice="triangular_lattice")
    session.do("add_geometry_op", system=electrons, kind="supercell", params={"n": [3, 3, 1]})
    term = session.do("add_term", system=electrons, kind="zeeman", params={"m": [0, 0, 0]})
    window.select(term)
    editor = window.properties.form.editors["m"].components[2]     # mz
    editor.open_panel()
    assert editor.kind_actions["from_result"].objectName() == "fieldKind_m_z_from_result"
    editor.choose_kind("from_result")             # no result yet: nothing to read
    assert session.document.find(term)[-1].params["m"][2] == 0.0
    assert editor.no_results.isVisible() and editor.button.text() == "f(r)"
    session.run_calculation(texture, wait=True, timeout=300)
    qtbot.waitUntil(lambda: session.result(texture) is not None, timeout=10_000)
    window.select("")
    window.select(term)
    editor = window.properties.form.editors["m"].components[2]
    assert editor.result_calc.findData(texture) >= 0
    editor.choose_kind("from_result")
    value = session.document.find(term)[-1].params["m"][2]
    assert value["kind"] == "from_result" and value["calculation"] == texture
    assert value["array"] == "magnetization" and value["component"] == 0
    editor = window.properties.form.editors["m"].components[2]
    editor.result_component.setCurrentIndex(editor.result_component.findData(2))
    editor.result_component.activated.emit(editor.result_component.currentIndex())
    editor.result_scale.setText("0.4")
    editor.result_scale.editingFinished.emit()
    value = session.document.find(term)[-1].params["m"][2]
    assert value["component"] == 2 and value["scale"] == 0.4
    settle(qtbot, window)
    report = next(r for r in window.builds[electrons]["reports"] if r["id"] == term)
    assert report["status"] == "ok"
    window.preview_field(term, "m")
    assert "from" in window.structure.caption.text()
    shot(window, "bridge")
    session.do("set_param", entry=texture, name="tries", value=3)   # the texture goes stale
    window.outliner.refresh(session)
    assert "stale result" in window.outliner.item(term).text(1)


def test_a_from_result_field_opens_before_its_result_exists(window, qtbot):
    """The form of a term whose Field reads a result not computed yet lists
    that calculation anyway (it raised a TypeError before)."""
    window.open_document("texture_exchange")
    settle(qtbot, window)
    window.select("t3")                              # m reads c1, which has not run
    editor = window.properties.form.editors["m"].components[0]
    assert editor.result_calc.itemData(editor.result_calc.currentIndex()) == "c1"
    assert window.properties.form.item_id == "t3"
