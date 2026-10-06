"""The grids of result views (decisions 170 to 180): the grid and
grid_place actions, the swaps and the returns to the tabs, a detached view
coming back to its cell, a result removed from the Document leaving its
cell, the view state, and the drops that a drag ends with."""
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from guiqula.ui import grid as gridmod
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


@pytest.fixture(autouse=True)
def clean(window):
    yield
    for grid_id in list(window.grids):
        window.close_grid(grid_id)
    for calc in list(window.plots):
        window.close_result(calc)


def _in_tab(window, calc):
    return window.viewport.indexOf(window.plots[calc]) >= 0


def _drop(widget, calc):
    """What a drag ending on the widget does to it: it enters, then drops
    (Qt delivers no drop to a widget that a drag did not enter)."""
    mime = gridmod.mime_of(calc)
    centre = QPointF(widget.rect().center())
    QApplication.sendEvent(widget, QDragEnterEvent(
        centre.toPoint(), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier))
    event = QDropEvent(centre, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def test_a_grid_holds_live_views_that_swap_and_go_back(window, qtbot, shot):
    session = window.session
    state = session.act("grid")
    assert state == {"grid": "g1", "rows": 2, "cols": 2, "cells": []}
    grid = window.grids["g1"]
    assert window.viewport.currentWidget() is grid and window.current_tab() == "grid:g1"
    assert grid.objectName() == "grid_g1"
    assert grid.cell(1, 1).objectName() == "gridCell_g1_1_1"
    assert grid.cell(0, 0).empty.isVisible()
    # a result into a cell: out of the tab bar, the same view, its title the tab's text
    state = session.act("grid_place", calculation="c1", grid="g1", row=0, col=0)
    assert state["cells"] == [[0, 0, "c1"]]
    view = window.plots["c1"]
    assert not _in_tab(window, "c1") and grid.cell(0, 0).view is view
    assert view.isVisible() and not grid.cell(0, 0).empty.isVisible()
    assert grid.cell(0, 0).title.label.text() == window._tab_text("c1")
    assert window.current_tab() == "grid:g1"
    session.act("grid_place", calculation="c2", grid="g1", row=1, col=1)
    shot(grid, "two")
    # onto a taken cell from another cell: the two swap
    state = session.act("grid_place", calculation="c1", grid="g1", row=1, col=1)
    assert state["cells"] == [[0, 0, "c2"], [1, 1, "c1"]]
    # the same place again changes nothing
    assert session.act("grid_place", calculation="c1", grid="g1", row=1, col=1) == state
    # from its tab onto a taken cell: the one there goes back to its tab
    session.act("grid_place", calculation="c2")
    assert _in_tab(window, "c2") and window.viewport.currentWidget() is window.plots["c2"]
    session.act("grid_place", calculation="c2", grid="g1", row=1, col=1)
    assert _in_tab(window, "c1") and grid.placed() == {(1, 1): "c2"}
    # a smaller grid gives back the results of the cells it leaves out
    session.act("grid_place", calculation="c1", grid="g1", row=0, col=1)
    state = session.act("grid", grid="g1", rows=1, cols=2)
    assert state == {"grid": "g1", "rows": 1, "cols": 2, "cells": [[0, 1, "c1"]]}
    assert _in_tab(window, "c2") and set(grid.cells) == {(0, 0), (0, 1)}
    assert grid.spins["rows"].value() == 1
    # Run names the calculation whose cell title was clicked
    grid.cell(0, 1).chosen.emit("c1")
    assert window.selected_calculation() == "c1"
    # closing the grid gives every result back to its tab
    session.act("grid", grid="g1", close=True)
    assert window.grids == {} and _in_tab(window, "c1") and _in_tab(window, "c2")


def test_refusals(window):
    session = window.session
    session.act("grid", rows=1, cols=1)
    with pytest.raises(Exception, match="1 to 4"):
        session.act("grid", rows=5)
    with pytest.raises(Exception, match="no grid 'g9'"):
        session.act("grid_place", calculation="c1", grid="g9")
    with pytest.raises(Exception, match="not a cell at row 1"):
        session.act("grid_place", calculation="c1", grid="g1", row=1, col=0)
    with pytest.raises(Exception, match="no calculation"):
        session.act("grid_place", calculation="c7", grid="g1")
    assert session.act("grid")["grid"] == "g2"


def test_detached_from_a_cell_it_comes_back_there(window):
    session = window.session
    session.act("grid", rows=1, cols=2)
    session.act("grid_place", calculation="c1", grid="g1", row=0, col=1)
    assert window.toggle_detached("c1") is True
    assert "c1" in window.plot_windows and window.grids["g1"].placed() == {}
    assert window.plots["c1"].detach.text() == "Attach"
    assert window.toggle_detached("c1") is False
    assert window.grids["g1"].placed() == {(0, 1): "c1"} and "c1" not in window.plot_windows
    # taken meanwhile: back to its tab
    window.toggle_detached("c1")
    session.act("grid_place", calculation="c2", grid="g1", row=0, col=1)
    window.toggle_detached("c1")
    assert _in_tab(window, "c1")


def test_a_removed_calculation_leaves_its_cell(window, qtbot):
    session = window.session
    calc = session.do("add_calculation", system="s1", kind="dos")
    session.act("grid", rows=1, cols=1)
    session.act("grid_place", calculation=calc, grid="g1")
    session.do("remove", entry=calc)
    qtbot.waitUntil(lambda: calc not in window.plots, timeout=5_000)
    assert window.grids["g1"].placed() == {} and window.grids["g1"].cell(0, 0).empty.isVisible()


def test_the_view_state_keeps_the_grids(window, tmp_path):
    session = window.session
    session.act("grid", rows=2, cols=3)
    session.act("grid_place", calculation="c2", grid="g1", row=1, col=2)
    session.act("grid_place", calculation="c1", grid="g1", row=0, col=0)
    state = window.view_state()
    assert state["grids"] == [{"grid": "g1", "rows": 2, "cols": 3,
                               "cells": [[0, 0, "c1"], [1, 2, "c2"]]}]
    assert state["tab"] == "grid:g1"
    image = tmp_path / "grid.png"
    session.act("grid", grid="g1", image=str(image))
    assert image.stat().st_size > 0
    window.apply_view_state({})
    assert window.grids == {}
    window.apply_view_state(state)
    assert window.grid_state("g1") == {"grid": "g1", "rows": 2, "cols": 3,
                                       "cells": [[0, 0, "c1"], [1, 2, "c2"]]}
    assert window.current_tab() == "grid:g1"
    # what no longer fits is skipped, never an error
    window.apply_view_state(dict(state, grids=[{"grid": "g1", "rows": 9, "cols": 1,
                                                "cells": [[0, 0, "c9"], [7, 7, "c1"]]},
                                               {"nonsense": 1}, "g2"]))
    assert window.grid_state("g1") == {"grid": "g1", "rows": 4, "cols": 1, "cells": []}


def test_a_drop_on_a_cell_and_on_the_tab_bar(window, qtbot):
    session = window.session
    session.act("grid")
    window.result_view("c1")
    grid = window.grids["g1"]
    assert gridmod.calc_of(gridmod.mime_of("c1")) == "c1"
    _drop(grid.cell(1, 0), "c1")
    qtbot.waitUntil(lambda: grid.placed() == {(1, 0): "c1"}, timeout=5_000)
    _drop(window.viewport.tabBar(), "c1")
    qtbot.waitUntil(lambda: _in_tab(window, "c1"), timeout=5_000)
    assert grid.placed() == {}
    # the tab bar drags results only
    bar = window.viewport.tabBar()
    assert bar.calc_at(window.viewport.indexOf(window.plots["c1"])) == "c1"
    assert bar.calc_at(0) is None and bar.calc_at(window.viewport.indexOf(grid)) is None


def test_a_drag_held_over_a_grid_tab_shows_it_and_a_drop_there_fills_it(window, qtbot):
    """Pressing a result's tab shows the result, hiding the grid: a drag
    held over the Grid tab shows the grid at once, and a drop on the Grid
    tab itself puts the result in the first free cell."""
    session = window.session
    session.act("grid", rows=1, cols=2)
    grid = window.grids["g1"]
    window.show_result("c1")                     # what pressing its tab does
    bar = window.viewport.tabBar()
    at = QPointF(bar.tabRect(window.viewport.indexOf(grid)).center())
    mime = gridmod.mime_of("c1")
    QApplication.sendEvent(bar, QDragEnterEvent(at.toPoint(), Qt.DropAction.MoveAction, mime,
                                                Qt.MouseButton.LeftButton,
                                                Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(bar, QDragMoveEvent(at.toPoint(), Qt.DropAction.MoveAction, mime,
                                               Qt.MouseButton.LeftButton,
                                               Qt.KeyboardModifier.NoModifier))
    assert window.viewport.currentWidget() is grid and grid.cell(0, 0).isVisible()
    QApplication.sendEvent(bar, QDropEvent(at, Qt.DropAction.MoveAction, mime,
                                           Qt.MouseButton.LeftButton,
                                           Qt.KeyboardModifier.NoModifier))
    qtbot.waitUntil(lambda: grid.placed() == {(0, 0): "c1"}, timeout=5_000)
    # the action alike: the first free cell, the one it is in already, refused when full
    assert session.act("grid_place", calculation="c2", grid="g1")["cells"] == \
        [[0, 0, "c1"], [0, 1, "c2"]]
    assert session.act("grid_place", calculation="c1", grid="g1")["cells"] == \
        [[0, 0, "c1"], [0, 1, "c2"]]
    session.act("grid")
    session.act("grid", grid="g2", rows=1, cols=1)
    session.act("grid_place", calculation="c1", grid="g2")
    with pytest.raises(Exception, match="grid g2 is full"):
        session.act("grid_place", calculation="c2", grid="g2")


def test_an_empty_cell_offers_the_results(window, qtbot):
    session = window.session
    session.act("grid", rows=1, cols=1)
    cell = window.grids["g1"].cell(0, 0)
    assert cell.choose.objectName() == "gridChoose_g1_0_0" and cell.choose.isVisible()
    menu = cell.choose.menu()
    menu.aboutToShow.emit()
    texts = [action.text() for action in menu.actions()]
    assert texts == [window._tab_text("c1"), window._tab_text("c2")]
    menu.actions()[1].trigger()
    qtbot.waitUntil(lambda: window.grids["g1"].placed() == {(0, 0): "c2"}, timeout=5_000)
    assert not cell.choose.isVisible()
