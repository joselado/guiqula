"""The 3D drawing with pyvista (View > 3D drawing, ui/pyvista_view.py),
driven offscreen: the scene renders off-screen, the mouse and the keys
move it as Blender's viewport does (PLAN.md phase 8: the middle button
orbits as a turntable, shift pans, ctrl zooms, the wheel zooms, the numpad
gives the views), the canvas and the results on the atoms draw with it, the
canvas's 3D box decides for the results too (a magnetization on a flat
lattice drawn in 3D), and a pyvista that is missing or cannot draw leaves
the drawing to mplot3d."""
import numpy as np
import pytest
from mpl_toolkits.mplot3d import Axes3D

pytest.importorskip("pyvista")

from PySide6.QtCore import Qt                         # noqa: E402
from PySide6.QtTest import QTest                      # noqa: E402

from guiqula.io import settings                       # noqa: E402
from guiqula.ui import pyvista_view                   # noqa: E402
from guiqula.ui.app import build_main_window          # noqa: E402

# a cluster that is not flat, as a build of engine/structure.py gives it
CLUSTER = {"positions": np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0.5], [1, 1, 1]]),
           "lattice": np.eye(3), "dimensionality": 0, "sublattice": np.array([1, -1, 1, -1]),
           "bonds": [(0, 1), (0, 2), (1, 3), (2, 3)], "image_bonds": []}


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.start_session("honeycomb_hubbard", warm=False)
    yield window
    window.close()


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)


def run(window, qtbot, calc):
    window.session.run_calculation(calc, wait=True, timeout=600)
    job = window.session.calc_jobs[calc]
    assert job.status == "done", job.error
    window.show_result(calc)
    qtbot.waitUntil(lambda: window.plots[calc].result is not None, timeout=10_000)
    return window.plots[calc]


def drawn(canvas):
    """Pixels that are not the background."""
    pixels = canvas.pixels().astype(int)
    return int(np.sum(np.any(np.abs(pixels - pixels[0, 0]) > 30, axis=2)))


def distance(plotter):
    position, focus, _ = plotter.camera_position
    return float(np.linalg.norm(np.subtract(position, focus)))


def test_the_scene_moves_as_in_blender(qapp, qtbot, tmp_path, shot):
    view = pyvista_view.SceneView("scene")
    qtbot.addWidget(view)
    view.resize(500, 400)
    view.show()
    view.show_scene(CLUSTER, selected=[0])
    canvas, plotter = view.canvas, view.canvas.plotter
    assert drawn(canvas) > 500                       # the sites and bonds are there
    assert plotter.actors.keys() >= {"sites", "bonds", "selection"}
    first = plotter.camera_position
    canvas.drag((250, 200), (330, 170), button="LeftButton")     # the left button is not
    assert np.allclose(plotter.camera_position[0], first[0])     # Blender's view button
    canvas.drag((250, 200), (330, 170))              # the middle button orbits
    turned = plotter.camera_position
    assert not np.allclose(first[0], turned[0])
    assert np.allclose(first[1], turned[1])          # about the same point
    assert distance(plotter) == pytest.approx(distance_of(first), rel=1e-6)
    assert view.canvas.view.description() == "User Perspective"
    up = np.array(turned[2])
    assert abs(np.dot(up, [0, 0, 1])) > 0.5          # a turntable: z stays up
    canvas.drag((250, 200), (330, 170), button="LeftButton", alt=True)   # alt+left emulates it
    assert not np.allclose(plotter.camera_position[0], turned[0])
    turned = plotter.camera_position
    for _ in range(3):
        canvas.send("MouseWheelForward", 250, 200)   # the wheel zooms in
    assert distance(plotter) < 0.9 * distance_of(first)
    canvas.drag((250, 200), (280, 200), shift=True)  # shift and the middle button pan
    assert not np.allclose(plotter.camera_position[1], turned[1])
    near = distance(plotter)
    canvas.drag((250, 200), (250, 300), ctrl=True)   # ctrl and the middle button zoom
    assert distance(plotter) > near                  # (down zooms out)
    before = np.array(plotter.camera_position[1])
    canvas.send("MouseWheelForward", 250, 200, ctrl=True)     # ctrl+wheel pans sideways
    moved = np.array(plotter.camera_position[1]) - before
    assert np.linalg.norm(moved) > 0
    canvas.send("MouseWheelForward", 250, 200, shift=True)    # shift+wheel pans up
    assert not np.allclose(plotter.camera_position[1], before + moved)
    shot(view, "turned")
    view.set_selection(np.zeros((0, 3)))
    assert "selection" not in plotter.actors
    view.reset_view()
    assert np.allclose(plotter.camera_position[0], first[0])   # the first view again
    view.show_scene(CLUSTER, keep=True, fit=False)   # the same system drawn again
    canvas.drag((250, 200), (300, 200))
    kept = plotter.camera_position
    view.show_scene(CLUSTER, keep=True, fit=False)
    assert np.allclose(plotter.camera_position[0], kept[0])    # the camera stays
    saved = view.save_image(tmp_path / "view.png")
    assert (tmp_path / "view.png").stat().st_size > 1000, saved


