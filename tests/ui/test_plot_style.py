"""The style of a result plot (decisions 164 to 169): the catalogue of
ui/plotstyle.py, each plot kind drawn in a style, the Style popup of a
result view and the plot_style action, kept in the view state and used by
the export."""
import numpy as np
import pytest
from matplotlib.figure import Figure

from guiqula.core.results import Result
from guiqula.ui import plots, plotstyle
from guiqula.ui.app import build_main_window


def test_the_catalogue_is_well_formed():
    """Every option has its label, its type, a default within its range,
    choices matplotlib knows, and a tooltip; a scalar result has none."""
    from matplotlib import colormaps
    assert set(plotstyle.OPTIONS) == set(plots.KINDS)
    assert plotstyle.options("scalar") == [] and plotstyle.options("unknown") == []
    for kind, options in plotstyle.OPTIONS.items():
        assert len({o["name"] for o in options}) == len(options)
        for opt in options:
            assert opt["label"] and opt["tip"] and opt["type"] in plotstyle.TYPES
            if opt["type"] == "number":
                assert opt["minimum"] <= opt["default"] <= opt["maximum"]
                assert opt["step"] > 0
            elif opt["type"] == "choice":
                assert opt["default"] is None or opt["default"] in opt["choices"]
                for choice in opt["choices"]:
                    assert choice in colormaps
            elif opt["type"] == "color":
                assert opt["default"] is None
            else:
                assert isinstance(opt["default"], bool)


def test_clean_keeps_what_differs_and_refuses_the_rest():
    assert plotstyle.clean("lines", {}) == {}
    assert plotstyle.clean("lines", {"linewidth": 1.2, "color": None, "dots": False}) == {}
    assert plotstyle.clean("lines", {"linewidth": 3, "color": "#ff0000"}) == \
        {"linewidth": 3.0, "color": "#ff0000"}
    with pytest.raises(ValueError, match="between 0.2 and 8"):
        plotstyle.clean("lines", {"linewidth": 100})
    with pytest.raises(ValueError, match="no style option 'size'"):
        plotstyle.clean("lines", {"size": 3})
    with pytest.raises(ValueError, match="colour"):
        plotstyle.clean("lines", {"color": "not a colour"})
    with pytest.raises(ValueError, match="one of"):
        plotstyle.clean("heatmap", {"cmap": "nope"})
    with pytest.raises(ValueError, match="true or false"):
        plotstyle.clean("heatmap", {"smooth": 1})
    # a style saved for another kind is dropped, not an error, when not strict
    assert plotstyle.clean("heatmap", {"linewidth": 3, "cmap": "gray", "saturate": 9},
                           strict=False) == {"cmap": "gray"}
    assert plotstyle.resolve("colored_scatter", {"size": 20})["cmap"] == "coolwarm"


def _curves():
    k = np.linspace(0, 1, 20)
    energies = np.column_stack([np.cos(np.pi * k), -np.cos(np.pi * k)])
    return k, energies


def _chain():
    r = np.array([[i, 0.0, 0.0] for i in range(8)], dtype=float)
    return {"positions": r, "lattice": np.eye(3) * 8, "dimensionality": 0,
            "bonds": np.array([[i, i + 1] for i in range(7)]),
            "image_bonds": np.zeros((0, 5), dtype=int), "sublattice": np.array([1, -1] * 4)}


