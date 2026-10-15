"""The Brillouin-zone canvas (decision 13.9) in the window of a k-path
(phase 9, part A): the zone and the high-symmetry points of the system, the
k-path drawn and edited (a vertex added, dragged onto a special point, the
default path back), the Fermi surface underneath; the bands follow. A 3D
crystal's zone is drawn in 3D (decision 236). The k-path row of a
calculation's form and the K-paths section of the outliner."""
import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent

from guiqula.ui import kspace as tools
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.start_session("haldane_chern", warm=False)
    yield window
    window.close()


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)


def test_hexagonal_zone():
    a = np.array([[1.5, 0.866025, 0], [-1.5, 0.866025, 0], [0, 0, 1]])
    b = np.linalg.inv(a).T                           # pyqula's: a_i . b_j = delta_ij
    zone = tools.brillouin_zone(b, 2)
    assert len(zone) == 6                            # a hexagon
    radii = np.linalg.norm(zone, axis=1)
    assert np.allclose(radii, radii[0], atol=1e-6)
    assert np.isclose(radii[0], np.linalg.norm(b[0, :2]) / np.sqrt(3), atol=1e-6)
    assert np.allclose(tools.plane_basis(b), np.eye(3)[:2])      # drawn in x and y


def test_a_three_dimensional_zone_is_drawn_whole():
    """The pyrochlore (fcc) as the worker hands it: the zone is the
    truncated octahedron, 14 faces, its volume the reciprocal cell's, and
    Z, R, A, B, off the plane k3 = 0, are points of it too."""
    from guiqula.ui import kspace3d
    s = 1 / (2 * np.sqrt(2))
    b = s * np.array([[-1.0, 1.0, -1.0], [1.0, 1.0, 1.0], [-1.0, -1.0, 1.0]])
    faces = tools.brillouin_zone_3d(b)
    assert sorted(len(f) for f in faces) == [4] * 6 + [6] * 8
    volume = 0.0
    for face in faces:
        normal = np.cross(face[1] - face[0], face[2] - face[0])
        normal /= np.linalg.norm(normal)
        area = np.linalg.norm(sum(np.cross(face[i], face[(i + 1) % len(face)])
                                  for i in range(len(face)))) / 2
        volume += area * abs(face[0].dot(normal)) / 3
    assert np.isclose(volume, abs(np.linalg.det(b)))
    special = {"G": [0.0, 0.0, 0.0], "M": [0.5, 0.0, 0.0], "M2": [0.0, 0.5, 0.0],
               "M3": [0.5, 0.5, 0.0], "Z": [0.0, 0.0, 0.5], "R": [0.5, 0.5, 0.5],
               "A": [0.5, 0.0, 0.5], "B": [0.0, 0.5, 0.5]}
    kspace = {"reciprocal": b, "special": special, "dimensionality": 3}
    names = [name for name, _, _ in kspace3d.special_points(kspace)]
    assert {"G", "Z", "R", "A", "B"} <= set(names)
    path = kspace3d.path_points(["G", "Z"], kspace)
    shift = path[1] @ np.linalg.inv(b) - [0.0, 0.0, 0.5]       # an image of Z, nearest Γ
    assert np.allclose(shift, np.round(shift), atol=1e-9)


def zone(window, calc="c1"):
    """The view of the zone window of the k-path a calculation walks."""
    out = window.kpath_window(calculation=calc)
    return window.kpath_windows[out["kpath"]].view, out["kpath"]


def test_the_path_on_the_zone(window, qtbot, shot):
    session = window.session
    settle(qtbot, window)
    assert "kspace" not in [window.viewport.tabText(i).lower().replace("-", "")
                            for i in range(window.viewport.count())]    # no k-space tab
    view, k = zone(window)
    assert view.objectName() == f"kspaceView_{k}"
    assert window.findChild(type(view.window()), f"kspaceWindow_{k}") is view.window()
    assert view.bar.objectName() == f"kspaceBar_{k}" and view.canvas.toolbar is view.toolbar
    assert view.kpath is None                                    # the default path
    assert {"G", "K", "M"} <= set(view.kspace["special"])
    special = tools.special_images(view.kspace)
    b = view.kspace["reciprocal"]

    def drawn():
        return tools.to_plane(session.document.kpath(k).vertices, b)
    view.add.setChecked(True)
    view.add_point(special["K"] + 0.01)                          # snaps onto K
    assert np.allclose(drawn(), [[0, 0], special["K"]], atol=1e-6)
    view.add_point(special["M"])
    view.add_point((0.0, 0.0))
    assert np.allclose(drawn(), [[0, 0], special["K"], special["M"], [0, 0]], atol=1e-6)
    assert np.allclose(view.vertices, drawn(), atol=1e-6)        # drawn where it was put
    free = special["M"] * 0.5
    view.move_vertex(2, free)                                    # off the special points
    assert np.allclose(drawn()[2], free, atol=1e-5)
    x, y = view.ax.transData.transform(view.vertices[2])         # drag it back onto M
    mx, my = view.ax.transData.transform(special["M"] + 0.01)
    MouseEvent("button_press_event", view.canvas, x, y, button=1)._process()
    MouseEvent("motion_notify_event", view.canvas, mx, my, button=1)._process()
    MouseEvent("button_release_event", view.canvas, mx, my, button=1)._process()
    assert np.allclose(drawn()[2], special["M"], atol=1e-6)
    session.run_calculation("c1", wait=True, timeout=300)
    qtbot.waitUntil(lambda: session.result("c1") is not None, timeout=10_000)
    ticks = session.result("c1").plot["xticks"]
    assert [name for _, name in ticks] == ["Γ", "K", "M", "Γ"]
    surface = session.do("add_calculation", system="s1", kind="fermi_surface",
                         params={"energy": 0.5, "nk": 30, "delta": 0.1})
    session.run_calculation(surface, wait=True, timeout=300)
    qtbot.waitUntil(lambda: "Fermi surface" in view.caption.text(), timeout=20_000)
    shot(view, "zone")
    view.default.click()
    assert session.document.kpath(k).vertices == []


