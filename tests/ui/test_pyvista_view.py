"""The 3D drawing with pyvista (View > 3D drawing, ui/pyvista_view.py),
driven offscreen: the scene renders off-screen, the mouse (VTK's events,
sent without a mouse) turns and zooms it as in a pyvista window, the canvas
and the results on the atoms draw with it, the canvas's 3D box decides for
the results too (a magnetization on a flat lattice drawn in 3D), and a
pyvista that is missing or cannot draw leaves the drawing to mplot3d."""
import numpy as np
import pytest
from mpl_toolkits.mplot3d import Axes3D

pytest.importorskip("pyvista")

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


def test_the_scene_turns_and_zooms_as_in_pyvista(qapp, qtbot, tmp_path, shot):
    view = pyvista_view.SceneView("scene")
    qtbot.addWidget(view)
    view.resize(500, 400)
    view.show()
    view.show_scene(CLUSTER, selected=[0])
    canvas, plotter = view.canvas, view.canvas.plotter
    assert drawn(canvas) > 500                       # the sites and bonds are there
    assert plotter.actors.keys() >= {"sites", "bonds", "selection"}
    first = plotter.camera_position
    canvas.drag((250, 200), (330, 170))              # a drag turns the view
    turned = plotter.camera_position
    assert not np.allclose(first[0], turned[0])
    assert np.allclose(first[1], turned[1])          # about the same point
    assert distance(plotter) == pytest.approx(distance_of(first), rel=1e-6)
    for _ in range(3):
        canvas.send("MouseWheelForward", 250, 200)   # the wheel zooms in
    assert distance(plotter) < 0.9 * distance_of(first)
    canvas.drag((250, 200), (280, 200), shift=True)  # shift+drag pans
    assert not np.allclose(plotter.camera_position[1], turned[1])
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
    assert settings.load()["renderer_3d"] == "matplotlib"
    settings.put("renderer_3d", "pyvista")
    assert settings.load()["renderer_3d"] == "pyvista"
    with pytest.raises(settings.SettingsError):
        settings.put("renderer_3d", "vtk")
