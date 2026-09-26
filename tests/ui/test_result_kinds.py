"""Phase 4 plot kinds and the 3D canvas, driven offscreen: a calculation of
each new plot kind runs in the batch worker and its result view draws it
(PLAN.md 3.4); a geometry that is not flat is drawn in 3D and the 3D box
switches it back to the flat drawing (answer 9 to the phase-2 report)."""
import numpy as np
import pytest
from mpl_toolkits.mplot3d import Axes3D

from guiqula.ui.app import build_main_window
from guiqula.ui.plots import scalar_rows


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
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


# kind, parameters, plot kind drawn
CASES = [
    ("ldos", {"energy": 0.3, "delta": 0.1, "nk": 4}, "structure_scalar"),
    ("magnetization", {"nk": 4}, "structure_vector"),
    ("chern", {"nk": 8}, "scalar"),
    ("fermi_surface", {"energy": 0.6, "nk": 16, "delta": 0.1}, "heatmap"),
    ("spectral_function", {"ne": 30, "nk": 20, "delta": 0.1}, "heatmap"),
    ("berry_curvature", {"nk": 8}, "heatmap"),
]


@pytest.mark.parametrize("kind, params, plot", CASES, ids=[c[0] for c in CASES])
def test_plot_kinds(window, qtbot, shot, kind, params, plot):
    settle(qtbot, window)
    calc = window.session.do("add_calculation", system="s1", kind=kind, params=params)
    view = run(window, qtbot, calc)
    assert view.result.plot["kind"] == plot
    if plot == "scalar":
        rows = scalar_rows(view.result)
        assert rows[0][0] == "Chern number" and float(rows[0][1]) == pytest.approx(
            float(view.result.arrays["chern"]))
        texts = [t.get_text() for t in view.ax.texts]
        assert "Chern number" in texts
        window.outliner.refresh(window.session)            # the number is in the outliner too
        assert window.outliner.item(calc).text(1) == rows[0][1]
    else:
        assert len(view.points[0]) > 0
        i = 0
        px, py = view.ax.transData.transform((view.points[0][i], view.points[1][i]))
        assert view.point_near(px, py) is not None
        text = view.readout_text(view.point_near(px, py))
        assert text.startswith("site ") if plot.startswith("structure") else "·" in text
    if plot.startswith("structure"):
        assert view.result.structure is not None
        assert len(view.result.structure["positions"]) == len(view.points[0])
    shot(view, kind)


def test_three_dimensional_geometry(window, qtbot, shot):
    session = window.session
    session.act("load", path="honeycomb_zeeman_rashba")
    session.do("set_lattice", system="s1", lattice="diamond_lattice")
    window.select("s1")
    settle(qtbot, window)
    structure = window.structure
    assert isinstance(structure.ax, Axes3D) and structure.box_3d.isChecked()
    assert structure._selector is None                      # the tools work in xy
    shot(structure, "diamond_3d")
    window.session.act("projection", name="xy")
    assert not isinstance(structure.ax, Axes3D) and not structure.box_3d.isChecked()
    assert window.view_state()["projection"] == "xy"
    window.select_sites(all=True)
    assert len(structure.selected()) == len(window.builds["s1"]["positions"])
    window.set_projection("3d")
    assert isinstance(structure.ax, Axes3D)
    chosen = structure._selection_artist._offsets3d
    assert len(chosen[0]) == len(structure.selected())     # the selection shows in 3D
    window.set_projection("auto")
    calc = session.do("add_calculation", system="s1", kind="magnetization", params={"nk": 3})
    view = run(window, qtbot, calc)
    assert isinstance(view.ax, Axes3D)                      # the result follows the geometry
    shot(view, "magnetization_3d")
    session.do("set_lattice", system="s1", lattice="honeycomb_lattice")
    settle(qtbot, window)
    assert not isinstance(structure.ax, Axes3D)             # flat again: drawn flat


def test_buckled_layers_are_not_flat():
    from guiqula.ui.structure import is_flat
    flat = {"positions": np.array([[0, 0, 0.0], [1, 0, 0.0]]), "dimensionality": 2}
    buckled = {"positions": np.array([[0, 0, 0.0], [1, 0, 0.3]]), "dimensionality": 2}
    bulk = {"positions": np.array([[0, 0, 0.0]]), "dimensionality": 3}
    assert is_flat(flat) and not is_flat(buckled) and not is_flat(bulk)