def test_a_click_on_a_vertex_passes_through_it_again(window, qtbot):
    """A press released where it started, on a vertex, adds that point again
    with Add points on (a path can go back to Γ); a drag still moves it."""
    session = window.session
    settle(qtbot, window)
    view, k = zone(window)
    special = tools.special_images(view.kspace)
    b = view.kspace["reciprocal"]

    def path():
        return session.document.kpath(k).vertices

    def click(point, jitter=0.0):
        x, y = view.ax.transData.transform(point)
        MouseEvent("button_press_event", view.canvas, x, y, button=1)._process()
        MouseEvent("motion_notify_event", view.canvas, x + jitter, y, button=1)._process()
        MouseEvent("button_release_event", view.canvas, x + jitter, y, button=1)._process()

    view.add.setChecked(True)
    view.bar.pan_button.click()                          # the bar's Pan (P3)
    qtbot.waitUntil(lambda: not view.add.isChecked())    # pan takes the clicks: Add shows off
    assert view.bar.pan_button.isChecked()
    view.add.setChecked(True)                            # and turns pan off again
    assert str(view.toolbar.mode) == "" and not view.bar.pan_button.isChecked()
    click(special["K"])                                  # a new path starts at Γ
    click(special["M"])
    click((0.0, 0.0), jitter=2)                          # on the Γ vertex, a click: again
    assert np.allclose(tools.to_plane(path(), b), [[0, 0], special["K"], special["M"], [0, 0]],
                       atol=1e-6)
    click(special["K"])                                  # and through K a second time
    assert len(path()) == 5 and np.allclose(tools.to_plane(path(), b)[4], special["K"],
                                            atol=1e-6)
    view.add.setChecked(False)                           # without Add points: nothing
    click(special["M"])
    assert len(path()) == 5
    view.default.click()


def test_a_shared_kpath_drives_every_calculation_walking_it(window, qtbot):
    """One k-path, two calculations (the bands and a second band structure
    added after them): an edit in the zone changes both, Make single-user
    gives one a copy, and the form's row says who walks what."""
    session = window.session
    settle(qtbot, window)
    c = session.do("add_calculation", system="s1", kind="bands")
    k = session.document.calculation("c1").params["kpath"]
    assert session.document.calculation(c).params["kpath"] == k
    window.select(c)
    editor = window.properties.form.editors["kpath"]
    assert editor.combo.objectName() == "kpath_kpath"
    assert "c1" in editor.combo.currentText() and c in editor.combo.currentText()
    assert editor.single.isEnabled()                         # walked by two
    view, _ = zone(window, c)
    view.add_point(tools.special_images(view.kspace)["K"])
    assert session.document.kpath(k).vertices[-1] == [1 / 3, 1 / 3, 0.0] or \
        len(session.document.kpath(k).vertices) == 2
    editor.action.emit("single")                             # Make single-user
    own = session.document.calculation(c).params["kpath"]
    assert own != k and session.document.kpath(own).vertices == \
        session.document.kpath(k).vertices
    assert window.outliner.item(own) is not None             # a row in K-paths
    assert c in window.outliner.item(own).text(1)
    session.do("set_kpath", kpath=k, vertices=[])
    session.do("remove", entry=c)
    session.do("remove", entry=own)


def test_a_system_shows_its_zone(window, qtbot):
    """Show Brillouin zone (a system's context menu): the window of the
    k-path of its last calculation walking one."""
    settle(qtbot, window)
    out = window.kpath_window(system="s1")
    assert out["kpath"] == window.session.document.calculation("c1").params["kpath"]
    assert out["window"] == f"kspaceWindow_{out['kpath']}"


def test_a_click_on_the_3d_zone_adds_its_point(window, qtbot):
    """A cubic crystal's zone in 3D (mplot3d): a click on the projection of a
    high-symmetry point adds it to the path by its label."""
    from guiqula.ui import kspace3d
    session = window.session
    s2 = session.do("add_system", lattice="cubic_lattice")
    c = session.do("add_calculation", system=s2, kind="bands")
    settle(qtbot, window)
    view, k = zone(window, c)
    qtbot.waitUntil(lambda: view.three_d and view.ax is not None, timeout=20_000)
    assert view.ax.name == "3d" and "in 3D" in view.caption.text()
    view.add.setChecked(True)
    view.canvas.draw()
    name, _, point = next(p for p in view.points_3d if p[0] == "R")
    x, y = kspace3d.screen_mpl(view.ax, point)[0]
    MouseEvent("button_press_event", view.canvas, x, y, button=1)._process()
    MouseEvent("button_release_event", view.canvas, x, y, button=1)._process()
    assert session.document.kpath(k).vertices == ["G", "R"]     # a new path starts at Γ
    session.do("remove", entry=c)
    session.do("remove", entry=k)
    session.do("remove", entry=s2)
