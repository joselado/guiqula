"""Calculations from picks (PLAN.md phase 7), driven offscreen: a point of
the bands picked through the window's pick and pick_to actions, the menu
of a right click on a result view, a locked calculation refusing, a box on
an LDOS map picking the atoms inside it, the Fermi-level target, a sweep
picked at a point of its curve, and the Run at once switch."""
import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent

from guiqula.commands import CommandError
from guiqula.registry import picks as pick_targets
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.resize(1400, 900)
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)


def shown(window, qtbot, calc, timeout=300_000):
    """Wait until a calculation has a current result drawn in its view."""
    window.show_result(calc)
    qtbot.waitUntil(lambda: window.session.result(calc) is not None
                    and not window.session.is_stale(calc)
                    and window.plots[calc].result is window.session.result(calc),
                    timeout=timeout)
    return window.plots[calc]


def run(window, qtbot, calc):
    window.session.run_calculation(calc, wait=True, timeout=600)
    assert window.session.calc_jobs[calc].status == "done", window.session.calc_jobs[calc].error
    return shown(window, qtbot, calc)


def ready(window, qtbot, calc):
    """A calculation's current result drawn, run first if it has none (a
    test run alone)."""
    session = window.session
    if session.result(calc) is None or session.is_stale(calc):
        return run(window, qtbot, calc)
    return shown(window, qtbot, calc)


def band_point(result, ik=10, band=7):
    energies = np.asarray(result.arrays["energies"])
    return float(result.arrays["k"][ik]), float(energies[ik, band])


def of(targets, what, **match):
    return next(i for i, t in enumerate(targets) if t["target"] == what
                and all(t.get(k) == v for k, v in match.items()))


def test_a_pick_on_the_bands_adds_an_ldos_at_that_energy(window, qtbot, shot):
    settle(qtbot, window)
    session = window.session
    view = run(window, qtbot, "c1")
    x, y = band_point(view.result)
    picked = session.act("pick", calculation="c1", x=x + 0.2, y=y + 0.001)    # snapped
    assert picked["values"]["energy"] == pytest.approx(y)
    assert picked["values"]["kpoint"] == pytest.approx(list(view.result.arrays["kpoints"][10]))
    assert picked["label"].startswith("E = ")
    kinds = {t["kind"] for t in picked["targets"] if t["target"] == "add"}
    assert {"ldos", "fermi_surface"} <= kinds
    assert any(t["target"] == "kpath" and t["calculation"] == "c1" for t in picked["targets"])
    assert any(t["target"] == "fermi_level" for t in picked["targets"])
    steps = len(session.dispatcher.history()["undo"])
    session.act("run_at_once", enabled=True)
    try:
        done = session.act("pick_to", calculation="c1", x=x, y=y,
                           target=of(picked["targets"], "add", kind="ldos"))
        calc = done["calculation"]
        ldos = session.document.calculation(calc)
        assert ldos.kind == "ldos" and ldos.params["energy"] == pytest.approx(y)
        assert ldos.name.startswith("at E = ") and ldos.name.endswith("from c1")
        assert window.current_tab() == calc              # shown, and run at once
        view = shown(window, qtbot, calc)
        assert view.result.params["energy"] == pytest.approx(y)
        assert "from c1" in window.outliner.item(calc).text(0)
        shot(window, "ldos_from_a_band_point")
        assert len(session.dispatcher.history()["undo"]) == steps + 1     # one step
        session.undo()
        assert calc not in {c.id for c in session.document.calculations}
    finally:
        session.act("run_at_once", enabled=False)


