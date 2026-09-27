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


def test_the_path_on_the_zone(window, qtbot, shot):
    session = window.session
    settle(qtbot, window)
    window.viewport.setCurrentIndex(1)
    assert window.current_tab() == "kspace"
    view = window.kspace_view
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
    next(a for a in view.toolbar.actions() if a.text() == "Pan").trigger()
    qtbot.waitUntil(lambda: not view.add.isChecked())    # pan takes the clicks: Add shows off
    view.add.setChecked(True)                            # and turns pan off again
    assert str(view.toolbar.mode) == ""
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
