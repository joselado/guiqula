"""Every registry entry against a direct pyqula call (CLAUDE.md hard rule).

Each case builds a small document through the command API, runs it through
the engine in this process, and compares with the same pyqula calls written
by hand. test_every_entry_has_a_case keeps the list complete."""
import random

import numpy as np
import pytest

from guiqula import registry
from guiqula.commands import Dispatcher
from guiqula.engine.build import build_system
from guiqula.engine.calculations import run_calculation

from .conftest import assert_same_hamiltonian

LATTICES = registry.kinds("lattice")


def system(lattice="honeycomb_lattice", ops=(), terms=(), has_spin=True):
    d = Dispatcher()
    s = d.do("add_system", lattice=lattice)
    d.do("set_construction", system=s, has_spin=has_spin)
    for kind, params in ops:
        d.do("add_geometry_op", system=s, kind=kind, params=params)
    ids = [d.do("add_term", system=s, kind=kind, params=params) for kind, params in terms]
    return d, s, ids


@pytest.mark.parametrize("lattice", LATTICES)
def test_lattice(pyqula, lattice):
    from pyqula import geometry
    d, s, _ = system(lattice)
    g = build_system(d.document, s).g
    direct = getattr(geometry, lattice)()
    assert np.allclose(g.r, direct.r) and g.dimensionality == direct.dimensionality


def positions_equal(g1, g2):
    a = np.array(sorted(map(tuple, np.round(g1.r, 8))))
    b = np.array(sorted(map(tuple, np.round(g2.r, 8))))
    return a.shape == b.shape and np.allclose(a, b)


OP_CASES = {
    "supercell": ({"n": [2, 3, 1]}, lambda g: g.get_supercell([2, 3, 1])),
    "ribbon": ({"n": 3}, lambda g: __import__("pyqula.ribbon").ribbon.bulk2ribbon(g, n=3, boundary=[1, 0])),
    "island": ({"n": 2.5, "nedges": 3, "rot": 0.3},
               lambda g: __import__("pyqula.islands").islands.get_geometry(
                   geo=g, n=2.5, nedges=3, rot=0.3, clean=True)),
    "remove_atoms": (None, None),        # built on a supercell, below
}


@pytest.mark.parametrize("kind", sorted(OP_CASES))
def test_geometry_op(pyqula, kind):
    from pyqula import geometry
    params, direct_op = OP_CASES[kind]
    if kind == "remove_atoms":
        d, s, _ = system(ops=[("supercell", {"n": [2, 2, 1]})])
        g_sc = geometry.honeycomb_lattice().get_supercell([2, 2, 1])
        params = {"positions": [list(map(float, g_sc.r[3]))], "tol": 0.1}
        d.do("add_geometry_op", system=s, kind="remove_atoms", params=params)
        direct = g_sc.remove([3])
    else:
        d, s, _ = system(ops=[(kind, params)])
        direct = direct_op(geometry.honeycomb_lattice())
    g = build_system(d.document, s).g
    assert positions_equal(g, direct) and g.dimensionality == direct.dimensionality


def tanh_profile(r):
    return 0.3 * np.tanh(r[0] / 4)


TERM_CASES = {
    "onsite": [({"mu": 0.3}, lambda h: h.add_onsite(0.3)),
               ({"mu": "0.2*x"}, lambda h: h.add_onsite(lambda r: 0.2 * r[0]))],
    "sublattice_imbalance": [({"mass": 0.2}, lambda h: h.add_sublattice_imbalance(0.2)),
                             ({"mass": "0.1*y"}, lambda h: h.add_sublattice_imbalance(lambda r: 0.1 * r[1]))],
    "zeeman": [({"m": [0.1, 0.0, 0.2]}, lambda h: h.add_zeeman([0.1, 0.0, 0.2])),
               ({"m": [0, 0, "0.3*tanh(x/4)"]}, lambda h: h.add_zeeman([0.0, 0.0, tanh_profile]))],
    "rashba": [({"c": 0.1}, lambda h: h.add_rashba(0.1)),
               ({"c": "0.1*cos(x)"}, lambda h: h.add_rashba(lambda r: 0.1 * np.cos(r[0])))],
    "haldane": [({"t": 0.05}, lambda h: h.add_haldane(0.05)),
                ({"t": "0.05*exp(-r)"}, lambda h: h.add_haldane(lambda r: 0.05 * np.exp(-np.linalg.norm(r))))],
    "anderson_disorder": [({"w": 0.5, "p": 1.0, "seed": 7}, None)],
    "kane_mele": [({"t": 0.05}, lambda h: h.add_kane_mele(0.05)),
                  ({"t": "0.05*cos(x)"}, lambda h: h.add_kane_mele(lambda r: 0.05 * np.cos(r[0])))],
    "antiferromagnetism": [({"m": [0, 0, 0.2]}, lambda h: h.add_antiferromagnetism(0.2)),
                           ({"m": [0.1, 0, "0.2*tanh(x)"]},
                            lambda h: h.add_antiferromagnetism(
                                lambda r: [0.1, 0.0, 0.2 * np.tanh(r[0])]))],
    "swave": [({"delta": 0.1}, lambda h: h.add_swave(0.1)),
              ({"delta": "0.1*exp(-r)"},
               lambda h: h.add_swave(lambda r: 0.1 * np.exp(-np.linalg.norm(r))))],
}


