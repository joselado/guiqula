"""Sweeps (decision 13.10): the Haldane phase diagram, point by point equal
to direct pyqula calls; the exported script loops over the same values;
targets that cannot be swept are refused; the key follows the system."""
import numpy as np
import pytest

from guiqula.commands import Dispatcher
from guiqula.engine.build import BuildCache
from guiqula.engine.calculations import CalculationError, run_calculation
from guiqula.io.script import export_script
from guiqula.registry import cost, pipeline

from .test_script_export import run_scripts


def haldane():
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_construction", system=s, has_spin=False)
    t1 = d.do("add_term", system=s, kind="haldane", params={"t": 0.1})
    t2 = d.do("add_term", system=s, kind="sublattice_imbalance", params={"mass": 0.1})
    c = d.do("add_calculation", system=s, kind="chern", params={"nk": 10})
    return d, s, t1, t2, c


def test_a_curve_equals_direct_calls(pyqula, repo, tmp_path):
    from pyqula import geometry
    d, s, t1, t2, c = haldane()
    sweep = d.do("add_calculation", system=s, kind="sweep", params={
        "calculation": c, "entry": t2, "param": "mass", "start": 0.0, "stop": 0.8, "steps": 5})
    progress = []
    result = run_calculation(d.document, sweep, cache=BuildCache(),
                             progress=lambda f, text: progress.append(f))
    expected = []
    for mass in np.linspace(0.0, 0.8, 5):
        h = geometry.honeycomb_lattice().get_hamiltonian(has_spin=False)
        h.add_haldane(0.1)
        h.add_sublattice_imbalance(mass)
        expected.append(h.get_chern(nk=10))
    assert np.allclose(result.arrays["value"], np.linspace(0.0, 0.8, 5))
    assert np.allclose(result.arrays["chern"], expected, atol=1e-10)
    assert result.plot == {"kind": "lines", "x": "value", "y": "chern", "xlabel": "t2 mass",
                           "ylabel": "chern"}
    assert progress[-1] == pytest.approx(1.0)
    got = run_scripts([export_script(d.document, sweep)], repo, tmp_path)[0]
    assert set(got) == set(result.arrays)
    assert np.allclose(got["chern"], result.arrays["chern"], atol=1e-10)


def test_a_map_of_two_parameters(pyqula, repo, tmp_path):
    d, s, t1, t2, c = haldane()
    sweep = d.do("add_calculation", system=s, kind="sweep", params={
        "calculation": c, "entry": t2, "param": "mass", "start": 0.0, "stop": 0.8, "steps": 3,
        "entry2": t1, "param2": "t", "start2": -0.1, "stop2": 0.1, "steps2": 3})
    result = run_calculation(d.document, sweep, cache=BuildCache())
    chern = np.round(result.arrays["chern"]).astype(int)
    assert chern.shape == (3, 3) and chern[0, 0] == -chern[0, 2] != 0 and chern[2, 2] == 0
    assert result.plot["kind"] == "heatmap"
    got = run_scripts([export_script(d.document, sweep)], repo, tmp_path)[0]
    assert np.allclose(got["chern"], result.arrays["chern"], atol=1e-10)


def test_a_vector_component_and_what_is_refused(pyqula):
    d, s, t1, t2, c = haldane()
    z = d.do("add_term", system=s, kind="zeeman", params={"m": [0, 0, 0.1]})
    gap = d.do("add_calculation", system=s, kind="gap")
    sweep = d.do("add_calculation", system=s, kind="sweep", params={
        "calculation": gap, "entry": z, "param": "m", "component": 2, "start": 0.0,
        "stop": 0.4, "steps": 3})
    assert pipeline.plan_calculation(d.document, sweep).problem is None
    result = run_calculation(d.document, sweep, cache=BuildCache())
    assert result.arrays["gap"].shape == (3,)

    def problem(**params):
        d.do("set_params", entry=sweep, params=params)
        return pipeline.plan_calculation(d.document, sweep).problem
    assert "give the component" in problem(component=None)
    assert "no parameter 'nope'" in problem(component=2, param="nope")
    assert "not a calculation" in problem(param="m", calculation="c99")
    assert "not a sweep" in problem(calculation=sweep)
    other = d.do("add_system")
    band = d.do("add_calculation", system=other, kind="bands")
    assert "runs on" in problem(calculation=band)
    d.do("set_params", entry=sweep, params={"calculation": gap})
    assert pipeline.plan_calculation(d.document, sweep).problem is None
    dos = d.do("add_calculation", system=s, kind="dos", params={"nk": 2, "ne": 10})
    d.do("set_params", entry=sweep, params={"calculation": dos})
    with pytest.raises(CalculationError, match="no number to collect"):
        run_calculation(d.document, sweep, cache=BuildCache())


