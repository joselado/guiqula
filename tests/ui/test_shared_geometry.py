"""A geometry as an object in the window (PLAN.md phase 9, part B and
decisions 273 to 275): the Geometries section lists it once with its
lattice, ops and regions, the Geometry row of each system names it and
selects it with that system as the context, its form holds the lattice and
the systems built on it while the system's form holds a combo of the
geometries, an op's form covers the locks of every system on it, and the
context menus give New Hamiltonian on this geometry and Duplicate linked."""
import pytest

from guiqula.session import Session
from guiqula.ui.app import build_main_window
from guiqula.ui.properties import EntryForm, GeometryForm, RegionForm, SystemForm


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


def test_the_geometry_is_listed_once_and_each_system_links_to_it(shared):
    window, session = shared
    outliner = window.outliner
    ids = [outliner.topLevelItem(i).data(0, 0x0100) for i in range(outliner.topLevelItemCount())]
    assert ids[:3] == ["geometries", "s1", "s2"]            # the geometries come first, once
    assert ids.count("geometries") == 1
    geometry = outliner.item("geo1")
    assert geometry.text(0) == "geo1  Honeycomb lattice · 1 op" and geometry.text(1) == "s1, s2"
    assert outliner.item("geo1/base").text(0) == "Honeycomb lattice"
    assert outliner.item("op1").parent() is geometry                # once, under the geometry
    assert outliner.item("r1").parent() is outliner.item("geo1/regions")
    assert outliner.item("s2/op1") is None and outliner.item("s2/r1") is None
    assert outliner.item("s1/geometry").text(0) == \
        "Geometry geo1 · Honeycomb lattice · 1 op · shared with s2"
    assert outliner.item("s2/geometry").text(0) == \
        "Geometry geo1 · Honeycomb lattice · 1 op · shared with s1"
    assert outliner.item("s1/geometry").childCount() == 0
    assert outliner.item("s1/base") is None and outliner.item("s1/regions") is None
    for path in ("geometries", "geo1/ops", "geo1/regions", "s1/hamiltonian"):
        assert outliner.add_button(path) is not None, path
    assert outliner.add_button("s1/geometry") is None


def test_the_geometry_row_of_a_system_selects_the_geometry_under_it(shared):
    window, session = shared
    window.select("s2/geometry")               # the link row: the geometry, s2 on the canvas
    assert window.selected == "geo1" and window.context == "s2"
    assert window.current_system() == "s2" and window.outliner.current_id() == "s2/geometry"
    form = window.properties.form
    assert isinstance(form, GeometryForm) and form.lattice.currentData() == "honeycomb_lattice"
    assert form.users.text() == "s1, s2"
    assert {"geo1", "s1", "s1/geometry", "s2", "s2/geometry"} <= set(form.whole_locks())
    window.select("geo1")                      # its own row: the first system on the canvas
    assert window.context is None and window.current_system() == "s1"
    assert window.outliner.current_id() == "geo1"
    assert isinstance(window.properties.form, GeometryForm)
    window.select("geo1/base")
    assert isinstance(window.properties.form, GeometryForm) and window.workspace == "geometry"
    window.select("s1/base")                   # the rows of before name the geometry's
    assert window.selected == "geo1/base"
    window.select("s2/regions")
    assert window.selected == "geo1/regions" and window.context is None
    window.select("r1")
    assert isinstance(window.properties.form, RegionForm)
    assert window.properties.form.system_id == "s1"
    window.select("op1")
    form = window.properties.form
    assert isinstance(form, EntryForm) and form.system_id == "s1"
    assert {"s1", "s1/geometry", "s2", "s2/geometry"} <= set(form.whole_locks())


def test_the_forms_edit_the_geometry_and_move_a_system(shared):
    window, session = shared
    window.select("s1")
    form = window.properties.form
    assert isinstance(form, SystemForm) and not hasattr(form, "lattice")
    assert form.geometry.currentData() == "geo1"
    assert form.geometry.itemText(0) == "geo1 · Honeycomb lattice · 1 op · s1, s2"
    geometry = session.do("add_geometry", lattice="square_lattice")
    assert form.geometry.count() == 2                       # the combo follows the document
    form.geometry.setCurrentIndex(form.geometry.findData(geometry))
    form.geometry.activated.emit(form.geometry.currentIndex())
    assert session.document.system("s1").geometry == geometry
    assert window.outliner.item("s1/geometry").text(0) == "Geometry geo2 · Square lattice"
    assert window.outliner.item("geo1").text(1) == "s2"
    session.undo()
    window.select("geo1")
    form = window.properties.form
    form.lattice.setCurrentIndex(form.lattice.findData("honeycomb_zigzag_ribbon"))
    form.lattice.activated.emit(form.lattice.currentIndex())
    assert session.document.geometry("geo1").base.kind == "honeycomb_zigzag_ribbon"
    form = window.properties.form                            # rebuilt with the new parameters
    assert isinstance(form, GeometryForm) and form.editors["width"].value() == 10
    form.editors["width"].spin.setValue(4)
    assert session.document.geometry("geo1").base.params == {"width": 4}
    session.do("lock", target="s2.width")                    # a system's lock of the lattice
    assert not form.editors["width"].isEnabled()
    assert "s2.width" in form.labels["width"].toolTip()


def test_an_edit_under_the_geometry_is_an_edit_of_both(shared):
    window, session = shared
    window.select("s2/geometry")
    session.do("set_param", entry="op1", name="n", value=[3, 3, 1])
    assert session.document.geometry("geo1").ops[0].params["n"] == [3, 3, 1]
    assert window.selected == "geo1"             # the form follows the same geometry
    window.outliner.setCurrentItem(window.outliner.item("op1"))
    window.outliner.delete_current()
    assert session.document.geometry("geo1").ops == []


def test_the_context_menu_shares_a_geometry(shared, qtbot):
    window, session = shared
    window.outliner.setCurrentItem(window.outliner.item("s1"))
    window.outliner.duplicate_linked_current()
    qtbot.waitUntil(lambda: len(session.document.systems) == 3)
    assert set(session.document.systems_on("geo1")) == {"s1", "s2", "s3"}
    window.select("geo1")
    session.do("add_system", geometry="geo1")  # New Hamiltonian on this geometry
    assert len(session.document.systems_on("geo1")) == 4
    assert "s1" in window.properties.form.users.text()
    unused = session.do("add_geometry", lattice="kagome_lattice")
    assert window.outliner.item(unused).text(1) == "unused"
    window.select(unused)
    assert isinstance(window.properties.form, GeometryForm)
    assert window.current_system() == "s1"                  # the canvas keeps a system
    assert window.properties.form.users.text() == "nothing: removing it loses nothing"
