"""The junction in the window (PLAN.md phase 9, part D): its row in the
outliner with a row for each of its systems, its form, New junction with
this lead in a system's context menu, the Junction group of the Add menu
while it is selected, its node in the node view."""
import pytest

from guiqula.session import Session
from guiqula.ui.app import build_main_window
from guiqula.ui.properties import JunctionForm

PREFIX = "addCalc"                  # the objectName of an entry of the Add menu


@pytest.fixture
def junction(qapp, no_jobs):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session(jobs=no_jobs)
    session.do("add_system", lattice="chain")
    window.attach(session)
    window._outliner_command("add_junction", {"left": "s1"})       # the context menu's
    yield window, session
    window.close()
    session.close()


def test_the_outliner_and_the_form(junction):
    window, session = junction
    assert window.selected == "j1"                     # the new junction is selected
    outliner = window.outliner
    assert outliner.item("j1").text(1) == "s1 to s2"
    assert outliner.item("j1/left").text(0).startswith("Left lead  s1")
    window.select("j1/right")                          # a row selects its system
    assert window.selected == "s2" and window.current_system() == "s2"
    window.select("j1")
    form = window.properties.form
    assert isinstance(form, JunctionForm) and window.current_target() == "j1"
    central = form.boxes["central"]
    assert central.currentData() is None
    dot = session.do("add_system", lattice="chain", name="dot")
    window.select("j1")
    form = window.properties.form
    form.boxes["central"].setCurrentIndex(form.boxes["central"].findData(dot))
    form.boxes["central"].activated.emit(form.boxes["central"].currentIndex())
    assert session.document.junction("j1").central == dot
    assert window.current_system() == dot              # the canvas: the central region


def test_the_add_menu_lists_the_junction_calculations(junction):
    window, session = junction
    window.select("j1")
    found = window.open_add_menu("calculations")
    window.palette_menus["calculation"].hide()
    listed = set(found["entries"])
    assert {f"{PREFIX}_{kind}" for kind in ("junction_didv", "junction_transmission",
                                             "junction_iv")} <= listed
    assert f"{PREFIX}_bands" not in listed           # a system's calculations are not offered
    calc = session.do("add_calculation", system="j1", kind="junction_didv")
    window.select(calc)
    assert window.current_target() == "j1"


def test_the_junction_node(junction):
    window, session = junction
    session.act("outliner_view", name="nodes")
    assert window.node_view.node_items["j1"].node.kind == "junction"
    links = {(l.link.source, l.link.target, l.link.socket) for l in window.node_view.link_items}
    assert {("s1", "j1", "left"), ("s2", "j1", "right")} <= links
