"""A calculation that names a second system (SystemParam): the local probe,
whose tip is a system of its own. The tip is planned with the calculation
and keys it, is built through the same cache, is written first in the
exported script, cannot be removed while named, and is refused when it
cannot be a tip. Its arrays against direct pyqula calls are in
test_entries.py (CALC_CASES "local_probe")."""
import numpy as np
import pytest

from guiqula.commands import CommandError, Dispatcher
from guiqula.engine.calculations import CalculationError, run_calculation
from guiqula.io.script import export_script
from guiqula.registry import cost, pipeline


def sample_and_tip(tip_terms=()):
    """An s-wave chain (s1) and a spinless chain (s2) as its tip."""
    d = Dispatcher()
    s = d.do("add_system", lattice="chain")
    d.do("add_term", system=s, kind="swave", params={"delta": 0.1})
    tip = d.do("add_system", lattice="chain")
    d.do("set_construction", system=tip, has_spin=False)
    for kind, params in tip_terms:
        d.do("add_term", system=tip, kind=kind, params=params)
    c = d.do("add_calculation", system=s, kind="local_probe",
             params={"probe": tip, "ne": 5, "emin": -0.3, "emax": 0.3, "delta": 1e-3})
    return d, s, tip, c


def test_the_tip_keys_the_result():
    """Editing the tip makes the curve stale; editing a third system does not."""
    d, s, tip, c = sample_and_tip()
    other = d.do("add_system", lattice="square_lattice")
    key = pipeline.calculation_key(d.document, c)
    d.do("add_term", system=other, kind="onsite", params={"mu": 0.3})
    assert pipeline.calculation_key(d.document, c) == key
    d.do("add_term", system=tip, kind="swave", params={"delta": 0.1})
    assert pipeline.calculation_key(d.document, c) != key
    d.do("set_param", entry=c, name="probe", value=None)        # pyqula's own tip
    assert pipeline.plan_calculation(d.document, c).others == {}


def test_what_cannot_be_a_tip_is_refused():
    d, s, tip, c = sample_and_tip()
    d.do("set_param", entry=c, name="probe", value=s)
    assert "the system it runs on" in pipeline.plan_calculation(d.document, c).problem
    d.do("set_param", entry=c, name="probe", value="s9")
    assert "there is no system 's9'" in pipeline.plan_calculation(d.document, c).problem
    spins = d.do("add_system", kind="classical_spin", lattice="chain")
    d.do("set_param", entry=c, name="probe", value=spins)
    assert "classical spins" in pipeline.plan_calculation(d.document, c).problem


def test_a_tip_in_use_cannot_be_removed():
    d, s, tip, c = sample_and_tip()
    with pytest.raises(CommandError, match="used by calculations"):
        d.do("remove", entry=tip)
    d.do("set_param", entry=c, name="probe", value=None)
    d.do("remove", entry=tip)


def test_a_tip_and_sites_that_are_refused(pyqula):
    d, s, tip, c = sample_and_tip()
    square = d.do("add_system", lattice="square_lattice")
    d.do("set_param", entry=c, name="probe", value=square)
    with pytest.raises(CalculationError, match="one-dimensional"):
        run_calculation(d.document, c)
    d.do("set_param", entry=c, name="probe", value=tip)
    with pytest.raises(CommandError, match="one position"):          # it touches one site
        d.do("set_param", entry=c, name="positions", value=[[0, 0, 0], [1, 0, 0]])
    d.do("set_param", entry=c, name="positions", value=[[0.4, 0, 0]])
    with pytest.raises(CalculationError, match="no site is within"):
        run_calculation(d.document, c)


def test_the_script_builds_the_tip_first(pyqula):
    d, s, tip, c = sample_and_tip([("swave", {"delta": 0.1})])
    script = export_script(d.document, c)
    assert script.index(f"# probe: system {tip}") < script.index("probe = h") \
        < script.index(f"# system {s}") < script.index("lead=probe")


def test_the_cost_knows_a_superconducting_tip():
    """Floquet-Keldysh, when tip and sample are both Nambu, costs seconds an
    energy where the scattering matrix costs milliseconds; a temperature
    multiplies either."""
    d, s, tip, c = sample_and_tip()
    builds = {s: {"dimension": 4, "dimensionality": 1, "sites": 1}}
    normal = cost.estimate(d.document, c, builds)["seconds"]
    d.do("set_param", entry=c, name="temp", value=0.01)
    warm = cost.estimate(d.document, c, builds)["seconds"]
    d.do("set_param", entry=c, name="temp", value=0.0)
    d.do("add_term", system=tip, kind="swave", params={"delta": 0.1})
    keldysh = cost.estimate(d.document, c, builds)["seconds"]
    assert normal < 1.0 < warm and keldysh > 60 * normal


def test_a_superconducting_tip_reveals_both_gaps(pyqula):
    """The physics the tip system buys: a normal tip on an s-wave chain
    sees the gap Delta, a superconducting one the sum of the two gaps, so
    at a bias between Delta and 2 Delta the first conducts and the second
    does not (below its threshold only multiple Andreev reflections carry
    current, weakly at a low transparency)."""
    d, s, tip, c = sample_and_tip([("onsite", {"mu": 0.5})])
    d.do("set_params", entry=c, params={"emin": 0.15, "emax": 0.15, "ne": 2, "T": 0.1})
    normal = run_calculation(d.document, c).arrays["didv"][0]
    d.do("add_term", system=tip, kind="swave", params={"delta": 0.1})
    superconducting = run_calculation(d.document, c).arrays["didv"][0]
    assert superconducting < 0.2 * normal, (normal, superconducting)