def test_the_menu_of_a_right_click(window, qtbot, shot):
    settle(qtbot, window)
    session = window.session
    view = ready(window, qtbot, "c1")
    x, y = band_point(view.result, ik=30, band=8)
    px, py = view.ax.transData.transform((x, y))
    for name in ("button_press_event", "button_release_event"):       # a right click
        MouseEvent(name, view.canvas, px, py, button=3)._process()
    menu = window._pick_menu
    qtbot.waitUntil(lambda: menu.isVisible(), timeout=5000)
    title = menu.findChild(type(menu.actions()[0]), "pickTitle")
    assert title is not None and title.text().startswith(f"E = ")
    shot(menu, "menu")
    labels = [a.text() for a in menu.actions() if a.objectName().startswith("pickTarget_")]
    fermi = next(i for i, text in enumerate(labels) if text.startswith("new Fermi surface"))
    menu.findChild(type(title), f"pickTarget_{fermi}").trigger()
    menu.close()
    calc = session.document.calculations[-1]
    assert calc.kind == "fermi_surface" and calc.params["energy"] == pytest.approx(y)
    assert "readout" and view.readout is not None
    session.undo()


def test_the_readout_says_what_a_pick_takes(window, qtbot):
    settle(qtbot, window)
    view = ready(window, qtbot, "c1")
    x, y = band_point(view.result)
    px, py = view.ax.transData.transform((x, y))
    MouseEvent("motion_notify_event", view.canvas, px, py)._process()
    assert "a pick takes E = " in view.readout.text() and "k = (" in view.readout.text()


def test_a_locked_calculation_refuses_the_pick(window, qtbot):
    settle(qtbot, window)
    session = window.session
    calc = session.do("add_calculation", system="s1", kind="ldos", params={"nk": 2})
    session.do("lock", target=f"{calc}.energy")
    try:
        view = ready(window, qtbot, "c1")
        x, y = band_point(view.result)
        picked = session.act("pick", calculation="c1", x=x, y=y)
        index = of(picked["targets"], "set", calculation=calc)
        with pytest.raises(CommandError, match="locked"):
            session.act("pick_to", calculation="c1", x=x, y=y, target=index)
        menu = window.pick_menu("c1", x, y)                   # from the menu: shown, not raised
        menu.findChild(type(menu.actions()[0]), f"pickTarget_{index}").trigger()
        assert "locked" in window.log.toPlainText().splitlines()[-1]
        assert session.document.calculation(calc).params["energy"] == 0.0
    finally:
        session.do("unlock")
        session.do("remove", entry=calc)


def test_a_box_on_an_ldos_map_picks_the_atoms_inside_it(window, qtbot, shot):
    settle(qtbot, window)
    session = window.session
    calc = session.do("add_calculation", system="s1", kind="ldos", params={"nk": 2,
                                                                        "delta": 0.2})
    try:
        view = run(window, qtbot, calc)
        positions = np.asarray(view.result.structure["positions"])
        box = [-0.1, -2.0, 1.6, 2.0]
        inside = [i for i, (px, py, _) in enumerate(positions)
                  if -0.1 <= px <= 1.6 and -2 <= py <= 2]
        assert 0 < len(inside) < len(positions)
        picked = session.act("pick", calculation=calc, box=box)
        assert picked["sites"] == inside and picked["label"] == f"{len(inside)} sites"
        assert [t["target"] for t in picked["targets"]] == ["add", "select_sites", "region"]
        assert picked["targets"][0]["kind"] == "site_dos"          # the DOS on them
        view.pick_tools["box"].setChecked(True)             # the tool is on the view
        assert view._selector is not None
        shot(view, "box_tool")
        view.pick_tools["box"].setChecked(False)
        done = session.act("pick_to", calculation=calc, box=box,
                           target=of(picked["targets"], "region"))
        region = session.document.system("s1").regions[-1]
        assert done["region"] == region.id and len(region.select["positions"]) == len(inside)
        session.undo()
        done = session.act("pick_to", calculation=calc, box=box,
                           target=of(picked["targets"], "select_sites"))
        assert done["sites"] == len(inside) and window.current_tab() == "structure"
        one = session.act("pick", calculation=calc, x=float(positions[0, 0]),
                          y=float(positions[0, 1]))
        assert one["values"]["sites"] == [pytest.approx(list(positions[0]))]
    finally:
        session.do("remove", entry=calc)


