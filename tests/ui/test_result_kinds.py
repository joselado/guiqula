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
    # the box and the lasso pick on the flat drawing only; a widget on a toolbar is hidden
    # by its action (Qt ignores its setVisible)
    assert not any(view._shown_by[view.pick_tools[t]].isVisible() for t in ("box", "lasso"))
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


def test_a_map_with_a_value_that_is_not_a_number(qapp):
    """One NaN in a 2D sweep's map (a point that gave no number) turned the
    map into a sparse scatter of squares, and a symmetric one got a colour
    bar of -0.1 to 0.1: the cell is left blank now, the rest is a map."""
    from matplotlib.figure import Figure
    from guiqula.core.results import Result
    from guiqula.ui import plots
    x, y = np.linspace(0, 1, 11), np.linspace(0, 2, 21)
    c = np.add.outer(np.sin(3 * x), np.cos(2 * y))              # c[i, j] at (x[i], y[j])
    c[5, 10] = np.nan
    for symmetric in (False, True):
        result = Result(calculation="c3", kind="sweep", key="k", params={},
                        arrays={"value": x, "value2": y, "gap": c},
                        plot={"kind": "heatmap", "x": "value", "y": "value2", "c": "gap",
                              "symmetric": symmetric})
        figure = Figure()
        ax, _ = plots.draw(figure, result)
        assert [type(a).__name__ for a in ax.collections] == ["QuadMesh"]
        assert ax.collections[0].get_array().mask.sum() == 1          # the one blank cell
        low, high = figure.axes[1].get_ylim()
        assert np.isclose(high, np.nanmax(np.abs(c)) if symmetric else np.nanmax(c))
    assert plots.grid_of(np.r_[x, 0.0], np.r_[x, 0.0], np.r_[x, 1.0]) is None   # not a grid


def test_the_difference_of_two_coloured_band_structures(qapp):
    """A difference replaces the coloured bands with curves: the colour bar
    of the bands ('sz') stayed beside them, in the view and in exports."""
    from matplotlib.figure import Figure
    from guiqula.core.results import Result
    from guiqula.ui import plots
    k = np.linspace(0, 1, 20)

    def bands(shift):
        energies = np.column_stack([np.cos(np.pi * k) + shift, -np.cos(np.pi * k)])
        return Result(calculation="c1", kind="bands", key=str(shift), params={},
                      arrays={"k": k, "energies": energies, "sz": np.sign(energies)},
                      plot={"kind": "colored_scatter", "x": "k", "y": "energies", "c": "sz"})
    figure = Figure()
    ax, points = plots.draw(figure, bands(0.0), overlays=[("c3", bands(0.1), "difference")])
    assert figure.axes == [ax] and not ax.collections
    assert np.allclose(ax.lines[0].get_ydata(), -0.1)
    assert ax.get_legend().get_texts()[0].get_text() == "c1 − c3"
    assert len(points[0]) == 40 and points[2] is None


def test_overlays(window, qtbot, shot):
    """Two densities of states on one axes, then their difference (13.11)."""
    session = window.session
    session.act("load", path="honeycomb_zeeman_rashba")
    settle(qtbot, window)
    other = session.do("add_calculation", system="s1", kind="dos",
                       params={"operator": "sz", "ne": 400})
    for calc in ("c2", other):
        view = run(window, qtbot, calc)
    view = window.plots["c2"]
    view.overlay.menu().aboutToShow.emit()
    names = [a.objectName() for a in view.overlay.menu().actions()]
    assert f"overlayWith_{other}" in names and f"difference_{other}" in names
    next(a for a in view.overlay.menu().actions()
         if a.objectName() == f"overlayWith_{other}").trigger()
    assert window.overlays["c2"] == [(other, "overlay")]
    assert [line.get_label() for line in view.ax.get_legend().get_lines()] == ["c2", other]
    shot(view, "overlay")
    session.act("overlay", calc="c2", other=other, mode="difference")
    assert window.overlays["c2"] == [(other, "difference")]
    assert view.ax.get_legend().get_texts()[0].get_text() == f"c2 − {other}"
    difference = view.result.arrays["dos"] - session.result(other).arrays["dos"]
    assert np.allclose(view.ax.lines[0].get_ydata(), difference)
    assert window.view_state()["overlays"] == {"c2": [[other, "difference"]]}
    with pytest.raises(Exception, match="cannot overlay itself"):
        session.act("overlay", calc="c2", other="c2")
    session.act("overlay", calc="c2")
    assert "c2" not in window.overlays and view.ax.get_legend() is None
    session.do("remove", entry=other)


def test_sliders_and_a_sweep_in_the_window(window, qtbot, shot):
    """A slider on the Rashba coupling: one drag is one undo step, the
    value follows undo; a sweep of the gap against it, drawn as a curve."""
    session = window.session
    session.act("load", path="honeycomb_zeeman_rashba")
    settle(qtbot, window)
    index = session.act("slider", entry="t2", param="c", minimum=0.0, maximum=0.4)
    zeeman = session.act("slider", entry="t1", param="m", component=0, minimum=-1, maximum=1)
    row = window.sliders_panel.rows[index]
    assert row.value.text() == "0.1"
    undo_depth = len(session.dispatcher._undo)
    for value in (0.2, 0.3):                                 # a drag
        window.set_slider(index, value, dragging=True)
    window.set_slider(index, 0.35)                           # released
    assert session.document.find("t2")[-1].params["c"] == pytest.approx(0.35)
    assert len(session.dispatcher._undo) == undo_depth + 1
    session.undo()
    assert session.document.find("t2")[-1].params["c"] == pytest.approx(0.1)
    assert window.sliders_panel.rows[index].value.text() == "0.1"
    session.act("set_slider", index=zeeman, value=0.5)
    assert session.document.find("t1")[-1].params["m"][0] == pytest.approx(0.5)
    assert window.view_state()["sliders"][1] == {"entry": "t1", "param": "m", "component": 0,
                                                 "min": -1.0, "max": 1.0}
    with pytest.raises(Exception, match="no parameter"):
        session.act("slider", entry="t2", param="nope")
    gap = session.do("add_calculation", system="s1", kind="gap")
    sweep = session.do("add_calculation", system="s1", kind="sweep", params={
        "calculation": gap, "entry": "t2", "param": "c", "start": 0.0, "stop": 0.3, "steps": 4})
    view = run(window, qtbot, sweep)
    assert view.result.plot["kind"] == "lines" and len(view.points[0]) == 4
    shot(window, "sliders_sweep")
    session.act("remove_slider", index=zeeman)
    session.act("remove_slider", index=index)
    assert window.sliders == []
