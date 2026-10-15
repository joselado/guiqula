"""Variants in the window: a second Hamiltonian linked into a calculation's
input, or a second geometry into a Hamiltonian's, in the node view; the
results of every input in one grid, Run running them together, the tree
saying what a variant is, and a further input taken away."""
import pytest
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from guiqula.core.document import variants_of
from guiqula.session import Session
from guiqula.ui.app import build_main_window
from guiqula.ui.properties import EntryForm


@pytest.fixture
def two(qapp, no_jobs):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session(jobs=no_jobs)
    session.do("add_system", lattice="honeycomb_lattice")
    window.attach(session)
    session.do("add_system", lattice="honeycomb_lattice")
    session.do("add_term", system="s2", kind="sublattice_imbalance", params={"mass": 0.3})
    session.do("add_calculation", system="s1", kind="dos", params={"ne": 20})
    session.act("outliner_view", name="nodes")
    yield window, session
    window.close()
    session.close()


def drag(view, start, end, modifier=Qt.KeyboardModifier.NoModifier):
    viewport = view.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, modifier, start)
    for t in (0.5, 1.0):
        QTest.mouseMove(viewport, QPoint(int(start.x() + t * (end.x() - start.x())),
                                         int(start.y() + t * (end.y() - start.y()))))
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, modifier, end)


def test_a_second_hamiltonian_into_a_calculation(two):
    window, session = two
    view = window.node_view
    view.resetTransform()
    view.centerOn(view.node_items["s2"])
    drag(view, view.socket_point("s2"), view.socket_point("c1", "target"))
    variant = variants_of(session.document, "c1")
    assert len(variant) == 1 and session.document.calculation(variant[0]).system == "s2"
    assert session.document.calculation("c1").system == "s1"      # the first input stays
    grid = window.variant_grids["c1"]
    assert window.current_tab() == f"grid:{grid}"                 # both results, side by side
    assert {calc for calc in window.grids[grid].placed().values()} == {"c1", variant[0]}
    assert len([l for l in view.link_items if l.link.target == "c1"
                and l.link.socket == "target"]) == 2
    window.select(variant[0])                                     # the tree and the form
    assert "variant of c1" in window.outliner.item(variant[0]).text(0)
    form = window.properties.form
    assert isinstance(form, EntryForm) and form.editors["ne"].value() == 20   # c1's
    assert form.findChild(QLabel, "variantNote") is not None
    asked = []
    act = window._act
    window._act = lambda name, **args: asked.append((name, args)) if name == \
        "run_calculation" else act(name, **args)
    window.run_guarded("c1", confirmed=True)                       # Run runs both
    assert [args["calculation"] for _, args in asked] == ["c1", variant[0]]
    window._act = act
    session.act("node_cut", node="c1", socket="target", source="s2")
    assert variants_of(session.document, "c1") == []


def test_ctrl_while_dropping_moves_the_input(two):
    window, session = two
    view = window.node_view
    view.resetTransform()
    view.centerOn(view.node_items["s2"])
    drag(view, view.socket_point("s2"), view.socket_point("c1", "target"),
         Qt.KeyboardModifier.ControlModifier)
    assert session.document.calculation("c1").system == "s2"
    assert variants_of(session.document, "c1") == []


def test_a_second_geometry_into_a_hamiltonian(two):
    window, session = two
    geometry = session.do("add_geometry", lattice="honeycomb_lattice")
    session.do("add_geometry_op", system=geometry, kind="supercell", params={"n": [2, 2, 1]})
    session.act("node_connect", source=geometry, target="s1", socket="geometry")
    system = next(s for s in session.document.systems if s.variant_of == "s1")
    follow = variants_of(session.document, "c1")
    assert [session.document.calculation(v).system for v in follow] == [system.id]
    assert window.current_tab() == f"grid:{window.variant_grids['c1']}"
    assert window.outliner.item(f"{system.id}/hamiltonian").text(0) == "Hamiltonian of s1"
    window.select(system.id)                                      # its form shows s1's
    assert window.properties.form.has_spin.currentData() is True
    assert system.id not in window.node_view.node_items           # drawn into s1's socket


def test_a_calculation_added_on_a_variant_goes_to_its_original(two):
    window, session = two
    geometry = session.do("add_geometry", lattice="square_lattice")
    session.do("add_variant", entry="s1", target=geometry)
    variant = variants_of(session.document, "s1")[0]
    window.select(variant)
    calc = window.add_calculation("dos")       # decision 262: never on the variant
    assert session.document.calculation(calc).system == "s1"
    assert [session.document.calculation(c).system
            for c in variants_of(session.document, calc)] == [variant]


def test_a_redone_variant_comes_back_into_its_grid(two):
    """Redo of a link that added a variant shows the variant's result in the
    grid of its original again, as the link did (decision 261)."""
    window, session = two
    session.act("node_connect", source="s2", target="c1", socket="target")
    grid = window.variant_grids["c1"]
    session.act("undo")
    assert variants_of(session.document, "c1") == []
    session.act("redo")
    variant = variants_of(session.document, "c1")
    assert len(variant) == 1 and variant[0] in window.plots
    assert set(window.grids[grid].placed().values()) == {"c1", variant[0]}