def test_the_fermi_level_target(window, qtbot):
    settle(qtbot, window)
    session = window.session
    view = ready(window, qtbot, "c1")
    x, y = band_point(view.result)
    picked = session.act("pick", calculation="c1", x=x, y=y)
    done = session.act("pick_to", calculation="c1", x=x, y=y,
                       target=of(picked["targets"], "fermi_level"))
    term = session.document.find(done["term"])[4]
    assert term.kind == "onsite" and term.name == pick_targets.FERMI_LEVEL
    assert term.params["mu"] == pytest.approx(-y)
    again = session.act("pick", calculation="c1", x=x, y=y)     # updates the same term
    target = again["targets"][of(again["targets"], "fermi_level")]
    assert target["term"] == term.id
    session.do("set_enabled", entry=term.id, enabled=False)      # off: the next pick turns
    steps = len(session.dispatcher.history()["undo"])            # it on, in one step
    target = session.act("pick", calculation="c1", x=x, y=y)["targets"]
    target = target[of(target, "fermi_level")]
    assert "update and enable" in target["label"]
    session.act("pick_to", calculation="c1", target=target)
    assert session.document.find(term.id)[4].enabled
    assert len(session.dispatcher.history()["undo"]) == steps + 1
    session.undo(3)
    assert not any(t.name == pick_targets.FERMI_LEVEL
                   for t in session.document.system("s1").hamiltonian.terms)


def test_a_point_of_a_sweep_sets_its_parameter(window, qtbot):
    settle(qtbot, window)
    session = window.session
    gap = session.do("add_calculation", system="s1", kind="total_energy", params={"nk": 2})
    sweep = session.do("add_calculation", system="s1", kind="sweep", params={
        "calculation": gap, "entry": "t2", "param": "c", "start": 0.0, "stop": 0.2, "steps": 3})
    try:
        view = run(window, qtbot, sweep)
        x = float(view.result.arrays["value"][1])
        y = float(view.result.arrays["energy"][1])
        picked = session.act("pick", calculation=sweep, x=x, y=y)
        assert picked["values"]["parameter"] == [
            {"entry": "t2", "param": "c", "component": None, "value": pytest.approx(0.1)}]
        target = of(picked["targets"], "parameter")
        assert picked["targets"][target]["run"] == gap
        done = session.act("pick_to", calculation=sweep, x=x, y=y, target=target)
        assert done["calculation"] == gap
        assert session.document.find("t2")[4].params["c"] == pytest.approx(0.1)
        session.undo()
        assert session.document.find("t2")[4].params["c"] == 0.1        # the preset's
    finally:
        session.do("remove", entry=sweep)
        session.do("remove", entry=gap)


def test_run_at_once(window, qtbot):
    """Off, adding or setting a calculation runs nothing; on, it runs."""
    settle(qtbot, window)
    session = window.session
    assert window.run_at_once is False           # tests and drivers: off unless asked
    calc = session.do("add_calculation", system="s1", kind="dos", params={"ne": 20, "nk": 2})
    try:
        assert calc not in session.calc_jobs
        session.act("run_at_once", enabled=True)
        assert window.run_at_once_action.isChecked()
        session.do("set_param", entry=calc, name="ne", value=30)
        assert calc in session.calc_jobs
        shown(window, qtbot, calc)
        session.do("set_param", entry="t2", name="c", value=0.12)     # not the calculation's
        assert session.status(calc) == "stale" and session.calc_jobs[calc].done
        session.undo()
        assert session.status(calc) == "done"
        sweep = session.do("add_calculation", system="s1", kind="sweep")   # not set up yet
        assert sweep not in session.calc_jobs
        session.do("remove", entry=sweep)
    finally:
        session.act("run_at_once", enabled=False)
        session.do("remove", entry=calc)


