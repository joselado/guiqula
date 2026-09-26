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