def numpad(canvas, key, *modifiers):
    flags = Qt.KeyboardModifier.KeypadModifier
    for modifier in modifiers:
        flags |= modifier
    QTest.keyClick(canvas, key, flags)


def test_the_numpad_gives_the_views_of_blender(qapp, qtbot, shot):
    view = pyvista_view.SceneView("scene")
    qtbot.addWidget(view)
    view.resize(500, 400)
    view.show()
    view.show_scene(CLUSTER, selected=[3])
    canvas, plotter = view.canvas, view.canvas.plotter
    canvas.setFocus()
    ctrl = Qt.KeyboardModifier.ControlModifier
    for key, name, opposite in ((Qt.Key.Key_1, "Front", "Back"), (Qt.Key.Key_3, "Right", "Left"),
                                (Qt.Key.Key_7, "Top", "Bottom")):
        numpad(canvas, key)
        assert canvas.view.description() == f"{name} Orthographic"
        assert plotter.camera.parallel_projection
        numpad(canvas, key, ctrl)
        assert canvas.view.description() == f"{opposite} Orthographic"
    numpad(canvas, Qt.Key.Key_7)                       # top: looking down -z, x right, y up
    position, focus, up = plotter.camera_position
    assert np.allclose(np.subtract(position, focus)[:2], 0, atol=1e-6)
    assert position[2] > focus[2] and np.allclose(up, [0, 1, 0], atol=1e-6)
    shot(view, "top")
    numpad(canvas, Qt.Key.Key_4)                       # orbiting leaves the axis view, and
    assert canvas.view.description() == "User Perspective"     # with it the orthographic view
    assert canvas.view.azimuth == pytest.approx(-90 - 15)
    assert not plotter.camera.parallel_projection
    numpad(canvas, Qt.Key.Key_1)                       # front: azimuth -90, elevation 0
    azimuth, elevation = canvas.view.azimuth, canvas.view.elevation
    numpad(canvas, Qt.Key.Key_6)
    assert canvas.view.azimuth == pytest.approx(azimuth + 15)
    numpad(canvas, Qt.Key.Key_8)
    assert canvas.view.elevation == pytest.approx(elevation + 15)
    numpad(canvas, Qt.Key.Key_2)
    assert canvas.view.elevation == pytest.approx(elevation)
    target = np.array(plotter.camera_position[1])
    numpad(canvas, Qt.Key.Key_4, ctrl)                 # ctrl and the numpad pan
    assert not np.allclose(plotter.camera_position[1], target)
    assert not canvas.view.ortho
    numpad(canvas, Qt.Key.Key_5)                       # 5 toggles the projection, by choice
    assert canvas.view.ortho and plotter.camera.parallel_projection
    numpad(canvas, Qt.Key.Key_4)                       # so turning keeps it orthographic
    assert canvas.view.ortho
    numpad(canvas, Qt.Key.Key_5)
    assert not canvas.view.ortho
    before = canvas.view.distance
    numpad(canvas, Qt.Key.Key_Plus)
    assert canvas.view.distance < before
    numpad(canvas, Qt.Key.Key_Minus)
    assert canvas.view.distance == pytest.approx(before)
    before = canvas.view.azimuth
    numpad(canvas, Qt.Key.Key_9)                       # half a turn about z
    assert (canvas.view.azimuth - before) % 360 == pytest.approx(180)
    numpad(canvas, Qt.Key.Key_Period)                  # the selected site (3) in sight
    assert np.allclose(canvas.view.target, CLUSTER["positions"][3])
    QTest.keyClick(canvas, Qt.Key.Key_Home)            # everything in sight
    assert np.allclose(canvas.view.target, [0.5, 0.5, 0.5])


