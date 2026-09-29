"""Moving in space (PLAN.md phase 8): Blender's viewport in the 3D scene and
Inkscape's canvas on the flat drawings. The arithmetic first (ui/navigation.py,
without a window), then the flat canvas driven with matplotlib's mouse events
and Qt's keys. The pyvista scene's own tests are tests/ui/test_pyvista_view.py."""
import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from guiqula.ui import navigation as nav
from guiqula.ui import shortcuts
from guiqula.ui import structure as st


# ---- Blender: the camera
def test_axis_views_look_the_way_blender_does():
    """Front looks along +y with x to the right and z up, right along -x with
    y to the right, top down with y up; the opposite side has the other
    sign, and the bottom view has y down."""
    expected = {"front": ([0, 1, 0], [1, 0, 0], [0, 0, 1]),
                "back": ([0, -1, 0], [-1, 0, 0], [0, 0, 1]),
                "right": ([-1, 0, 0], [0, 1, 0], [0, 0, 1]),
                "left": ([1, 0, 0], [0, -1, 0], [0, 0, 1]),
                "top": ([0, 0, -1], [1, 0, 0], [0, 1, 0]),
                "bottom": ([0, 0, 1], [1, 0, 0], [0, -1, 0])}
    view = nav.Turntable()
    for name, vectors in expected.items():
        view.axis_view(name)
        for got, want in zip(view.directions(), vectors):
            assert np.allclose(got, want, atol=1e-9), name
        assert view.axis() == name and view.ortho
    assert nav.Turntable().axis_view("front", opposite=True) == "back"


def test_orbiting_is_a_turntable_and_leaves_the_axis_view():
    view = nav.Turntable(azimuth=-90.0, elevation=0.0)
    view.orbit(100, 0)                       # to the right: the camera goes to the left
    assert view.azimuth < -90.0 and view.elevation == 0.0
    assert np.allclose(view.directions()[2], [0, 0, 1])     # z stays up
    view.orbit(0, 100)                       # down: the camera goes up
    assert view.elevation > 0.0
    view.axis_view("top")
    assert view.ortho and view.auto_ortho
    view.orbit(3, 0)                         # auto perspective: back to perspective
    assert not view.ortho and view.axis() is None
    view.toggle_projection()                 # by choice, so turning keeps it
    view.axis_view("front")
    view.orbit(3, 0)
    assert view.ortho
    # past the pole the view is upside down and the horizontal drag turns the other way
    upside_down = nav.Turntable(azimuth=0.0, elevation=120.0)
    assert upside_down.directions()[2][2] < 0
    upside_down.orbit(100, 0)
    assert upside_down.azimuth > 0.0


def test_steps_pans_and_zooms():
    view = nav.Turntable(azimuth=-90.0, elevation=0.0)
    view.orbit_step("right")
    assert view.azimuth == pytest.approx(-75.0)
    view.orbit_step("up")
    assert view.elevation == pytest.approx(15.0)
    view.flip()
    assert view.azimuth == pytest.approx(105.0)
    with pytest.raises(ValueError, match="orbit step"):
        view.orbit_step("sideways")
    view = nav.Turntable(azimuth=-90.0, elevation=0.0)
    view.pan(100, 0, 400)                    # the scene follows the pointer to the right
    assert view.target[0] < 0 and view.target[1] == pytest.approx(0.0)
    view.pan_step("up", 400)                 # the view goes up
    assert view.target[2] > 0
    near = view.distance
    view.zoom(1)
    assert view.distance == pytest.approx(near / nav.ZOOM_STEP)
    view.zoom_drag(near, 200.0, 100.0)       # dragging up zooms in
    assert view.distance < near
    view.zoom_drag(near, 200.0, 300.0)
    assert view.distance > near


def test_frame_fits_the_bounds_at_any_aspect():
    view = nav.Turntable()
    view.frame((0, 2, 0, 2, 0, 2), aspect=1.0)
    assert np.allclose(view.target, [1, 1, 1])
    wide, narrow = view.distance, nav.Turntable()
    narrow.frame((0, 2, 0, 2, 0, 2), aspect=0.5)
    assert narrow.distance > wide            # a narrow window needs more room
    view.frame((1, 1, 1, 1, 1, 1))           # a single site: never closer than one unit
    assert view.distance == pytest.approx(nav.MIN_RADIUS / np.sin(np.radians(15.0)))
    view.frame(None)
    assert np.allclose(view.target, 0)