@pytest.mark.parametrize("kind, case", [(k, i) for k in sorted(TERM_CASES)
                                        for i in range(len(TERM_CASES[k]))])
def test_term(pyqula, kind, case):
    from pyqula import disorder, geometry
    params, direct_term = TERM_CASES[kind][case]
    d, s, _ = system(ops=[("supercell", {"n": [2, 2, 1]})], terms=[(kind, params)])
    built = build_system(d.document, s)
    assert [r["status"] for r in built.reports] == ["ok"] * (len(built.reports) - 1) + ["disabled"]
    h = geometry.honeycomb_lattice().get_supercell([2, 2, 1]).get_hamiltonian(has_spin=True)
    if kind == "anderson_disorder":
        np.random.seed(7)
        random.seed(7)
        disorder.anderson(h, w=0.5, p=1.0)
    else:
        direct_term(h)
    assert_same_hamiltonian(built.h, h)


def test_piecewise_field(pyqula):
    """One value per region plus a default; the later piece wins where
    regions overlap (PLAN.md 3.8)."""
    from pyqula import geometry
    d, s, (t,) = system(ops=[("supercell", {"n": [3, 3, 1]})], terms=[("onsite", {"mu": 0.0})])
    r1 = d.do("add_region", system=s, select={"kind": "expression", "expr": "x > 1"})
    r2 = d.do("add_region", system=s, select={"kind": "expression", "expr": "y > 0"})
    d.do("set_param", entry=t, name="mu", value={
        "kind": "piecewise", "default": 0.1,
        "pieces": [{"region": r1, "value": "0.5*y"}, {"region": r2, "value": -0.3}]})
    h = geometry.honeycomb_lattice().get_supercell([3, 3, 1]).get_hamiltonian(has_spin=True)
    h.add_onsite(lambda r: -0.3 if r[1] > 0 else (0.5 * r[1] if r[0] > 1 else 0.1))
    assert_same_hamiltonian(build_system(d.document, s).h, h)


def test_region_restricts_a_field(pyqula):
    from pyqula import geometry
    d, s, (t,) = system(ops=[("supercell", {"n": [3, 3, 1]})], terms=[("onsite", {"mu": 0.4})])
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x > 1"})
    d.do("set_region", entry=t, region=r)
    h = geometry.honeycomb_lattice().get_supercell([3, 3, 1]).get_hamiltonian(has_spin=True)
    h.add_onsite(lambda r: 0.4 * float(r[0] > 1))
    assert_same_hamiltonian(build_system(d.document, s).h, h)


MEANFIELD_CASES = {
    "interactions": [
        {"U": 3.0, "mf": "antiferro", "nk": 4, "mix": 0.5},
        {"U": "2.5 + 0.5*tanh(x)", "V1": 0.2, "mf": "random", "seed": 5, "nk": 4, "mix": 0.5},
        {"U": 2.0, "fix": "mu", "mu": 0.1, "mf": "ferro", "nk": 3, "mix": 0.5},
        {"U": 3.0, "filling": "0.5 + 0.05*tanh(x)", "mf": "antiferro", "nk": 4, "mix": 0.5},
        {"U": 3.0, "mf": "antiferro", "nk": 4, "engine": "jax", "solver": "newton"},
        {"U": 3.0, "mf": "antiferro", "nk": 4, "engine": "jax", "solver": "linear_mixing",
         "mix": 0.5, "maxite": 500, "T": 1e-3},
    ],
}


@pytest.mark.parametrize("kind, case", [(k, i) for k in sorted(MEANFIELD_CASES)
                                        for i in range(len(MEANFIELD_CASES[k]))])
