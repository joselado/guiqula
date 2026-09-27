"""Site selection on the structure canvas (PLAN.md 13.2): the pure
geometry, then real mouse events on an offscreen canvas."""
import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent

from guiqula.ui import structure as st


def grid_build(n=4):
    """An n x n square flake with first-neighbour bonds and two sublattices."""
    xs, ys = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float), indexing="ij")
    positions = np.stack([xs.ravel(), ys.ravel(), np.zeros(n * n)], axis=1)
    d = np.linalg.norm(positions[:, None] - positions[None], axis=2)
    bonds = np.array([(i, j) for i, j in zip(*np.nonzero(np.isclose(d, 1.0))) if i < j])
    sublattice = np.where((xs + ys).ravel() % 2 == 0, 1.0, -1.0)
    return {"positions": positions, "lattice": np.eye(3), "dimensionality": 0,
            "sublattice": sublattice, "bonds": bonds, "image_bonds": np.zeros((0, 5), int),
            "mode": "spinless", "sites": n * n}


def test_selection_geometry():
    b = grid_build()
    r = b["positions"]
    assert st.indices_in_box(r, 2.5, 2.5, 0.5, 0.5).tolist() == [5, 6, 9, 10]   # corners in any order
    triangle = [[-0.5, -0.5], [3.5, -0.5], [-0.5, 3.5]]
    assert len(st.indices_in_polygon(r, triangle)) == 10
    assert st.indices_in_polygon(r, [[0, 0], [1, 1]]).tolist() == []
    assert st.nearest_index(r, 1.1, 2.2) == 6 and st.nearest_index(r, 1.5, 2.5, 0.3) is None
    assert st.coordination(b).tolist().count(4) == 4                # the inner 2 x 2
    assert len(st.edge_indices(b)) == 12
    assert len(st.sublattice_indices(b, 1)) == len(st.sublattice_indices(b, -1)) == 8
    assert st.combine([1, 2], [2, 3], "add").tolist() == [1, 2, 3]
    assert st.combine([1, 2], [2, 3], "toggle").tolist() == [1, 3]
    assert st.combine([1, 2], [2, 3], "remove").tolist() == [1]
    with pytest.raises(ValueError, match="unknown selection mode"):
        st.combine([], [], "nope")
    assert st.match_positions(r, [[1.0, 2.0, 0.0], [9.0, 9.0, 0.0]]).tolist() == [6]


@pytest.fixture
def view(qtbot):
    view = st.StructureView()
    qtbot.addWidget(view)
    view.resize(600, 600)
    view.show()
    qtbot.waitExposed(view)
    view.show_structure("s1", grid_build(), "grid")
    view.canvas.draw()
    return view


def mouse(view, kind, x, y, button=1, key=None, step=0):
    px, py = view.ax.transData.transform((x, y))
    MouseEvent(kind, view.canvas, px, py, button, key=key, step=step)._process()


def test_pick_with_modifiers(view):
    counts = []
    view.selection_changed.connect(counts.append)
    mouse(view, "button_press_event", 1.05, 0.05)                 # site (1, 0) is index 4
    assert view.selected().tolist() == [4]
    mouse(view, "button_press_event", 2.0, 3.0, key="shift")
    assert view.selected().tolist() == [4, 11]
    mouse(view, "button_press_event", 1.0, 1.0, key="control")
    mouse(view, "button_press_event", 2.0, 3.0, key="control")
    assert view.selected().tolist() == [4, 5]
    assert "2 selected" in view.caption.text()
    mouse(view, "button_press_event", 1.5, 1.5)                   # on nothing: clears
    assert view.selected().tolist() == [] and counts[-1] == 0
    assert np.allclose(view._selection_artist.get_offsets(), np.zeros((0, 2)))


def test_box_and_lasso_tools(view):
    view.set_tool("box")
    mouse(view, "button_press_event", -0.2, -0.2)                 # inside the margins
    mouse(view, "motion_notify_event", 1.3, 1.3)
    mouse(view, "button_release_event", 1.3, 1.3)
    assert view.selected().tolist() == [0, 1, 4, 5]
    view.set_tool("lasso")
    path = [(1.5, -0.2), (3.2, -0.2), (3.2, 1.5), (1.5, 1.5)]
    mouse(view, "button_press_event", *path[0])
    for point in path[1:]:
        mouse(view, "motion_notify_event", *point)
    mouse(view, "button_release_event", *path[-1])
    assert view.selected().tolist() == [8, 9, 12, 13]
    mouse(view, "button_press_event", 0.0, 0.0)      # clicks do not pick in lasso mode
    assert view.selected().tolist() == [8, 9, 12, 13]
    with pytest.raises(ValueError, match="unknown tool"):
        view.set_tool("brush")


def toolbar_action(view, text):
    return next(a for a in view.toolbar.actions() if a.text() == text)


def test_pan_or_zoom_takes_the_clicks_until_a_tool_is_chosen(view, qtbot):
    """matplotlib keeps its pan or zoom mode on until its button is clicked
    again, and meanwhile the canvas selects nothing; choosing a selection
    tool (the window's Pick, Box, Lasso or their keys) turns it off."""
    states = []
    view.navigation_changed.connect(states.append)
    for text in ("Pan", "Zoom"):
        toolbar_action(view, text).trigger()                    # the toolbar button
        qtbot.waitUntil(lambda: states[-1:] == [True])
        mouse(view, "button_press_event", 1.05, 0.05)
        mouse(view, "button_release_event", 1.05, 0.05)
        assert view.selected().tolist() == []                   # the mode took the click
        view.set_tool("pick")
        assert str(view.toolbar.mode) == "" and states[-1] is False
        assert not toolbar_action(view, text).isChecked()
        mouse(view, "button_press_event", 1.05, 0.05)
        assert view.selected().tolist() == [4]
        view.select([], "replace")
    toolbar_action(view, "Pan").trigger()                       # and off with its own button
    qtbot.waitUntil(lambda: states[-1:] == [True])
    toolbar_action(view, "Pan").trigger()
    qtbot.waitUntil(lambda: states[-1:] == [False])


def test_selection_survives_a_rebuild_and_wheel_zooms(view):
    view.select([0, 15])
    view.show_structure("s1", grid_build(), "same geometry again")
    assert view.selected().tolist() == [0, 15]
    smaller = grid_build(3)
    view.show_structure("s1", smaller, "a smaller flake")
    assert view.selected().tolist() == [0]           # (3, 3) is gone, (0, 0) stays
    width = np.diff(view.ax.get_xlim())[0]
    mouse(view, "scroll_event", 1.0, 1.0, button="up", step=1)
    assert np.diff(view.ax.get_xlim())[0] < width
    view.show_structure("s2", smaller, "another system")
    assert view.selected().tolist() == []