def test_apply_sets_the_camera():
    class Camera:
        pass
    camera = Camera()
    view = nav.Turntable(target=(1, 2, 3), distance=5.0, azimuth=0.0, elevation=0.0, ortho=True)
    view.apply(camera)
    assert np.allclose(camera.position, [6, 2, 3]) and np.allclose(camera.focal_point, [1, 2, 3])
    assert np.allclose(camera.up, [0, 0, 1]) and camera.parallel_projection
    assert camera.parallel_scale == pytest.approx(5.0 * np.tan(np.radians(15.0)))


# ---- Inkscape: the limits
def test_limits_and_history():
    assert nav.zoom_limits((0.0, 4.0), 1.0, 0.5) == (0.5, 2.5)          # 1 stays where it is
    assert nav.shift_limits((0.0, 4.0), 1.5) == (1.5, 5.5)
    low, high = nav.limits_around([1.0, 3.0], margin=0.25)
    assert (low + high) / 2 == pytest.approx(2.0) and high - low == pytest.approx(3.0)
    assert nav.limits_around([2.0])[1] - nav.limits_around([2.0])[0] > 1.0
    history = nav.ZoomHistory()
    a, b, c = ((0, 1), (0, 1)), ((0, 2), (0, 2)), ((0, 3), (0, 3))
    assert history.previous(a) is None and history.next(a) is None
    history.push(a)
    history.push(a)                          # the same view is not pushed twice
    history.push(b)
    assert history.previous(c) == b and history.previous(b) == a
    assert history.previous(a) is None
    assert history.next(a) == b and history.next(b) == c
    history.push(a)                          # a new zoom drops the ones ahead
    assert history.next(a) is None


# ---- Inkscape: the canvas
@pytest.fixture
def view(qtbot):
    from tests.ui.test_structure_tools import grid_build
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


def pixels(view, *points):
    """The display pixels of data points now: a pointer keeps its pixel while the
    drawing moves under it, so a drag is given in pixels."""
    return [tuple(view.ax.transData.transform(point)) for point in points]


def at(view, kind, pixel, button=1, key=None):
    MouseEvent(kind, view.canvas, pixel[0], pixel[1], button, key=key)._process()


def limits(view):
    view.ax.apply_aspect()
    return np.array([view.ax.get_xlim(), view.ax.get_ylim()])


def test_the_wheel_scrolls_and_ctrl_zooms_about_the_pointer(view):
    before = limits(view)
    mouse(view, "scroll_event", 1.0, 1.0, button="up", step=1)
    scrolled = limits(view)
    assert np.allclose(scrolled[0], before[0]) and np.all(scrolled[1] > before[1])
    assert np.allclose(np.diff(scrolled, axis=1), np.diff(before, axis=1))
    mouse(view, "scroll_event", 1.0, 1.0, button="down", step=-1)
    assert np.allclose(limits(view), before)
    mouse(view, "scroll_event", 1.0, 1.0, button="up", step=1, key="shift")   # sideways
    sideways = limits(view)
    assert np.all(sideways[0] < before[0]) and np.allclose(sideways[1], before[1])
    mouse(view, "scroll_event", 1.0, 1.0, button="down", step=-1, key="shift")
    x, y = view.ax.transData.transform((1.0, 2.0))
    MouseEvent("scroll_event", view.canvas, x, y, "up", key="control", step=1)._process()
    zoomed = limits(view)
    assert np.allclose(np.diff(zoomed, axis=1), np.diff(before, axis=1) / nav.ZOOM_FACTOR)
    assert np.allclose(view.ax.transData.transform((1.0, 2.0)), (x, y), atol=1.0)   # it stays put
    MouseEvent("scroll_event", view.canvas, x, y, "down", key="control", step=-1)._process()
    assert np.allclose(limits(view), before)


