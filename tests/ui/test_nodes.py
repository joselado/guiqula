"""The node view (PLAN.md phase 9, part C): the Outliner dock's other view,
the nodes and links of the Document, a link drawn with the mouse as one
Command, the same edit made through the tree's form and through the nodes
giving the same Document, refusals said, places kept as view state."""
import json

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from guiqula.session import Session
from guiqula.ui.app import build_main_window


def make_window(qapp, no_jobs):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session(jobs=no_jobs)
    session.do("add_system", lattice="honeycomb_lattice")
    window.attach(session)
    session.do("add_calculation", system="s1", kind="bands")
    session.do("add_calculation", system="s1", kind="dos")
    session.do("add_kpath", vertices=["G", "K", "M", "G"])                 # k2, walked by none
    return window, session


@pytest.fixture
def nodes(qapp, no_jobs):
    window, session = make_window(qapp, no_jobs)
    yield window, session
    window.close()
    session.close()


def document_of(session):
    data = json.loads(session.document.to_json())
    data.pop("ui", None)
    return data


def drag(view, start, end):
    viewport = view.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for t in (0.25, 0.5, 0.75, 1.0):
        point = QPoint(int(start.x() + t * (end.x() - start.x())),
                       int(start.y() + t * (end.y() - start.y())))
        QTest.mouseMove(viewport, point)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       end)


def test_the_dock_shows_the_tree_or_the_nodes(nodes, shot, qtbot):
    window, session = nodes
    panel, view = window.outliner_panel, window.node_view
    assert panel.view() == "tree" and not view.isVisible()
    width = window.docks["outlinerDock"].width()
    assert session.act("outliner_view", name="nodes") == "nodes"
    assert panel.view() == "nodes" and view.isVisible()
    qtbot.waitUntil(lambda: window.docks["outlinerDock"].width() > width)   # widened
    assert set(view.node_items) == {"geo1", "k1", "k2", "s1", "c1", "c2"}
    styles = {(l.link.source, l.link.target, l.link.socket) for l in view.link_items}
    assert {("geo1", "s1", "geometry"), ("s1", "c1", "target"), ("k1", "c1", "kpath"),
            ("s1", "c2", "target")} <= styles
    assert view.node_items["s1"].node.title == "Hamiltonian"
    window.select("c2")                                          # the selection follows
    assert view.node_items["c2"].isSelected()
    view.node_items["c1"].setSelected(False)
    view.scene().clearSelection()
    view.node_items["s1"].setSelected(True)                      # and goes back to the tree
    assert window.selected == "s1" and window.outliner.current_id() == "s1"
    assert window.view_state()["outliner"] == "nodes"
    shot(window, "nodes")
    session.act("outliner_view", name="tree")
    assert panel.view() == "tree" and "outliner" not in window.view_state()


def test_a_link_drawn_with_the_mouse_is_one_command(nodes):
    window, session = nodes
    session.act("outliner_view", name="nodes")
    view = window.node_view
    view.resetTransform()                                       # one scene unit, one pixel
    view.centerOn(view.node_items["c1"])
    steps = len(session.dispatcher.history()["undo"])
    drag(view, view.socket_point("k2"), view.socket_point("c1", "kpath"))
    assert session.document.calculation("c1").params["kpath"] == "k2"
    assert len(session.dispatcher.history()["undo"]) == steps + 1          # one undo step
    assert ("k2", "c1", "kpath") in {(l.link.source, l.link.target, l.link.socket)
                                     for l in view.link_items}  # drawn again
    drag(view, view.socket_point("k2"), view.socket_point("c1", "target"))   # refused
    assert session.document.calculation("c1").system == "s1"
    assert "takes a system" in window.log.toPlainText()


def test_the_tree_and_the_nodes_make_the_same_document(qapp, no_jobs):
    """One edit, the k-path of the bands, made by the form's combo in one
    window and by a link in the node view of another: the two Documents are
    the same."""
    tree, tree_session = make_window(qapp, no_jobs)
    graph, graph_session = make_window(qapp, no_jobs)
    try:
        tree.select("c1")
        combo = tree.properties.form.editors["kpath"].combo
        combo.setCurrentIndex(combo.findData("k2"))
        combo.activated.emit(combo.currentIndex())
        graph_session.act("node_connect", source="k2", target="c1", socket="kpath")
        assert document_of(tree_session) == document_of(graph_session)
        assert tree_session.document.calculation("c1").params["kpath"] == "k2"
    finally:
        for window, session in ((tree, tree_session), (graph, graph_session)):
            window.close()
            session.close()


def test_places_are_view_state(nodes):
    window, session = nodes
    session.act("outliner_view", name="nodes")
    modified = session.modified
    session.act("node_move", node="s1", x=400, y=300)
    assert window.node_view.node_items["s1"].pos().x() == 400
    assert session.modified == modified                         # not a change of the document
    state = window.view_state()
    assert state["nodes"] == {"s1": [400.0, 300.0]}
    session.act("node_arrange")
    assert window.view_state().get("nodes") is None
    window.apply_view_state(state)
    assert window.node_view.node_items["s1"].pos().x() == 400


def test_a_double_click_opens_and_del_removes(nodes, qtbot):
    window, session = nodes
    session.act("outliner_view", name="nodes")
    view = window.node_view
    view.resetTransform()
    view.centerOn(view.node_items["k2"])
    point = view.mapFromScene(view.node_items["k2"].sceneBoundingRect().center())
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, point)
    assert "k2" in window.kpath_windows and window.kpath_windows["k2"].isVisible()
    window.kpath_windows["k2"].close()
    window.select("k2")
    view.setFocus()
    QTest.keyClick(view, Qt.Key.Key_Delete)
    qtbot.waitUntil(lambda: all(k.id != "k2" for k in session.document.kpaths))
    window.select("k1")
    QTest.keyClick(view, Qt.Key.Key_Delete)                    # walked by c1: refused
    assert any(k.id == "k1" for k in session.document.kpaths)


def test_the_forms_leave_the_variants_out(nodes):
    """A variant is no node of its own (decision 262): the forms that name a
    system, an embedding's and a junction's combos and a tip's, do not offer
    it, since the node view would draw that input linked to nothing."""
    from PySide6.QtWidgets import QComboBox
    window, session = nodes
    variant = session.do("add_variant", entry="s1",
                         target=session.do("add_geometry", lattice="honeycomb_lattice"))
    session.do("add_embedding", pristine="s1")
    session.do("add_junction", left="s1")
    session.do("add_calculation", system="s1", kind="local_probe")
    for entry, combo in (("e1", "embedding_pristine"), ("j1", "junction_left"),
                         ("c5", "system_probe")):
        window.select(entry)
        box = window.properties.form.findChild(QComboBox, combo)
        assert box is not None and box.count() > 1, combo
        assert variant not in [box.itemData(i) for i in range(box.count())], combo
    with pytest.raises(Exception, match="the system it runs on"):     # its own: refused
        session.act("node_connect", source="s1", target="c5", socket="probe")
    assert session.document.calculation("c5").params["probe"] is None