def test_every_kind_is_drawn_in_its_style(qapp):
    k, energies = _curves()
    lines = Result(calculation="c1", kind="bands", key="", params={},
                   arrays={"k": k, "e": energies}, plot={"kind": "lines", "x": "k", "y": "e"})
    figure = Figure()
    ax, _ = plots.draw(figure, lines, style={"linewidth": 3, "color": "#ff0000", "dots": True,
                                              "fill": True})
    assert ax.lines[0].get_linewidth() == 3 and ax.lines[0].get_color() == "#ff0000"
    assert ax.lines[0].get_marker() == "o" and len(ax.collections) == 2    # the fills
    ax, _ = plots.draw(Figure(), lines, overlays=[("c9", lines, "overlay")],
                       style={"linewidth": 2.4})
    assert ax.lines[0].get_linewidth() == 2.4 and ax.lines[2].get_linewidth() == 2.0

    coloured = Result(calculation="c1", kind="bands", key="", params={},
                      arrays={"k": k, "e": energies, "sz": np.sign(energies)},
                      plot={"kind": "colored_scatter", "x": "k", "y": "e", "c": "sz"})
    ax, _ = plots.draw(Figure(), coloured, style={"size": 30, "cmap": "viridis",
                                                   "saturate": 0.5})
    points = ax.collections[0]
    assert points.get_sizes()[0] == 30 and points.get_cmap().name == "viridis"
    assert points.get_clim() == (-0.5, 0.5)

    x, y = np.linspace(0, 1, 11), np.linspace(0, 2, 21)
    c = np.add.outer(np.sin(3 * x), np.cos(2 * y))
    for symmetric in (True, False):
        heat = Result(calculation="c3", kind="sweep", key="", params={},
                      arrays={"x": x, "y": y, "c": c},
                      plot={"kind": "heatmap", "x": "x", "y": "y", "c": "c",
                            "symmetric": symmetric})
        ax, _ = plots.draw(Figure(), heat, style={"cmap": "gray", "saturate": 0.5,
                                                   "smooth": True})
        mesh = ax.collections[0]
        assert mesh.get_cmap().name == "gray"
        low, high = mesh.get_clim()
        if symmetric:
            assert np.isclose(high, 0.5 * np.abs(c).max()) and np.isclose(low, -high)
        else:
            assert np.isclose(low, c.min()) and np.isclose(high, c.min() + 0.5 * np.ptp(c))
    ax, _ = plots.draw(Figure(), heat)                       # the defaults as before
    assert ax.collections[0].get_cmap().name == "inferno"

    build = _chain()
    scalar = Result(calculation="c4", kind="ldos", key="", params={},
                    arrays={"v": np.linspace(0, 1, 8)},
                    plot={"kind": "structure_scalar", "values": "v"}, structure=build)
    plain, _ = plots.draw(Figure(), scalar)
    assert plots.along_a_line(scalar)                        # a chain: a curve against x
    ax, _ = plots.draw(Figure(), scalar, style={"atom_size": 2, "cmap": "hot"})
    assert ax.collections[0].get_sizes()[0] == 4 * plain.collections[0].get_sizes()[0]
    assert ax.collections[0].get_cmap().name == "hot"
    build["positions"][1, 1] = 1.0                           # not a line any more: the atoms
    ax, _ = plots.draw(Figure(), scalar, style={"atom_size": 2, "cmap": "hot", "bonds": False})
    plain, _ = plots.draw(Figure(), scalar)
    assert len(ax.collections) == len(plain.collections) - 1      # no bonds
    vectors = np.column_stack([np.ones(8), np.zeros(8), np.linspace(-1, 1, 8)])
    vector = Result(calculation="c5", kind="magnetization", key="", params={},
                    arrays={"m": vectors},
                    plot={"kind": "structure_vector", "vectors": "m"}, structure=build)
    ax, _ = plots.draw(Figure(), vector, style={"arrow_length": 2, "arrow_width": 2,
                                                 "arrow_color": "#00ff00", "cmap": "bwr"})
    quiver = next(a for a in ax.collections if type(a).__name__ == "Quiver")
    assert quiver.scale == pytest.approx(1 / 1.6) and quiver.width == pytest.approx(0.012)
    assert tuple(quiver.get_facecolor()[0][:3]) == (0.0, 1.0, 0.0)


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def _settle(qtbot, window):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=120_000)


def _run(window, qtbot, calc):
    window.session.run_calculation(calc, wait=True, timeout=600)
    assert window.session.calc_jobs[calc].status == "done"
    window.show_result(calc)
    qtbot.waitUntil(lambda: window.plots[calc].result is not None, timeout=10_000)
    return window.plots[calc]