def test_the_view_menu_and_names(qapp, qtbot):
    view = pyvista_view.SceneView("scene")
    qtbot.addWidget(view)
    view.resize(500, 400)
    view.show()
    view.show_scene(CLUSTER)
    assert view.view_button.text() == "View: User Perspective"
    view.view_actions["top"].trigger()
    assert view.view_button.text() == "View: Top Orthographic"
    assert view.view_actions["orthographic"].isChecked()
    view.view_actions["orthographic"].trigger()          # unchecked: perspective again
    assert view.view_button.text() == "View: Top Perspective"
    for name in pyvista_view.VIEW_NAMES:
        assert view.set_view(name) == name
    with pytest.raises(ValueError, match="unknown view"):
        view.set_view("sideways")
    view.set_view("reset")
    assert view.view_button.text() == "View: User Perspective"


def distance_of(camera):
    return float(np.linalg.norm(np.subtract(camera[0], camera[1])))


def test_the_window_draws_in_3d_with_pyvista(window, qtbot, shot):
    session, structure = window.session, window.structure
    assert structure.renderer_3d == "matplotlib"          # the default
    assert window.renderer_actions["matplotlib"].isChecked()
    assert session.act("renderer_3d", name="pyvista") == "pyvista"
    assert window.renderer_actions["pyvista"].isChecked()
    assert window.view_state().get("renderer_3d") is None   # a setting, not the document's
    session.do("set_lattice", system="s1", lattice="diamond_lattice")
    settle(qtbot, window)
    assert structure.in_scene and structure.ax is None
    assert structure.stack.currentWidget() is structure.scene
    assert not structure.toolbar.isVisibleTo(structure) and \
        structure.scene.bar.isVisibleTo(structure)
    assert drawn(structure.scene.canvas) > 500
    shot(structure, "diamond_pyvista")
    window.select_sites(all=True)                         # the selection shows in the scene
    assert "selection" in structure.scene.canvas.plotter.actors
    structure.scene.canvas.drag((200, 150), (260, 150))
    turned = structure.scene.canvas.plotter.camera_position
    session.act("theme", name="dark")                     # drawn again, the camera kept
    pixels = structure.scene.canvas.pixels()
    assert pixels[0, 0].sum() < 150
    assert np.allclose(structure.scene.canvas.plotter.camera_position[0], turned[0])
    session.act("theme", name="light")
    session.act("renderer_3d", name="matplotlib")
    assert not structure.in_scene and isinstance(structure.ax, Axes3D)
    assert structure.toolbar.isVisibleTo(structure)
    session.act("renderer_3d", name="pyvista")
    session.do("set_lattice", system="s1", lattice="honeycomb_lattice")
    settle(qtbot, window)
    assert not structure.in_scene                          # flat: drawn flat
    calc = session.do("add_calculation", system="s1", kind="magnetization", params={"nk": 4})
    view = run(window, qtbot, calc)
    assert not view.in_scene and view.ax is not None       # flat, in auto
    assert view._shown_by[view.pick_tools["box"]].isVisible()
    flat = view.ax
    session.act("renderer_3d", name="matplotlib")          # a flat drawing is not redrawn
    session.act("renderer_3d", name="pyvista")
    assert view.ax is flat
    session.act("projection", name="3d")                   # the 3D box, for the results too
    assert structure.in_scene and view.in_scene and view.ax is None
    assert "arrows" in view.scene.canvas.plotter.actors    # the Neel state, as arrows
    assert not any(view._shown_by[b].isVisible() for b in view.pick_tools.values())
    assert not any(a.isVisible() for a in view._navigation)   # the scene has its own bar
    shot(view, "magnetization_pyvista")
    session.act("renderer_3d", name="matplotlib")          # mplot3d, the same projection
    assert isinstance(view.ax, Axes3D) and not view.in_scene
    assert all(a.isVisible() for a in view._navigation)
    session.act("renderer_3d", name="pyvista")
    session.act("projection", name="auto")
    assert not view.in_scene and not structure.in_scene
    session.act("renderer_3d", name="matplotlib")


