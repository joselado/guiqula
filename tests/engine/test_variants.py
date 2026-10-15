"""Variants computed: a calculation's variant gives what the same
calculation made by hand on its input gives, and a system's variant is its
original's Hamiltonian built on the variant's geometry."""
import numpy as np

from guiqula.commands import Dispatcher
from guiqula.engine.build import build_system
from guiqula.engine.calculations import run_calculation


def test_a_variant_is_the_same_calculation_on_its_input(pyqula):
    d = Dispatcher()
    s1 = d.do("add_system", lattice="honeycomb_lattice")
    s2 = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_term", system=s2, kind="sublattice_imbalance", params={"mass": 0.3})
    c = d.do("add_calculation", system=s1, kind="dos", params={"ne": 11, "nk": 6})
    v = d.do("add_variant", entry=c, target=s2)
    by_hand = d.do("add_calculation", system=s2, kind="dos", params={"ne": 11, "nk": 6})
    variant, direct = run_calculation(d.document, v), run_calculation(d.document, by_hand)
    assert np.allclose(variant.arrays["dos"], direct.arrays["dos"])
    assert not np.allclose(variant.arrays["dos"], run_calculation(d.document, c).arrays["dos"])


def test_a_system_variant_builds_the_original_on_its_geometry(pyqula):
    d = Dispatcher()
    s1 = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_term", system=s1, kind="zeeman", params={"m": [0.0, 0.0, 0.2]})
    geometry = d.do("add_geometry", lattice="honeycomb_lattice")
    d.do("add_geometry_op", system=geometry, kind="supercell", params={"n": [2, 1, 1]})
    v = d.do("add_variant", entry=s1, target=geometry)
    original, variant = build_system(d.document, s1), build_system(d.document, v)
    assert variant.h.intra.shape[0] == 2 * original.h.intra.shape[0]   # twice the cell
    assert variant.h.has_spin                                          # the Zeeman term
