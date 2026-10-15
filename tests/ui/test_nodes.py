"""The node view (PLAN.md phase 9, part C): the Outliner dock's other view,
the nodes and links of the Document, a link drawn with the mouse as one
Command, the same edit made through the tree's form and through the nodes
giving the same Document, refusals said, places kept as view state."""
import json
from pathlib import Path

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


def test_del_removes_a_selection_with_what_it_uses_as_one_step(qapp, no_jobs, qtbot):
    """Del on a system selected with its geometry and its calculations
    removes the users first, as one undo step (decision 269); a selection
    still used from outside it is refused whole."""
    window, session = make_window(qapp, no_jobs)
    try:
        session.act("outliner_view", name="nodes")
        view = window.node_view
        undo = len(session.dispatcher.history()["undo"])
        view.scene().clearSelection()
        for node in ("s1", "c1"):                     # c2 still runs on s1: refused whole
            view.node_items[node].setSelected(True)
        view.setFocus()
        QTest.keyClick(view, Qt.Key.Key_Delete)
        assert [c.id for c in session.document.calculations] == ["c1", "c2"]
        assert "c2" in window.log.toPlainText().splitlines()[-1]
        view.scene().clearSelection()
        for node in ("geo1", "k1", "s1", "c1", "c2"):
            view.node_items[node].setSelected(True)
        QTest.keyClick(view, Qt.Key.Key_Delete)
        qtbot.waitUntil(lambda: not session.document.systems)
        assert not session.document.calculations and not session.document.geometries
        assert [k.id for k in session.document.kpaths] == ["k2"]
        assert len(session.dispatcher.history()["undo"]) == undo + 1
        session.undo()
        assert [s.id for s in session.document.systems] == ["s1"]
        assert [c.id for c in session.document.calculations] == ["c1", "c2"]
    finally:
        window.close()
        session.close()


def test_a_place_is_not_inherited_by_a_new_entry(nodes):
    """The place of a removed node is not saved, comes back with an undo,
    and is not taken by a new entry that gets the same id (decision 270)."""
    window, session = nodes
    session.act("outliner_view", name="nodes")
    session.act("node_move", node="c2", x=500, y=500)
    column = window.node_view.node_items["c1"].pos().x()
    session.do("remove", entry="c2")
    assert "nodes" not in window.view_state()
    session.undo()
    assert window.node_view.node_items["c2"].pos().x() == 500
    session.do("remove", entry="c2")
    assert session.do("add_calculation", system="s1", kind="ldos") == "c2"
    assert window.node_view.node_items["c2"].pos().x() == column
    assert "c2" not in window.node_places and "nodes" not in window.view_state()
    with pytest.raises(Exception, match="zz99"):
        session.act("node_move", node="zz99", x=1, y=2)
    window.apply_view_state({"nodes": {"zz99": [1, 2], "s1": [400, 300]}})
    assert window.node_places == {"s1": [400.0, 300.0]}


def test_a_link_drag_survives_a_refresh(nodes):
    """A build or a job ending while a link is drawn (the scene drawn again)
    raises nothing, and the link is still made on the drop (decision 271)."""
    window, session = nodes
    session.act("outliner_view", name="nodes")
    view = window.node_view
    view.resetTransform()
    view.centerOn(view.node_items["k2"])
    viewport = view.viewport()
    start, end = view.socket_point("k2"), view.socket_point("c1", "kpath")
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(viewport, QPoint(start.x() + 30, start.y()))
    window._refresh_tree()                                  # what _job_changed does
    QTest.mouseMove(viewport, end)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    assert session.document.calculation("c1").params["kpath"] == "k2"


def test_a_node_drag_survives_a_refresh(nodes):
    window, session = nodes
    session.act("outliner_view", name="nodes")
    view = window.node_view
    view.resetTransform()
    view.centerOn(view.node_items["c1"])
    item = view.node_items["c1"]
    start = view.mapFromScene(item.mapToScene(QPoint(60, 8)))
    viewport = view.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, 5):
        QTest.mouseMove(viewport, QPoint(start.x() - 10 * step, start.y() + 15 * step))
    window._refresh_tree()
    end = QPoint(start.x() - 50, start.y() + 75)
    QTest.mouseMove(viewport, end)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    place = window.node_places.get("c1")
    assert place is not None
    assert view.node_items["c1"].pos().x() == place[0] and view.node_items["c1"].pos().y() == place[1]
    assert place[1] > 0


