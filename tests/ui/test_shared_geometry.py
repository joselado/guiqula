"""A geometry shared by two systems in the window (PLAN.md phase 9, part B):
the Geometry row of each says so, the first system shows its ops and
regions by their ids and the later one as linked rows that select the same
entry under it, an op's form covers the locks of every system on it, and
the context menu of a system gives New Hamiltonian on this geometry and
Duplicate linked."""
import pytest

from guiqula.session import Session
from guiqula.ui.app import build_main_window
from guiqula.ui.properties import EntryForm, GeometryForm, RegionForm


@pytest.fixture
def shared(qapp, no_jobs):
    """A honeycomb supercell (s1) with a region, and a second Hamiltonian on
    its geometry (s2)."""
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session(jobs=no_jobs)
    session.do("add_system", lattice="honeycomb_lattice")
    window.attach(session)
    session.do("add_geometry_op", system="s1", kind="supercell", params={"n": [2, 2, 1]})
    session.do("add_region", system="s1", select={"kind": "expression", "expr": "x < 0"},
               name="left")
    session.do("duplicate_linked", system="s1")
    yield window, session
    window.close()
    session.close()


def test_both_systems_show_the_shared_geometry(shared):
    window, session = shared
    outliner = window.outliner
    assert outliner.item("s1/geometry").text(0) == "Geometry geo1 · shared with s2"
    assert outliner.item("s2/geometry").text(0) == "Geometry geo1 · shared with s1"
    assert outliner.item("op1") is not None and outliner.item("s2/op1") is not None
    assert outliner.item("r1") is not None and outliner.item("s2/r1") is not None
    window.select("s2/op1")                    # the same op, under the second system
    assert window.selected == "op1" and window.context == "s2"
    assert window.current_system() == "s2" and outliner.current_id() == "s2/op1"
    form = window.properties.form
    assert isinstance(form, EntryForm) and form.system_id == "s2"
    assert {"s1", "s1/geometry", "s2", "s2/geometry"} <= set(form.whole_locks())
    window.select("op1")
    assert window.context is None and window.current_system() == "s1"
    window.select("s2/r1")
    assert isinstance(window.properties.form, RegionForm)
    assert window.properties.form.system_id == "s2"


def test_an_edit_under_one_system_is_an_edit_of_both(shared):
    window, session = shared
    window.select("s2/op1")
    session.do("set_param", entry="op1", name="n", value=[3, 3, 1])
    assert session.document.geometry("geo1").ops[0].params["n"] == [3, 3, 1]
    assert window.selected == "op1"            # the form follows the same entry
    window.outliner.setCurrentItem(window.outliner.item("s2/op1"))
    window.outliner.delete_current()
    assert session.document.geometry("geo1").ops == []


def test_the_context_menu_shares_a_geometry(shared, qtbot):
    window, session = shared
    window.outliner.setCurrentItem(window.outliner.item("s1"))
    window.outliner.duplicate_linked_current()
    qtbot.waitUntil(lambda: len(session.document.systems) == 3)
    assert session.document.systems_on("geo1") == ["s1", "s3", "s2"] or \
        set(session.document.systems_on("geo1")) == {"s1", "s2", "s3"}
    window.select("s1")
    session.do("add_system", geometry="geo1")  # New Hamiltonian on this geometry
    assert len(session.document.systems_on("geo1")) == 4
    window.select("geo1")
    assert isinstance(window.properties.form, GeometryForm)
    assert "s1" in window.properties.form.users.text()