def test_the_style_action_the_popup_and_the_view_state(window, qtbot, shot):
    """plot_style draws a result again in its style and keeps the zoom; the
    popup's controls dispatch it; Reset empties it; the view state keeps
    it and restores it; the export draws with it."""
    session = window.session
    _settle(qtbot, window)
    with pytest.raises(Exception, match="run it first"):
        session.act("plot_style", calculation="c2", linewidth=3)
    view = _run(window, qtbot, "c2")                           # a dos: lines
    assert view.style_button.isEnabled() and view.bar.shown(view.style_button)
    view.ax.set_xlim(-1.0, 1.0)                                # a zoom, kept by a restyle
    assert session.act("plot_style", calculation="c2", linewidth=3, color="#ff0000") == \
        {"linewidth": 3.0, "color": "#ff0000"}
    assert view.ax.lines[0].get_linewidth() == 3 and view.ax.get_xlim() == (-1.0, 1.0)
    assert window.plot_styles == {"c2": {"linewidth": 3.0, "color": "#ff0000"}}
    with pytest.raises(Exception, match="no style option"):
        session.act("plot_style", calculation="c2", size=3)
    assert view.ax.lines[0].get_linewidth() == 3               # untouched by the refusal
    # the popup: one control per option, named; a change dispatches the whole style
    view.open_style()
    popup = view.style_popup
    assert popup.isVisible() and set(popup.controls) == {"linewidth", "color", "dots", "fill"}
    assert popup.controls["linewidth"].objectName() == "style_linewidth_c2"
    assert popup.controls["linewidth"].value() == 3 and popup.controls["color"].value == \
        "#ff0000"
    popup.controls["dots"].setChecked(True)
    assert window.plot_styles["c2"] == {"linewidth": 3.0, "color": "#ff0000", "dots": True}
    assert view.ax.lines[0].get_marker() == "o"
    shot(view, "styled")
    assert window.view_state()["styles"] == {"c2": window.plot_styles["c2"]}
    # the export draws with the style
    drawn = {}
    original = plots.draw

    def spy(figure, result, *args, **kwargs):
        drawn["style"] = kwargs.get("style")
        return original(figure, result, *args, **kwargs)
    import sys
    plots_module = sys.modules["guiqula.ui.plots"]
    plots_module.draw = spy
    try:
        session.act("export_bundle", calculation="c2", path="out/c2")
    finally:
        plots_module.draw = original
    assert drawn["style"] == window.plot_styles["c2"]
    popup.reset.click()
    assert "c2" not in window.plot_styles and view.ax.lines[0].get_linewidth() == 1.2
    popup.hide()
    # restored from the ui block, applied when the result is drawn, dropped when stale
    session.act("plot_style", calculation="c2", fill=True)
    state = window.view_state()
    window.apply_view_state({})
    assert window.plot_styles == {}
    window.apply_view_state(state)
    assert window.plot_styles == {"c2": {"fill": True}}
    qtbot.waitUntil(lambda: window.plots["c2"].result is not None, timeout=10_000)
    assert len(window.plots["c2"].ax.collections) == 1       # the fill
    window.apply_view_state(dict(state, styles={"c2": {"size": 3}, "nope": {"fill": True}}))
    assert window.plot_styles == {"c2": {"size": 3}}         # checked at drawing time
    qtbot.waitUntil(lambda: window.plots["c2"].result is not None, timeout=10_000)
    assert window.plots["c2"].style == {}                    # not a lines option: ignored
    session.act("plot_style", calculation="c2", reset=True)
    assert window.plot_styles == {}


def test_a_scalar_result_has_no_style(window, qtbot):
    session = window.session
    _settle(qtbot, window)
    calc = session.do("add_calculation", system="s1", kind="chern", params={"nk": 8})
    view = _run(window, qtbot, calc)
    assert view.result.plot["kind"] == "scalar"
    assert not view.style_button.isEnabled()
    with pytest.raises(Exception, match="no style to change"):
        session.act("plot_style", calculation=calc, linewidth=3)
    session.do("remove", entry=calc)