def test_a_click_in_the_kspace_tab_picks_a_kpoint(window, qtbot, shot):
    """With Add points off, a click in the zone is a k-point (snapped onto
    K here), and the eigenstate there is computed."""
    settle(qtbot, window)
    session = window.session
    window.select("s1")
    window.viewport.setCurrentIndex(1)                       # the k-space tab
    view = window.kspace_view
    qtbot.waitUntil(lambda: view.ax is not None, timeout=10_000)
    from guiqula.ui import kspace as tools
    k_point = tools.special_images(view.kspace)["K"]
    px, py = view.ax.transData.transform(k_point)
    for name in ("button_press_event", "button_release_event"):
        MouseEvent(name, view.canvas, px, py, button=1)._process()
    menu = window._pick_menu
    qtbot.waitUntil(lambda: menu.isVisible(), timeout=5000)
    labels = [a.text() for a in menu.actions() if a.objectName().startswith("pickTarget_")]
    assert any(text.startswith("new Eigenstate at k = (") for text in labels), labels
    assert any(text.startswith("new Local density of states at k = (") for text in labels)
    shot(menu, "kspace_menu")
    menu.close()
    k = tools.snap(k_point, view.kspace)
    picked = session.act("pick", system="s1", values={"kpoint": k})
    session.act("run_at_once", enabled=True)
    try:
        done = session.act("pick_to", system="s1", values={"kpoint": k},
                           target=of(picked["targets"], "add", kind="eigenstate"))
        view = shown(window, qtbot, done["calculation"])
        assert view.result.params["k"] == pytest.approx(k)
        assert abs(view.result.arrays["weight"].sum() - 1) < 1e-8
        assert "|ψ|² of the state at E = " in view.result.plot["clabel"]
        shot(view, "eigenstate")
    finally:
        session.act("run_at_once", enabled=False)
        session.undo()


def test_the_dos_on_the_selected_sites(window, qtbot, shot):
    settle(qtbot, window)
    session = window.session
    window.select("s1")
    window.viewport.setCurrentIndex(0)
    assert session.act("select_sites", indices=[0, 3]) == 2
    menu = window._selection_menu()
    labels = {a.text(): a for a in menu.actions() if a.objectName().startswith("pickTarget_")}
    assert "new DOS on sites on 2 sites" in labels, list(labels)
    assert not any("region" in text or "select" in text for text in labels)   # buttons of their own
    menu.close()
    labels["new DOS on sites on 2 sites"].trigger()
    calc = session.document.calculations[-1]
    try:
        assert calc.kind == "site_dos" and len(calc.params["positions"]) == 2
        session.do("set_params", entry=calc.id, params={"ne": 60, "nk": 4})
        view = run(window, qtbot, calc.id)
        assert view.result.plot["kind"] == "lines" and view.result.arrays["dos"].max() > 0
        shot(view, "site_dos")
    finally:
        session.do("remove", entry=calc.id)


def drag(view, start, end, qtbot=None):
    """A left-button drag on a result view, from and to data coordinates."""
    (x0, y0), (x1, y1) = (view.ax.transData.transform(p) for p in (start, end))
    MouseEvent("button_press_event", view.canvas, x0, y0, button=1)._process()
    for t in np.linspace(0.25, 1.0, 4):
        MouseEvent("motion_notify_event", view.canvas, x0 + t * (x1 - x0),
                   y0 + t * (y1 - y0), button=1)._process()
    MouseEvent("button_release_event", view.canvas, x1, y1, button=1)._process()