def test_meanfield(pyqula, kind, case):
    from pyqula import geometry
    params = MEANFIELD_CASES[kind][case]
    d, s, _ = system(terms=[("rashba", {"c": 0.1})], has_spin=False)
    d.do("set_meanfield", system=s, enabled=True, kind=kind, params=params)
    built = build_system(d.document, s)
    report = built.reports[-1]
    assert report["id"] == f"{s}/meanfield" and report["status"] == "ok"
    p = registry.get("meanfield", kind).normalize_params(params)
    h = geometry.honeycomb_lattice().get_hamiltonian(has_spin=True)
    h.add_rashba(0.1)
    kwargs = {name: p[name] for name in ("V1", "V2", "V3", "J1", "J2", "J3", "mf", "nk",
                                         "maxerror")}
    kwargs.update({name: p[name] for name in ("mix", "maxite", "T") if p[name] is not None})
    kwargs["U"] = p["U"] if isinstance(p["U"], float) else \
        (lambda r: 2.5 + 0.5 * np.tanh(r[0]))
    filling = p["filling"] if isinstance(p["filling"], float) else \
        np.array([0.5 + 0.05 * np.tanh(r[0]) for r in h.geometry.r])
    kwargs.update({"mu": p["mu"]} if p["fix"] == "mu" else {"filling": filling})
    if p["engine"] == "jax":
        kwargs.update(use_jax=True, solver=p["solver"])
    np.random.seed(p["seed"])
    random.seed(p["seed"])
    direct, energy = h.get_mean_field_hamiltonian(return_total_energy=True, **kwargs)
    assert direct is not None
    assert report["notes"]["total_energy"] == pytest.approx(energy, abs=1e-10)
    assert_same_hamiltonian(built.h, direct)


def test_meanfield_names_and_bounds(pyqula):
    """The solver names come from pyqula; the filling's constants are
    checked, an expression is checked by pyqula when it runs."""
    from pyqula.scftk import densitydensity_jax

    from guiqula.engine.context import source_names
    assert source_names("jax_solvers") == densitydensity_jax.get_jax_solver_names()
    d, s, _ = system()
    with pytest.raises(Exception, match="filling: must be at most 1"):
        d.do("set_meanfield", system=s, params={"filling": 1.5})
    d.do("set_meanfield", system=s, enabled=True, params={"U": 3.0, "nk": 2, "mix": 0.5,
                                                          "filling": "0.5 + 2*x"})
    from guiqula.engine.build import BuildError
    with pytest.raises(BuildError, match=r"must lie in \[0,1\]"):
        build_system(d.document, s)                 # pyqula refuses a filling outside [0, 1]


def test_meanfield_that_does_not_converge_fails_the_build(pyqula):
    from guiqula.engine.build import BuildError
    d, s, _ = system()
    d.do("set_meanfield", system=s, enabled=True, params={"U": 3.0, "maxite": 1, "nk": 2})
    with pytest.raises(BuildError, match="did not converge"):
        build_system(d.document, s)
    deferred = build_system(d.document, s, meanfield=False)        # the interactive build
    assert deferred.reports[-1]["status"] == "deferred"


CALC_CASES = {
    "bands": [{"nk": 30}, {"nk": 30, "operator": "sz"}],
    "dos": [{"ne": 30, "nk": 8, "delta": 0.1}, {"ne": 15, "nk": 8, "delta": 0.1, "mode": "Green"},
            {"ne": 30, "nk": 8, "delta": 0.1, "operator": "sublattice"}],
}


@pytest.mark.parametrize("kind, case", [(k, i) for k in sorted(CALC_CASES)
                                        for i in range(len(CALC_CASES[k]))])
def test_calculation(pyqula, kind, case):
    from pyqula import geometry
    params = CALC_CASES[kind][case]
    d, s, _ = system(terms=[("rashba", {"c": 0.2}), ("sublattice_imbalance", {"mass": 0.1})])
    c = d.do("add_calculation", system=s, kind=kind, params=params)
    progress = []
    result = run_calculation(d.document, c, progress=lambda f, text: progress.append(f))
    h = geometry.honeycomb_lattice().get_hamiltonian(has_spin=True)
    h.add_rashba(0.2)
    h.add_sublattice_imbalance(0.1)
    if kind == "bands":
        out = h.get_bands(write=False, **params)
        nk = len(np.unique(out[0]))
        assert np.allclose(result.arrays["energies"], out[1].reshape(nk, -1), rtol=0, atol=1e-12)
        if "operator" in params:
            assert np.allclose(result.arrays["weights"], out[2].reshape(nk, -1), rtol=0, atol=1e-12)
            assert result.plot["kind"] == "colored_scatter"
        assert progress and progress[-1] == pytest.approx(1.0)
    else:
        p = dict(registry.get("calculation", "dos").normalize_params(params))
        kwargs = dict(energies=np.linspace(p["emin"], p["emax"], p["ne"]), delta=p["delta"],
                      nk=p["nk"], mode=p["mode"], write=False)
        if p["operator"]:
            kwargs["operator"] = p["operator"]
        es, ds = h.get_dos(**kwargs)
        assert np.allclose(result.arrays["energies"], es) and np.allclose(result.arrays["dos"], ds,
                                                                          rtol=0, atol=1e-12)


def test_every_entry_has_a_case():
    covered = {"lattice": set(LATTICES), "geometry_op": set(OP_CASES),
               "term": set(TERM_CASES), "meanfield": set(MEANFIELD_CASES),
               "calculation": set(CALC_CASES)}
    for family, kinds in covered.items():
        assert kinds == set(registry.kinds(family)), family