def test_the_keys_and_the_action_move_the_scene_of_the_window(window, qtbot):
    session, structure = window.session, window.structure
    session.act("renderer_3d", name="pyvista")
    session.do("set_lattice", system="s1", lattice="diamond_lattice")
    settle(qtbot, window)
    canvas = structure.scene.canvas
    assert structure.in_scene
    window.viewport.setCurrentIndex(0)             # the Structure tab, not a result's
    window.activateWindow()
    canvas.setFocus()
    qtbot.waitUntil(lambda: canvas.hasFocus(), timeout=5000)
    numpad(canvas, Qt.Key.Key_3)          # the right view: the numpad, not the digit's shortcut
    assert canvas.view.description() == "Right Orthographic"
    QTest.keyClick(canvas, Qt.Key.Key_3)  # the digit zooms to the selection (all, when none)
    assert canvas.view.description() == "Right Orthographic"
    before = canvas.view.distance
    QTest.keyClick(canvas, Qt.Key.Key_Plus)
    assert canvas.view.distance < before
    QTest.keyClick(canvas, Qt.Key.Key_Minus)
    assert canvas.view.distance == pytest.approx(before)
    target = canvas.view.target.copy()
    QTest.keyClick(canvas, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
    assert not np.allclose(canvas.view.target, target)      # Ctrl and the arrows pan
    QTest.keyClick(canvas, Qt.Key.Key_Home)                 # the window's own Home
    assert np.allclose(canvas.view.target, structure.scene.canvas.view.target)
    assert session.act("view_3d", name="top") == "Top Orthographic"
    assert session.act("view_3d", name="perspective") == "Top Perspective"
    assert session.act("view_3d", name="reset") == "User Perspective"
    with pytest.raises(ValueError, match="unknown view"):
        session.act("view_3d", name="sideways")
    with pytest.raises(ValueError, match="no result view"):
        session.act("view_3d", name="top", calculation="c99")
    session.act("renderer_3d", name="matplotlib")
    with pytest.raises(ValueError, match="nothing is drawn in 3D"):
        session.act("view_3d", name="top")
    session.act("renderer_3d", name="pyvista")
    session.do("set_lattice", system="s1", lattice="honeycomb_lattice")
    settle(qtbot, window)
    session.act("renderer_3d", name="matplotlib")


def test_pyvista_is_the_default_of_the_program_when_it_can_draw(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("GUIQULA_CONFIG_DIR", str(tmp_path))
    window = build_main_window(use_settings=True)
    try:
        assert window.structure.renderer_3d == "pyvista"
        assert window.renderer_actions["pyvista"].isChecked()
    finally:
        window.close()
    # without pyvista, and never chosen: matplotlib, and nothing to complain about
    monkeypatch.setattr(pyvista_view, "available", lambda: False)
    monkeypatch.setattr(pyvista_view, "unavailable_reason", lambda: "pyvista is not installed")
    window = build_main_window(use_settings=True)
    try:
        assert window.structure.renderer_3d == "matplotlib"
        assert "not installed" not in window.log.toPlainText()
    finally:
        window.close()
    # chosen by the user and gone since: matplotlib, and the window says so
    settings.put("renderer_3d", "pyvista")
    window = build_main_window(use_settings=True)
    try:
        assert window.structure.renderer_3d == "matplotlib"
        assert "not installed" in window.log.toPlainText()
    finally:
        window.close()


def test_without_pyvista_the_drawing_stays_with_matplotlib(window, qtbot, monkeypatch):
    session, structure = window.session, window.structure
    monkeypatch.setattr(pyvista_view, "available", lambda: False)
    monkeypatch.setattr(pyvista_view, "unavailable_reason", lambda: "pyvista is not installed")
    with pytest.raises(ValueError, match="not installed"):
        session.act("renderer_3d", name="pyvista")
    assert structure.renderer_3d == "matplotlib"
    assert window.renderer_actions["matplotlib"].isChecked()     # the menu says so
    assert not window.renderer_actions["pyvista"].isEnabled()
    monkeypatch.undo()

    def broken(*args, **kwargs):
        raise RuntimeError("no OpenGL here")
    monkeypatch.setattr(pyvista_view, "draw_scene", broken)
    session.act("renderer_3d", name="pyvista")
    assert window.renderer_actions["pyvista"].isEnabled()
    session.act("projection", name="3d")
    assert not structure.in_scene and isinstance(structure.ax, Axes3D)
    assert "pyvista could not draw (no OpenGL here)" in structure.caption.text()
    session.act("projection", name="auto")
    session.act("renderer_3d", name="matplotlib")


def test_the_choice_is_a_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("GUIQULA_CONFIG_DIR", str(tmp_path))
    assert settings.CHOICES["renderer_3d"] == pyvista_view.RENDERERS
    assert settings.load()["renderer_3d"] == "pyvista"       # the default, when it can draw
    assert not settings.chosen("renderer_3d")
    settings.put("renderer_3d", "matplotlib")
    assert settings.load()["renderer_3d"] == "matplotlib" and settings.chosen("renderer_3d")
    settings.put("renderer_3d", "pyvista")
    assert settings.load()["renderer_3d"] == "pyvista"
    with pytest.raises(settings.SettingsError):
        settings.put("renderer_3d", "vtk")
