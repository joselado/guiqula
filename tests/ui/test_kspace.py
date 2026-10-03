"""The Brillouin-zone canvas (decision 13.9): the zone and the
high-symmetry points of the current system, the k-path of a calculation
drawn and edited (a vertex added, dragged onto a special point, the
default path back), the Fermi surface underneath; the bands follow."""
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


def test_a_three_dimensional_zone_is_its_k3_0_cut():
    """The pyrochlore (fcc) as the worker hands it: b1 and b2 leave the xy
    plane, and Z, R, A, B have k3 = 1/2. The canvas drew the xy projection:
    'Z' sat on an image of M2, a click on it stored M2, and the zone was a
    square. It is the k3 = 0 cut now, with the points in that plane only."""
    import itertools
    from guiqula.registry import kpaths
    s = 1 / (2 * np.sqrt(2))
    b = s * np.array([[-1.0, 1.0, -1.0], [1.0, 1.0, 1.0], [-1.0, -1.0, 1.0]])
    special = {"G": [0.0, 0.0, 0.0], "M": [0.5, 0.0, 0.0], "M2": [0.0, 0.5, 0.0],
               "M3": [0.5, 0.5, 0.0], "Z": [0.0, 0.0, 0.5], "R": [0.5, 0.5, 0.5],
               "A": [0.5, 0.0, 0.5], "B": [0.0, 0.5, 0.5]}
    kspace = {"reciprocal": b, "special": special, "dimensionality": 3,
              "default_path": np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.5]])}
    drawn = tools.special_images(kspace)
    assert set(drawn) == {"G", "M", "M2", "M3"}
    clicked = []
    for name, point in drawn.items():                    # a click on a label stores its point
        stored = np.array(tools.snap(point + 0.01, kspace))
        shift = stored - special[name]
        assert stored[2] == 0 and np.allclose(shift, np.round(shift), atol=1e-9)
        assert np.allclose(tools.to_plane(stored, b)[0], point)
        clicked.append(list(stored))
    assert kpaths.tick_names(b, 3, clicked, special) == \
        [tools.NAMES.get(name, name) for name in drawn]  # and the bands name it so
    zone = tools.brillouin_zone(b, 3)
    assert len(zone) == 6                                # a hexagon, not a square
    reciprocal = [np.array(n) @ b for n in itertools.product(range(-2, 3), repeat=3) if any(n)]
    for corner in zone @ tools.plane_basis(b):           # in 3D: a corner of the cell's cut
        margins = [g.dot(g) / 2 - corner.dot(g) for g in reciprocal]
        assert min(margins) > -1e-9 and sum(abs(m) < 1e-9 for m in margins) >= 2
    assert np.allclose(tools.to_plane(tools.to_reduced(zone[0], b), b)[0], zone[0])


def test_the_path_on_the_zone(window, qtbot, shot):
    session = window.session
    settle(qtbot, window)
    window.viewport.setCurrentIndex(1)
    assert window.current_tab() == "kspace"
    view = window.kspace_view
    assert view.bar.objectName() == "kspaceBar" and view.canvas.toolbar is view.toolbar
    assert view.calc == "c1" and view.kpath is None             # the bands, default path
    assert {"G", "K", "M"} <= set(view.kspace["special"])
    special = tools.special_images(view.kspace)
    b = view.kspace["reciprocal"]

    def drawn():
        return tools.to_plane(session.document.calculation("c1").params["kpath"], b)
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
    assert session.document.calculation("c1").params["kpath"] is None
    window.viewport.setCurrentIndex(1)          # running c1 brought its result forward
    assert window.view_state()["tab"] == "kspace"


def test_a_click_on_a_vertex_passes_through_it_again(window, qtbot):
    """A press released where it started, on a vertex, adds that point again
    with Add points on (a path can go back to Γ); a drag still moves it."""
    session = window.session
    settle(qtbot, window)
    window.viewport.setCurrentIndex(1)
    view = window.kspace_view
    special = tools.special_images(view.kspace)
    b = view.kspace["reciprocal"]

    def path():
        return session.document.calculation("c1").params["kpath"]

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