def test_key_and_cost(pyqula):
    d, s, t1, t2, c = haldane()
    sweep = d.do("add_calculation", system=s, kind="sweep", params={
        "calculation": c, "entry": t2, "param": "mass", "steps": 7})
    key = pipeline.calculation_key(d.document, sweep)
    d.do("set_param", entry=t1, name="t", value=0.2)         # the system changed: stale
    assert pipeline.calculation_key(d.document, sweep) != key
    builds = {s: {"dimension": 2, "dimensionality": 2, "sites": 2}}
    inner = cost.estimate(d.document, c, builds)["seconds"]
    assert cost.estimate(d.document, sweep, builds)["seconds"] == pytest.approx(7 * inner)


def test_values_the_entry_cannot_take_are_refused():
    """A value out of the parameter's bounds would make the entry invalid at
    that point, which would then be computed without it (a mean field with
    a filling above 1 as the non-interacting system): the sweep is refused
    when planned, and its script is not exported."""
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_meanfield", system=s, enabled=True, params={"U": 3.0, "nk": 4})
    op = d.do("add_geometry_op", system=s, kind="uniaxial_strain", params={"s": 0.0})
    c = d.do("add_calculation", system=s, kind="total_energy", params={"nk": 4})
    sweep = d.do("add_calculation", system=s, kind="sweep", params={
        "calculation": c, "entry": f"{s}/meanfield", "param": "filling", "start": 0.5,
        "stop": 1.25, "steps": 4})
    problem = pipeline.plan_calculation(d.document, sweep).problem
    assert "filling: must be at most 1.0, got 1.25" in problem
    with pytest.raises(ValueError, match="must be at most 1.0"):
        export_script(d.document, sweep)
    d.do("set_params", entry=sweep, params={"stop": 1.0})
    assert pipeline.plan_calculation(d.document, sweep).problem is None
    d.do("set_params", entry=sweep, params={"entry2": op, "param2": "s", "start2": 0.0,
                                            "stop2": 1.2, "steps2": 3})
    assert "s: must be at most 0.9, got 1.2" in pipeline.plan_calculation(d.document,
                                                                         sweep).problem


def test_a_point_without_the_swept_entry_fails():
    """pyqula may still reject a value inside the bounds: that point fails
    the sweep instead of being computed without the entry; the other
    entries skipped on the way are the sweep's reports."""
    from guiqula.core.results import Result
    from guiqula.engine.context import ApplyContext
    from guiqula.registry import base as registry
    from guiqula.registry.sweeps import SweepError
    d, s, t1, t2, c = haldane()
    spec = registry.get("calculation", "sweep")
    params = spec.normalize_params({"calculation": c, "entry": t2, "param": "mass",
                                    "start": 0.0, "stop": 1.0, "steps": 3})

    def run(rejected):
        """The inner calculation: t9 always skipped, t2 at the rejected masses."""
        def inner(document):
            mass = document.find(t2)[4].params["mass"]
            reports = [{"id": "t9", "stage": "term", "kind": "kekule", "status": "invalid",
                        "message": "TypeError: no"}]
            if mass in rejected:
                reports.append({"id": t2, "stage": "term", "kind": "sublattice_imbalance",
                                "status": "invalid", "message": "ValueError: too large"})
            return Result(calculation=c, kind="chern", key="", params={},
                          arrays={"chern": np.float64(mass)}, plot={}, reports=reports)
        return inner
    ctx = ApplyContext(spec, params)
    arrays = spec.apply(d.document, ctx, run(()))
    assert np.allclose(arrays["chern"], [0.0, 0.5, 1.0])
    assert [(r["id"], r["message"]) for r in ctx.notes["reports"]] == [
        ("t9", "at t2 mass = 0: TypeError: no")]
    with pytest.raises(SweepError, match=r"t2 is skipped at t2 mass = 1 \(ValueError: too "
                                         r"large\), so that point would be computed without it"):
        spec.apply(d.document, ApplyContext(spec, params), run((1.0,)))


def test_a_sweep_of_the_island_size_exports_the_island(pyqula, repo, tmp_path):
    """The script is generated with the swept value set between the first
    and the last value (one the entry takes: the island's size has a
    minimum), so it builds the island at every value, as the engine does."""
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_construction", system=s, has_spin=False)
    island = d.do("add_geometry_op", system=s, kind="island", params={"n": 1.0})
    d.do("add_term", system=s, kind="sublattice_imbalance", params={"mass": 0.1})
    c = d.do("add_calculation", system=s, kind="total_energy", params={"nk": 1})
    sweep = d.do("add_calculation", system=s, kind="sweep", params={
        "calculation": c, "entry": island, "param": "n", "start": 1.5, "stop": 2.5, "steps": 3})
    result = run_calculation(d.document, sweep, cache=BuildCache())
    assert len(set(np.round(result.arrays["energy"], 6))) == 3
    source = export_script(d.document, sweep)
    assert "islands.get_geometry(geo=g, n=value," in source and "skipped" not in source
    got = run_scripts([source], repo, tmp_path)[0]
    assert np.allclose(got["energy"], result.arrays["energy"], atol=1e-10)