def test_the_middle_button_drags_and_clicks_zoom(view):
    before = limits(view)
    start, middle, end = pixels(view, (1.0, 1.0), (1.5, 1.0), (2.0, 1.0))
    at(view, "button_press_event", start, 2)
    at(view, "motion_notify_event", middle, 2)
    at(view, "motion_notify_event", end, 2)
    at(view, "button_release_event", end, 2)
    dragged = limits(view)
    assert np.allclose(dragged[0], before[0] - 1.0, atol=0.02)      # the layout settles a hair
    assert np.allclose(dragged[1], before[1], atol=0.02)
    assert view.selected().tolist() == []                   # and nothing was picked
    x, y = view.ax.transData.transform((2.0, 2.0))
    mouse(view, "button_press_event", 2.0, 2.0, button=2)   # a click: zoom in about it
    mouse(view, "button_release_event", 2.0, 2.0, button=2)
    zoomed = limits(view)
    assert np.allclose(np.diff(zoomed, axis=1), np.diff(dragged, axis=1) / nav.ZOOM_FACTOR)
    assert np.allclose(view.ax.transData.transform((2.0, 2.0)), (x, y), atol=1.0)
    mouse(view, "button_press_event", 2.0, 2.0, button=2, key="shift")   # shift: out
    mouse(view, "button_release_event", 2.0, 2.0, button=2, key="shift")
    assert np.allclose(np.diff(limits(view), axis=1), np.diff(dragged, axis=1), rtol=1e-3)


def test_space_turns_the_left_button_into_the_hand(view):
    before = limits(view)
    view.set_tool("box")
    QTest.keyPress(view.canvas, Qt.Key.Key_Space)
    assert view.navigation.hand
    start, middle, end = pixels(view, (0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
    at(view, "button_press_event", start)
    at(view, "motion_notify_event", middle)
    at(view, "motion_notify_event", end)
    at(view, "button_release_event", end)
    assert np.allclose(limits(view)[0], before[0] - 2.0, atol=0.02)
    assert view.selected().tolist() == []
    QTest.keyRelease(view.canvas, Qt.Key.Key_Space)
    assert not view.navigation.hand
    view.set_tool("pick")
    mouse(view, "button_press_event", 1.05, 0.05)           # a click selects again
    assert len(view.selected()) == 1


def test_zoom_keys_history_and_selection(view):
    handlers = view.navigation.key_handlers()
    assert set(handlers) <= {row[0] for row in shortcuts.SHORTCUTS}
    start = limits(view)
    handlers["zoom_in"]()
    handlers["zoom_in"]()
    assert np.allclose(np.diff(limits(view), axis=1), np.diff(start, axis=1) / 2)
    handlers["zoom_previous"]()
    assert np.allclose(np.diff(limits(view), axis=1), np.diff(start, axis=1) / nav.ZOOM_FACTOR)
    handlers["zoom_previous"]()
    assert np.allclose(limits(view), start)
    assert not handlers["zoom_previous"]()                  # nothing before
    handlers["zoom_next"]()
    handlers["zoom_next"]()
    assert np.allclose(np.diff(limits(view), axis=1), np.diff(start, axis=1) / 2)
    handlers["zoom_out"]()
    before = limits(view)
    handlers["scroll_right"]()                              # the view moves right
    assert np.all(limits(view)[0] > before[0]) and np.allclose(limits(view)[1], before[1])
    handlers["scroll_up"]()
    assert np.all(limits(view)[1] > before[1])
    view.select([5, 6, 9, 10])                              # the inner 2 x 2
    handlers["zoom_selection"]()
    frame = limits(view)
    assert np.all(frame[:, 0] < [1.0, 1.0]) and np.all(frame[:, 1] > [2.0, 2.0])
    assert np.all(np.diff(frame, axis=1) < 3.0)             # closer than the whole flake
    box = view.ax.get_window_extent()                       # the equal aspect is kept
    assert np.diff(frame[0])[0] / np.diff(frame[1])[0] == pytest.approx(
        box.width / box.height, rel=1e-3)
    handlers["zoom_drawing"]()
    whole = limits(view)
    assert np.all(np.diff(whole, axis=1) > np.diff(frame, axis=1))
    view.select([], "replace")
    handlers["zoom_selection"]()                            # nothing selected: everything
    assert np.allclose(limits(view), whole)
    assert view.navigation.history.past                     # zooms were remembered ...
    from tests.ui.test_structure_tools import grid_build
    view.show_structure("s2", grid_build(3), "another system")
    assert not view.navigation.history.past                 # ... for that drawing only
    assert not handlers["zoom_previous"]()


def test_a_3d_drawing_is_left_to_its_own_controls(view):
    view.set_projection("3d")
    view.show_structure("s2", view.build, "3d")
    assert view.navigation.axes() is None
    assert not view.navigation.zoom(0.5)