def test_nodes_on_an_empty_document_are_drawn_at_their_size(qapp, no_jobs, qtbot):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session(jobs=no_jobs)
    window.attach(session)
    try:
        session.act("outliner_view", name="nodes")
        qtbot.wait(50)                                  # the queued frame_all
        assert window.node_view.transform().m11() == 1.0
        session.do("add_system", lattice="honeycomb_lattice")
        assert window.node_view.transform().m11() == 1.0
    finally:
        window.close()
        session.close()


def test_home_reaches_a_node_moved_far(nodes):
    window, session = nodes
    session.act("outliner_view", name="nodes")
    view = window.node_view
    session.act("node_move", node="c2", x=3000, y=2000)
    view.setFocus()
    QTest.keyClick(view, Qt.Key.Key_Home)
    shown = view.mapToScene(view.viewport().rect()).boundingRect()
    for node in ("s1", "c2"):
        assert shown.contains(view.node_items[node].sceneBoundingRect()), node


def test_a_geometry_node_and_its_tree_row_select_each_other(nodes):
    window, session = nodes
    session.act("outliner_view", name="nodes")
    view = window.node_view
    view.scene().clearSelection()
    view.node_items["geo1"].setSelected(True)
    assert window.selected == "geo1" and window.outliner.current_id() == "s1/geometry"
    window.select("s1/geometry")
    assert view.node_items["geo1"].isSelected()


def test_the_menu_of_a_socket_is_deleted_when_it_closes(nodes, qapp):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QMenu
    window, session = nodes
    session.act("outliner_view", name="nodes")
    view = window.node_view
    point = view.socket_point("c1", "kpath")
    for _ in range(3):
        view.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point,
                                                view.viewport().mapToGlobal(point)))
        shown = [m for m in view.findChildren(QMenu, "nodeSocketMenu") if m.isVisible()]
        assert len(shown) == 1
        shown[0].hide()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert len(view.findChildren(QMenu, "nodeSocketMenu")) == 0


def test_no_k_path_link_passes_behind_a_node(qapp, no_jobs):
    """On every preset's default layout a k-path's link meets no node but
    the two it joins (decision 272)."""
    from pathlib import Path
    import guiqula
    from guiqula.ui.nodes import NodeView
    presets = sorted(p.stem for p in (Path(guiqula.__file__).parent / "presets").glob("*.json"))
    view = NodeView()
    for preset in presets:
        session = Session(preset, jobs=no_jobs)
        try:
            view.refresh(session)
            for link in view.link_items:
                if view.node_items[link.link.source].node.kind != "kpath":
                    continue
                path = link.path()
                for node, item in view.node_items.items():
                    if node in (link.link.source, link.link.target):
                        continue
                    box = item.sceneBoundingRect()
                    assert not any(box.contains(path.pointAtPercent(i / 100))
                                   for i in range(101)), (preset, link.link.source, node)
        finally:
            session.close()
    view.deleteLater()


def test_a_grab_after_a_link_does_not_crash(run_python, tmp_path):
    # the "+" of a section row kept a plain QModelIndex, which the resize of a
    # grab read after the tree was rebuilt: a segfault, so in its own process
    drive = str(Path(run_python.src).parent / "tools" / "drive.py")
    code = ("import sys, runpy; sys.argv = " + repr([
        drive, "honeycomb_zeeman_rashba", "--no-warm",
        "--do", '{"do": "outliner_view", "name": "nodes"}',
        "--do", '{"do": "add_kpath", "vertices": ["G", "K", "M", "G"]}',
        "--do", '{"do": "node_connect", "source": "k2", "target": "c1", "socket": "kpath"}',
        "--widget", "outlinerDock", "--shot", str(tmp_path / "nodes.png")])
        + "; runpy.run_path(sys.argv[0], run_name='__main__')")
    result = run_python(code, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
    assert (tmp_path / "nodes.png").exists()