def test_a_marker_stays_on_the_plot_and_drives_its_parameter(window, qtbot, shot):
    """Part 3: the energy a pick set is a line on the bands, bound to the
    LDOS's energy as a slider is; a drag moves it (one undo step), and a
    command or an undo moves the line."""
    settle(qtbot, window)
    session = window.session
    view = ready(window, qtbot, "c1")
    x, y = band_point(view.result)
    picked = session.act("pick", calculation="c1", x=x, y=y)
    done = session.act("pick_to", calculation="c1", x=x, y=y,
                       target=of(picked["targets"], "add", kind="ldos"))
    calc = done["calculation"]
    try:
        marker = window.sliders[-1]
        assert (marker["entry"], marker["param"], marker["on"], marker["axis"]) == \
            (calc, "energy", "c1", "y")
        view = window.plots["c1"]
        assert [(m["kind"], m["value"]) for m in view.markers] == [("hline", pytest.approx(y))]
        row = window.sliders_panel.rows[-1]
        assert row.label.text() == f"{calc} energy on c1"
        window.show_result("c1")
        steps = len(session.dispatcher.history()["undo"])
        target = y + 0.4 * (marker["max"] - y)
        drag(view, (x, y), (x, target))
        energy = session.document.calculation(calc).params["energy"]
        assert energy == pytest.approx(target, abs=0.02 * (marker["max"] - marker["min"]))
        assert len(session.dispatcher.history()["undo"]) == steps + 1      # one drag, one step
        assert view.markers[0]["value"] == pytest.approx(energy)
        shot(view, "dragged")
        session.do("set_param", entry=calc, name="energy", value=0.1)      # a command moves it
        assert view.markers[0]["value"] == pytest.approx(0.1)
        session.undo()
        assert view.markers[0]["value"] == pytest.approx(energy)
        state = window.view_state()["sliders"]
        assert state[-1]["on"] == "c1" and state[-1]["axis"] == "y"
        run(window, qtbot, calc)                   # with the automatic re-run on, the LDOS
        session.act("auto_rerun", enabled=True)    # follows the line
        try:
            window.show_result("c1")
            drag(view, (x, energy), (x, y))
            qtbot.waitUntil(lambda: session.result(calc).params["energy"] == pytest.approx(
                session.document.calculation(calc).params["energy"]), timeout=120_000)
        finally:
            session.act("auto_rerun", enabled=False)
    finally:
        session.do("remove", entry=calc)
    assert all(s.get("on") != "c1" or s["entry"] != calc for s in window.sliders)
    assert view.markers == []                           # pruned with its calculation


def test_a_kpoint_marker_on_a_fermi_surface(window, qtbot):
    """A k-point picked on a map is a dot there; dragged, the k-point of
    the eigenstate follows the cell under it."""
    settle(qtbot, window)
    session = window.session
    surface = session.do("add_calculation", system="s1", kind="fermi_surface",
                         params={"energy": 0.5, "nk": 16, "delta": 0.1})
    try:
        view = run(window, qtbot, surface)
        kx, ky = view.result.arrays["kx"], view.result.arrays["ky"]
        x, y = float(kx[40]), float(ky[40])
        picked = session.act("pick", calculation=surface, x=x, y=y)
        done = session.act("pick_to", calculation=surface, x=x, y=y,
                           target=of(picked["targets"], "add", kind="eigenstate"))
        marker = window.sliders[-1]
        assert (marker["param"], marker["axis"], marker["quantity"]) == ("k", "xy", "kpoint")
        dots = [m for m in view.markers if m["kind"] == "dots"]
        assert dots and any(np.allclose(point, [x, y], atol=1e-9) for point in dots[0]["value"])
        assert len(dots[0]["value"]) > 1                    # its images in the extended zone
        x2, y2 = float(kx[100]), float(ky[100])
        drag(view, (x, y), (x2, y2))
        k = session.document.calculation(done["calculation"]).params["k"]
        assert k == pytest.approx(session.act("pick", calculation=surface, x=x2, y=y2)[
            "values"]["kpoint"])
        assert window.sliders_panel.rows[-1].slider is None       # a k-point: no range
        session.do("remove", entry=done["calculation"])
    finally:
        session.do("remove", entry=surface)
