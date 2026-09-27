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


def pq(name):
    """A pyqula module (imported when a case runs, not at collection)."""
    import importlib
    return importlib.import_module("pyqula." + name)


# lattices whose pyqula call takes arguments: the direct call with the defaults
LATTICE_CALLS = {
    "honeycomb_zigzag_ribbon": lambda: pq("geometry").honeycomb_zigzag_ribbon(ntetramers=10),
    "honeycomb_armchair_ribbon": lambda: pq("geometry").honeycomb_armchair_ribbon(ntetramers=10),
    "square_ribbon": lambda: pq("geometry").square_ribbon(natoms=10),
    "triangular_ribbon": lambda: pq("geometry").triangular_ribbon(n=10),
    "kagome_ribbon": lambda: pq("geometry").kagome_ribbon(n=5),
    "lieb_ribbon": lambda: pq("geometry").lieb_ribbon(n=5),
    "multilayer_graphene": lambda: pq("specialgeometry").multilayer_graphene(l="AB"),
    "twisted_bilayer": lambda: pq("specialgeometry").twisted_bilayer(3),
}


@pytest.mark.parametrize("lattice", LATTICES)
def test_lattice(pyqula, lattice):
    d, s, _ = system(lattice)
    g = build_system(d.document, s).g
    direct = LATTICE_CALLS[lattice]() if lattice in LATTICE_CALLS else \
        getattr(pq("geometry"), lattice)()
    assert np.allclose(g.r, direct.r) and g.dimensionality == direct.dimensionality


def positions_equal(g1, g2):
    a = np.array(sorted(map(tuple, np.round(g1.r, 8))))
    b = np.array(sorted(map(tuple, np.round(g2.r, 8))))
    return a.shape == b.shape and np.allclose(a, b)


def honeycomb(n=None):
    g = pq("geometry").honeycomb_lattice()
    return g if n is None else g.get_supercell([n, n, 1])


def finite(g):
    g.set_finite()
    return g


def in_place(g, method, *args):
    getattr(g, method)(*args)
    return g


SUPERCELL4 = [("supercell", {"n": [4, 4, 1]})]

# kind: (params, base lattice, ops before it, the geometry built directly)
OP_CASES = {
    "supercell": ({"n": [2, 3, 1]}, "honeycomb_lattice", [],
                  lambda: honeycomb().get_supercell([2, 3, 1])),
    "ribbon": ({"n": 3}, "honeycomb_lattice", [],
               lambda: pq("ribbon").bulk2ribbon(honeycomb(), n=3, boundary=[1, 0])),
    "island": ({"n": 2.5, "nedges": 3, "rot": 0.3}, "honeycomb_lattice", [],
               lambda: pq("islands").get_geometry(geo=honeycomb(), n=2.5, nedges=3, rot=0.3,
                                                  clean=True)),
    "remove_atoms": ({"positions": [[-1.0, 0.0, 0.0]], "tol": 0.1}, "honeycomb_lattice",
                     [("supercell", {"n": [2, 2, 1]})], lambda: honeycomb(2).remove([3])),
    "keep_where": ({"condition": "x**2 + y**2 < 4"}, "honeycomb_lattice", SUPERCELL4,
                   lambda: pq("sculpt").intersec(honeycomb(4),
                                                 lambda r: r[0]**2 + r[1]**2 < 4)),
    "remove_where": ({"condition": "(x > 0) & (y > 0)"}, "honeycomb_lattice", SUPERCELL4,
                     lambda: honeycomb(4).remove(lambda r: r[0] > 0 and r[1] > 0)),
    "finite": ({}, "honeycomb_lattice", SUPERCELL4, lambda: finite(honeycomb(4))),
    "clean": ({"iterative": True}, "honeycomb_lattice",
              SUPERCELL4 + [("keep_where", {"condition": "x**2 + y**2 < 6"}), ("finite", {})],
              lambda: finite(pq("sculpt").intersec(
                  honeycomb(4), lambda r: r[0]**2 + r[1]**2 < 6)).clean(iterative=True)),
    "film": ({"nz": 3}, "cubic_lattice", [],
             lambda: pq("films").geometry_film(pq("geometry").cubic_lattice(), nz=3)),
    "orthorhombic": ({}, "triangular_lattice", [],
                     lambda: pq("supercell").turn_orthorhombic(
                         pq("geometry").triangular_lattice())),
    "rotate": ({"angle": 17.0}, "honeycomb_lattice", [], lambda: honeycomb().rotate(17.0)),
    "shift": ({"d": [0.3, -0.2, 0.1]}, "honeycomb_lattice", [],
              lambda: in_place(honeycomb(), "shift", np.array([-0.3, 0.2, -0.1]))),
    "center": ({}, "honeycomb_lattice", SUPERCELL4,
               lambda: in_place(honeycomb(4), "center")),
    "uniaxial_strain": ({"s": 0.07}, "honeycomb_lattice", [],
                        lambda: in_place(honeycomb(), "add_strain", 0.07)),
    "python": ({"code": "from pyqula import sculpt\n"
                        "g = sculpt.intersec(g, lambda r: r[0]**2 + r[1]**2 < 4)\n"},
               "honeycomb_lattice", SUPERCELL4,
               lambda: pq("sculpt").intersec(honeycomb(4), lambda r: r[0]**2 + r[1]**2 < 4)),
}


@pytest.mark.parametrize("kind", sorted(OP_CASES))
def test_geometry_op(pyqula, kind):
    params, lattice, before, direct_geometry = OP_CASES[kind]
    d, s, _ = system(lattice, ops=before + [(kind, params)])
    g = build_system(d.document, s).g
    direct = direct_geometry()
    assert len(g.r) < len(honeycomb(4).r) or kind not in ("keep_where", "remove_where", "clean")
    assert positions_equal(g, direct) and g.dimensionality == direct.dimensionality
    assert np.allclose(g.a1, direct.a1) and np.allclose(g.a2, direct.a2)


def test_remove_atoms_matches_sites_by_cells(pyqula):
    """Remove selected matches the sites through core/nearest.py: an N x M
    array of distances took 329 MB to remove half of 3,200 sites (1.7 GB
    for 7,200); the same sites go."""
    import tracemalloc
    d, s, _ = system(ops=[("supercell", {"n": [40, 40, 1]})], has_spin=False)
    d.do("set_construction", system=s, is_sparse=True)
    g = build_system(d.document, s, meanfield=False).g
    half = g.r[:, 0] > np.median(g.r[:, 0])
    d.do("add_geometry_op", system=s, kind="remove_atoms",
         params={"positions": g.r[half].tolist()})
    tracemalloc.start()
    try:
        left = build_system(d.document, s, meanfield=False).g
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 50e6, peak
    assert positions_equal(left, g.remove([int(i) for i in np.nonzero(half)[0]]))


def _interpolated(points, length):
    """Gaussian-weighted average of control points, written again here."""
    points = np.array(points, dtype=float)

    def f(r):
        w = np.exp(-((points[:, 0] - r[0]) ** 2 + (points[:, 1] - r[1]) ** 2) / (2 * length ** 2))
        return float(np.dot(w, points[:, 2]) / w.sum())
    return f


def tanh_profile(r):
    return 0.3 * np.tanh(r[0] / 4)


def painted_at(value, default):
    """A painted Field: value on the site at (-1, 0, 0), default elsewhere;
    and the direct function of a bond pyqula gets for it (by_bond_ends)."""
    field = {"kind": "painted", "sites": [[-1.0, 0.0, 0.0, value]], "default": default}

    def site(r):
        return value if np.linalg.norm(np.asarray(r) - [-1.0, 0.0, 0.0]) < 0.1 else default
    return field, lambda h: by_bond_ends(h.geometry, site)


TERM_CASES = {
    "onsite": [({"mu": 0.3}, lambda h: h.add_onsite(0.3)),
               ({"mu": "0.2*x"}, lambda h: h.add_onsite(lambda r: 0.2 * r[0])),
               ({"mu": {"kind": "profile", "name": "gaussian", "params": {"x0": 1.0}}},
                lambda h: h.add_onsite(lambda r: np.exp(-((r[0] - 1) ** 2 + r[1] ** 2) / 8))),
               ({"mu": {"kind": "interpolated", "points": [[0, 0, 0.5], [2, 0, -0.5]],
                        "length": 1.0}},
                lambda h: h.add_onsite(_interpolated([[0, 0, 0.5], [2, 0, -0.5]], 1.0))),
               ({"mu": {"kind": "painted", "sites": [[-1.0, 0.0, 0.0, 0.7]], "default": 0.1}},
                lambda h: h.add_onsite(lambda r: 0.7 if np.linalg.norm(
                    np.asarray(r) - [-1.0, 0.0, 0.0]) < 0.1 else 0.1))],
    "sublattice_imbalance": [({"mass": 0.2}, lambda h: h.add_sublattice_imbalance(0.2)),
                             ({"mass": "0.1*y"}, lambda h: h.add_sublattice_imbalance(lambda r: 0.1 * r[1]))],
    "zeeman": [({"m": [0.1, 0.0, 0.2]}, lambda h: h.add_zeeman([0.1, 0.0, 0.2])),
               ({"m": [0, 0, "0.3*tanh(x/4)"]}, lambda h: h.add_zeeman([0.0, 0.0, tanh_profile]))],
    "rashba": [({"c": 0.1}, lambda h: h.add_rashba(0.1)),
               ({"c": "0.1*cos(x)"}, lambda h: h.add_rashba(lambda r: 0.1 * np.cos(r[0]))),
               ({"c": painted_at(0.3, 0.1)[0]},       # at a bond: the mean of its ends
                lambda h: h.add_rashba(painted_at(0.3, 0.1)[1](h)))],
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
    "anti_kane_mele": [({"t": 0.05}, lambda h: h.add_anti_kane_mele(0.05)),
                       ({"t": "0.05*cos(y)"},
                        lambda h: h.add_anti_kane_mele(lambda r: 0.05 * np.cos(r[1])))],
    "modified_haldane": [({"t": 0.07}, lambda h: h.add_modified_haldane(0.07)),
                         ({"t": "0.07*tanh(x)"},
                          lambda h: h.add_modified_haldane(lambda r: 0.07 * np.tanh(r[0])))],
    "kekule": [({"t": 0.1}, lambda h: h.add_kekule(0.1)),
               ({"t": "0.1 + 0.05*x"}, lambda h: h.add_kekule(lambda r: 0.1 + 0.05 * r[0]))],
    "strain": [({"s": 1.1}, lambda h: h.add_strain(lambda r: 1.1)),
               ({"s": "1 + 0.1*x"}, lambda h: h.add_strain(lambda r: 1 + 0.1 * r[0])),
               ({"s": {"kind": "interpolated", "points": [[0, 0, 1.0], [3, 0, 1.3]],
                       "length": 2.0}},             # a callable already: exported unwrapped
                lambda h: h.add_strain(_interpolated([[0, 0, 1.0], [3, 0, 1.3]], 2.0))),
               ({"s": painted_at(1.3, 1.0)[0]},     # and the onsite energies at the sites
                lambda h: h.add_strain(painted_at(1.3, 1.0)[1](h)))],
    "valley_exchange": [({"v": [0.0, 0.1, 0.2]}, lambda h: h.add_valley_exchange([0.0, 0.1, 0.2]))],
    "crystal_field": [({"v": 0.2, "rcut": 4.0}, lambda h: h.add_crystal_field(0.2, rcut=4.0))],
    "electric_field": [({"E": [0.1, 0.0, 0.3]},
                        lambda h: h.add_onsite(lambda r: 0.1 * r[0] + 0.3 * r[2]))],
    "orbital_field": [({"B": 0.02, "gauge": "symmetric"},
                       lambda h: h.add_peierls(0.02, gauge="symmetric"))],
    "inplane_field": [({"b": 0.1, "phi": 0.3}, lambda h: h.add_inplane_bfield(b=0.1, phi=0.3))],
    "spin_spiral": [({"axis": [0, 0, 1], "q": [0.5, 0, 0]},
                     lambda h: h.generate_spin_spiral(vector=[0.0, 0.0, 1.0],
                                                      qspiral=[0.5, 0.0, 0.0]))],
    "pairing": [({"delta": 0.1, "mode": "dx2y2"}, lambda h: h.add_pairing(delta=0.1, mode="dx2y2")),
                ({"delta": "0.1*cos(x)", "mode": "triplet", "d": [1, 0, "0.5*y"]},
                 lambda h: h.add_pairing(delta=lambda r: 0.1 * np.cos(r[0]), mode="triplet",
                                         d=lambda r: [1.0, 0.0, 0.5 * r[1]])),
                ({"delta": painted_at(0.3, 0.1)[0], "mode": "dx2y2"},
                 lambda h: h.add_pairing(delta=painted_at(0.3, 0.1)[1](h), mode="dx2y2"))],
    "phase_disorder": [({"w": 0.3, "seed": 3}, None)],
    "python": [({"code": "h.add_kane_mele(0.05)", "needs": "spin"},
                lambda h: h.add_kane_mele(0.05)),
               ({"code": "h = h.copy()   # a new object\nh.add_onsite(0.2)\n"},
                lambda h: h.add_onsite(0.2))],
}
# terms tested on another system: construction and lattice
TERM_SYSTEMS = {"phase_disorder": {"has_spin": False},
                "pairing": {"finite": True},       # pyqula wants a periodic pairing function
                "valley_exchange": {"n": 3},       # a Kekule-commensurate cell
                "inplane_field": {"lattice": "multilayer_graphene", "tij": [1.0, 0.0, 0.3]}}


@pytest.mark.parametrize("kind, case", [(k, i) for k in sorted(TERM_CASES)
                                        for i in range(len(TERM_CASES[k]))])
def test_term(pyqula, kind, case):
    from pyqula import disorder, geometry, specialgeometry
    params, direct_term = TERM_CASES[kind][case]
    options = TERM_SYSTEMS.get(kind, {})
    has_spin = options.get("has_spin", True)
    lattice = options.get("lattice", "honeycomb_lattice")
    n = options.get("n", 2)
    ops = [("supercell", {"n": [n, n, 1]})] + ([("finite", {})] if options.get("finite") else [])
    d, s, _ = system(lattice, ops=ops, terms=[(kind, params)], has_spin=has_spin)
    if "tij" in options:
        d.do("set_construction", system=s, tij=options["tij"])
    built = build_system(d.document, s)
    assert [r["status"] for r in built.reports] == ["ok"] * (len(built.reports) - 1) + ["disabled"]
    g = specialgeometry.multilayer_graphene(l="AB") if lattice == "multilayer_graphene" else \
        geometry.honeycomb_lattice()
    kwargs = {"tij": options["tij"]} if "tij" in options else {}
    g = g.get_supercell([n, n, 1])
    if options.get("finite"):
        g.set_finite()
    h = g.get_hamiltonian(has_spin=has_spin, **kwargs)
    if kind == "anderson_disorder":
        np.random.seed(7)
        random.seed(7)
        disorder.anderson(h, w=0.5, p=1.0)
    elif kind == "phase_disorder":
        np.random.seed(3)
        random.seed(3)
        h.intra = disorder.phase(h, w=0.3).intra
    else:
        direct_term(h)
    assert_same_hamiltonian(built.h, h)


def test_a_factor_takes_no_region(pyqula):
    """The hopping modulation multiplies what is there: restricted to a
    region it would zero the Hamiltonian outside, so the planner refuses."""
    d, s, (t,) = system(terms=[("strain", {"s": 1.2})])
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x > 0"})
    d.do("set_region", entry=t, region=r)
    report = next(rep for rep in build_system(d.document, s).reports if rep["id"] == t)
    assert report["status"] == "invalid" and "piecewise" in report["message"]


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


@pytest.mark.parametrize("value", [0.1, "0.1 + 0.05*y"])
def test_region_restricts_a_kekule_hopping(pyqula, value):
    """pyqula's add_kekule reads a callable of two parameters as a function
    of the two ends of a bond: a Field restricted to a region is a function
    of one position only (it had default arguments, and the term was
    skipped with a numpy TypeError)."""
    from pyqula import geometry
    d, s, (t,) = system(ops=[("supercell", {"n": [3, 3, 1]})], terms=[("kekule", {"t": value})])
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x > 0"})
    d.do("set_region", entry=t, region=r)
    built = build_system(d.document, s)
    assert next(rep for rep in built.reports if rep["id"] == t)["status"] == "ok"
    h = geometry.honeycomb_lattice().get_supercell([3, 3, 1]).get_hamiltonian(has_spin=True)
    h.add_kekule(lambda r: (0.1 if value == 0.1 else 0.1 + 0.05 * r[1]) * float(r[0] > 0))
    assert_same_hamiltonian(built.h, h)


def by_bond_ends(g, site_value, rule=np.mean):
    """What pyqula gets for a Field known on the sites only, at a bond
    (core/bonds.py), written again by brute force: at a site, its value;
    elsewhere the ends of the shortest pairs of sites (of the cell and the
    cells around) symmetric about the point, their mean (or minimum)."""
    shifts = [np.zeros(3)]
    if g.dimensionality == 2:
        shifts = [i * np.asarray(g.a1) + j * np.asarray(g.a2)
                  for i in range(-2, 3) for j in range(-2, 3)]
    cell = np.asarray(g.r, dtype=float)
    points = np.concatenate([cell + s for s in shifts])
    values = np.tile([site_value(r) for r in cell], len(shifts))

    def f(m):
        m = np.asarray(m, dtype=float)
        d = np.linalg.norm(points - m, axis=1)
        if d.min() < 1e-6:
            return values[d.argmin()]
        pairs = np.linalg.norm(points[:, None] + points[None, :] - 2 * m, axis=2) < 1e-6
        a, b = np.nonzero(pairs)
        if not len(a):
            return site_value(m)
        best = d[a] < d[a].min() + 1e-6
        return rule(np.concatenate([values[a[best]], values[b[best]]]))
    return f


BOND_TERMS = [("rashba", "c", "add_rashba"), ("haldane", "t", "add_haldane"),
              ("kane_mele", "t", "add_kane_mele"), ("kekule", "t", "add_kekule")]


@pytest.mark.parametrize("finite", [False, True])
@pytest.mark.parametrize("kind, name, method", BOND_TERMS)
def test_fields_known_on_the_sites_at_the_bonds(pyqula, kind, name, method, finite):
    """pyqula evaluates these at the bond midpoints, where a painted Field
    or a region by positions found no site: the term did nothing while its
    report said ok. At a bond, a painted value is the mean of the ends',
    and a region holds the bonds whose two ends it holds; a region of
    every site, or the same value painted everywhere, is the constant."""
    from pyqula import geometry
    from guiqula.core import fields
    ops = [("supercell", {"n": [3, 3, 1]})] + ([("finite", {})] if finite else [])
    d, s, (t,) = system(ops=ops, terms=[(kind, {name: 0.1})])
    g = build_system(d.document, s).g
    right = [i for i, r in enumerate(g.r) if r[0] > 0]

    def direct(value):
        h = geometry.honeycomb_lattice().get_supercell([3, 3, 1])
        if finite:
            h.set_finite()
        h = h.get_hamiltonian(has_spin=True)
        getattr(h, method)(value)
        return h
    constant = build_system(d.document, s).h
    painted = fields.paint(0.1, g.r, right, 0.3)
    d.do("set_param", entry=t, name=name, value=painted)
    built = build_system(d.document, s)
    assert next(r for r in built.reports if r["id"] == t)["status"] == "ok"
    assert_same_hamiltonian(built.h, direct(by_bond_ends(g, lambda r: 0.3 if r[0] > 0 else 0.1)))
    d.do("set_param", entry=t, name=name, value=fields.paint(0.0, g.r, range(len(g.r)), 0.1))
    assert_same_hamiltonian(build_system(d.document, s).h, constant)
    d.do("set_param", entry=t, name=name, value=0.1)
    region = d.do("add_region", system=s, select={"kind": "positions", "tol": 0.05,
                                                  "positions": g.r[right].tolist()})
    d.do("set_region", entry=t, region=region)
    inside = by_bond_ends(g, lambda r: float(r[0] > 0), np.min)
    assert_same_hamiltonian(build_system(d.document, s).h, direct(lambda r: 0.1 * inside(r)))
    d.do("set_region", entry=t, region=None)
    d.do("set_param", entry=t, name=name, value={"kind": "piecewise", "default": 0.02,
                                                  "pieces": [{"region": region, "value": 0.1}]})
    assert_same_hamiltonian(build_system(d.document, s).h,
                            direct(lambda r: 0.1 if inside(r) else 0.02))
    everywhere = d.do("add_region", system=s, select={"kind": "positions", "tol": 0.05,
                                                      "positions": g.r.tolist()})
    d.do("set_param", entry=t, name=name, value=0.1)
    d.do("set_region", entry=t, region=everywhere)
    assert_same_hamiltonian(build_system(d.document, s).h, constant)


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


def calc_system(name):
    """(dispatcher, system id) of a test system built through commands, and
    the same Hamiltonian built directly."""
    from pyqula import geometry, islands
    d = Dispatcher()
    if name == "rashba":           # spinful, gapped, time-reversal broken by nothing
        s = d.do("add_system", lattice="honeycomb_lattice")
        d.do("add_term", system=s, kind="rashba", params={"c": 0.2})
        d.do("add_term", system=s, kind="sublattice_imbalance", params={"mass": 0.1})
        h = geometry.honeycomb_lattice().get_hamiltonian(has_spin=True)
        h.add_rashba(0.2)
        h.add_sublattice_imbalance(0.1)
    elif name == "haldane":        # spinless Chern insulator
        s = d.do("add_system", lattice="honeycomb_lattice")
        d.do("set_construction", system=s, has_spin=False)
        d.do("add_term", system=s, kind="haldane", params={"t": 0.1})
        h = geometry.honeycomb_lattice().get_hamiltonian(has_spin=False)
        h.add_haldane(0.1)
    elif name == "kane_mele":      # quantum spin Hall insulator
        s = d.do("add_system", lattice="honeycomb_lattice")
        d.do("add_term", system=s, kind="kane_mele", params={"t": 0.05})
        h = geometry.honeycomb_lattice().get_hamiltonian(has_spin=True)
        h.add_kane_mele(0.05)
    elif name == "zeeman":         # a spin-polarized metal
        s = d.do("add_system", lattice="honeycomb_lattice")
        d.do("add_term", system=s, kind="zeeman", params={"m": [0.1, 0.0, 0.4]})
        d.do("add_term", system=s, kind="onsite", params={"mu": 0.3})
        h = geometry.honeycomb_lattice().get_hamiltonian(has_spin=True)
        h.add_zeeman([0.1, 0.0, 0.4])
        h.add_onsite(0.3)
    elif name == "flake":          # a finite Haldane island
        s = d.do("add_system", lattice="honeycomb_lattice")
        d.do("set_construction", system=s, has_spin=False)
        d.do("add_geometry_op", system=s, kind="island", params={"n": 2.0, "nedges": 3})
        d.do("add_term", system=s, kind="haldane", params={"t": 0.1})
        g = islands.get_geometry(geo=geometry.honeycomb_lattice(), n=2.0, nedges=3, rot=0.0,
                                 clean=True)
        h = g.get_hamiltonian(has_spin=False)
        h.add_haldane(0.1)
    elif name in ("spins", "gas", "ising"):      # classical systems: h is the model
        kind, lattice, n, terms, setup = {
            "spins": ("classical_spin", "triangular_lattice", 3, [("heisenberg", {})], {}),
            "gas": ("lattice_gas", "triangular_lattice", 6,
                    [("gas_interaction", {"J1": 1.0})], {"filling": 1 / 3}),
            "ising": ("ising", "square_lattice", 6, [("ising_interaction", {})], {})}[name]
        d, s, _ = classical(kind, lattice, n, terms, model_params=setup)
        h = direct_model(kind, lattice, n, **setup)
        for term, params in terms:
            h.add_heisenberg(Jij=[1.0]) if term == "heisenberg" else \
                h.add_interaction(Jij=[params.get("J1", 1.0)])
    elif name == "chain":          # one-dimensional, for the surface DOS at its end
        s = d.do("add_system", lattice="chain")
        d.do("set_construction", system=s, has_spin=False)
        d.do("add_term", system=s, kind="onsite", params={"mu": 0.2})
        h = geometry.chain().get_hamiltonian(has_spin=False)
        h.add_onsite(0.2)
    else:
        raise KeyError(name)
    return d, s, h


def _energies(p):
    return np.linspace(p["emin"], p["emax"], p["ne"])


def _direct_path(h, p):
    """The k-points and vertex indices of a k-path, as the adapter makes them."""
    from guiqula.registry import kpaths
    g = h.geometry
    return kpaths.path_points(np.array([g.b1, g.b2, g.b3]), kpaths.vertices_of(g, p["kpath"]),
                              p["nk"])


def _direct_bands(h, p):
    kwargs = {"nk": p["nk"]} if p["operator"] is None else {"nk": p["nk"],
                                                             "operator": p["operator"]}
    ticks = None
    if p["kpath"] is not None:
        kwargs["kpath"], ticks = _direct_path(h, p)
    out = h.get_bands(write=False, **kwargs)
    nk = len(np.unique(out[0]))
    arrays = {"k": np.unique(out[0]), "energies": out[1].reshape(nk, -1)}
    if p["operator"] is not None:
        arrays["weights"] = out[2].reshape(nk, -1)
    if ticks is not None:
        arrays["ticks"] = ticks
    return arrays


def _direct_spectral(h, p):
    extra, ticks = {}, None
    if p["kpath"] is not None:
        extra["kpath"], ticks = _direct_path(h, p)
    arrays = dict(zip(("k", "energies", "weight"), pq("kdos").kdos_bands(
        h, energies=_energies(p), delta=p["delta"], nk=p["nk"], mode=p["mode"], **_op(p),
        **extra)))
    if ticks is not None:
        arrays["ticks"] = ticks
    return arrays


def _direct_dos(h, p):
    kwargs = dict(energies=_energies(p), delta=p["delta"], nk=p["nk"], mode=p["mode"],
                  write=False)
    if p["operator"]:
        kwargs["operator"] = p["operator"]
    np.random.seed(p["seed"])
    random.seed(p["seed"])
    es, ds = h.get_dos(**kwargs)
    return {"energies": es, "dos": ds}


def _op(p):
    return {} if p.get("operator") is None else {"operator": p["operator"]}


# the arrays a direct pyqula call gives, for normalized parameters p
DIRECT = {
    "bands": _direct_bands,
    "dos": _direct_dos,
    "ldos": lambda h, p: {"ldos": h.get_ldos(e=p["energy"], delta=p["delta"], nk=p["nk"], nrep=1,
                                             write=False, return_rd=True, **_op(p))[1]},
    "density": lambda h, p: {"density": h.get_vev(nk=p["nk"])},
    "magnetization": lambda h, p: {"magnetization": h.get_magnetization(nk=p["nk"])},
    "real_space_chern": lambda h, p: {"marker": pq("topology").real_space_chern(h)[1]},
    "fermi_surface": lambda h, p: dict(zip(("kx", "ky", "weight"), h.get_fermi_surface(
        e=p["energy"], nk=p["nk"], delta=p["delta"], write=False, **_op(p)))),
    "spectral_function": _direct_spectral,
    "surface_spectral_function": lambda h, p: dict(zip(
        ("k", "energies", "surface", "bulk"), h.get_surface_kdos(
            energies=_energies(p), delta=p["delta"], nk=p["nk"], write=False, **_op(p)))),
    "berry_curvature": lambda h, p: dict(zip(("kx", "ky", "berry"), h.get_berry_curvature(
        nk=p["nk"], write=False))),
    "berry_curvature_path": lambda h, p: dict(zip(("k", "berry"), pq(
        "topology").get_berry_curvature_path(h, nk=p["nk"]))),
    "chern": lambda h, p: {"chern": h.get_chern(nk=p["nk"])},
    "spin_chern": lambda h, p: {"spin_chern": h.get_spin_chern(nk=p["nk"])},
    "z2": lambda h, p: {"z2": pq("topology").z2_invariant(h, nk=p["nk"], nt=p["nt"])},
    "gap": lambda h, p: {"gap": h.get_gap()},
    "total_energy": lambda h, p: {"energy": h.get_total_energy(nk=p["nk"])},
    "python": lambda h, p: dict(zip(("k", "e"), h.get_bands(nk=20, write=False))),
    "minimize_spins": lambda m, p: _seeded(p, lambda: (m.minimize_energy(tries=p["tries"]), {
        "magnetization": m.magnetization, "local_energy": m.get_local_energy(),
        "energy": m.energy()})[1]),
    "anneal_gas": lambda m, p: _seeded(p, lambda: (lambda es: {
        "occupation": m.den, "local_energy": m.get_local_energy(), "step": np.arange(len(es)),
        "energy": es})(m.anneal(temps=np.geomspace(p["t_start"], p["t_end"], p["temperatures"]),
                                ntries=p["ntries"]))),
    "anneal_ising": lambda m, p: _seeded(p, lambda: (lambda es_ms: {
        "spins": m.s, "local_energy": m.get_local_energy(), "local_field": m.get_local_field(),
        "step": np.arange(len(es_ms[0])), "energy": es_ms[0], "magnetization": es_ms[1]})(
        m.anneal(temps=np.geomspace(p["t_start"], p["t_end"], p["temperatures"]),
                 ntries=p["ntries"]))),
    "optical_conductivity": lambda h, p: (lambda w, sigma: {
        "omega": w, "real": sigma[:, 0, 1].real, "imag": sigma[:, 0, 1].imag})(
        *h.get_optical_conductivity(energies=_energies(p), nk=p["nk"], T=p["T"],
                                    delta=p["delta"])),
}

def _seeded(p, run):
    np.random.seed(p["seed"])
    random.seed(p["seed"])
    return run()


# kind: [(params, test system, what the result must show)]
CALC_CASES = {
    "bands": [({"nk": 30}, "rashba", None), ({"nk": 30, "operator": "sz"}, "rashba", None),
              ({"nk": 20, "kpath": ["G", "K", "M", "G"]}, "haldane",   # neighbouring K and M
               lambda a: list(a["ticks"]) == [0, 12, 18, 28]),     # |b|/sqrt3, /2sqrt3, /2
              ({"nk": 20, "kpath": [[0, 0, 0], [0.5, 0, 0], [0.5, 0.5, 0]]}, "haldane", None)],
    "dos": [({"ne": 30, "nk": 8, "delta": 0.1}, "rashba", None),
            ({"ne": 15, "nk": 8, "delta": 0.1, "mode": "Green"}, "rashba", None),
            ({"ne": 30, "nk": 8, "delta": 0.1, "operator": "sublattice"}, "rashba", None),
            ({"ne": 40, "nk": 4, "delta": 0.1, "mode": "KPM", "seed": 3}, "rashba", None)],
    "ldos": [({"energy": 0.5, "delta": 0.1, "nk": 6}, "rashba", None),
             ({"energy": 0.2, "delta": 0.1, "nk": 1, "operator": "sublattice"}, "flake", None)],
    "density": [({"nk": 6}, "zeeman", None)],
    "magnetization": [({"nk": 6}, "zeeman", lambda a: a["magnetization"][:, 2].min() < -0.05)],
    "real_space_chern": [({}, "flake", None)],
    "fermi_surface": [({"energy": 0.5, "nk": 12, "delta": 0.1}, "rashba", None)],
    "spectral_function": [({"ne": 20, "nk": 12, "delta": 0.1}, "rashba", None),
                          ({"ne": 10, "nk": 6, "delta": 0.1, "mode": "green",
                            "operator": "sz"}, "rashba", None),
                          ({"ne": 10, "nk": 8, "delta": 0.1, "kpath": ["G", "M"]}, "rashba",
                           None)],
    "surface_spectral_function": [({"ne": 10, "nk": 6, "delta": 0.05}, "haldane", None),
                                  ({"ne": 12, "delta": 0.05}, "chain", None)],
    "berry_curvature": [({"nk": 8}, "haldane", None)],
    "berry_curvature_path": [({"nk": 30}, "haldane", None)],
    "chern": [({"nk": 12}, "haldane", lambda a: abs(abs(a["chern"]) - 1) < 1e-6)],
    "spin_chern": [({"nk": 10}, "kane_mele", lambda a: abs(abs(a["spin_chern"]) - 1) < 1e-2)],
    "z2": [({"nk": 12, "nt": 12}, "kane_mele", lambda a: int(a["z2"]) == -1),   # a parity
           ({"nk": 12, "nt": 12}, "rashba", lambda a: int(a["z2"]) == 1)],
    "gap": [({}, "haldane", lambda a: a["gap"] > 0.5)],
    "total_energy": [({"nk": 8}, "rashba", None)],
    "optical_conductivity": [({"ne": 5, "nk": 6, "component": "xy"}, "haldane", None)],
    "python": [({"code": "k, e = h.get_bands(nk=20, write=False)\narrays = {'k': k, 'e': e}\n"},
                "rashba", None)],
    "minimize_spins": [({"tries": 3}, "spins", lambda a: abs(a["energy"] / 9 + 3) < 1e-3),
                       ({"tries": 2, "show": "local energy"}, "spins", None)],
    "anneal_gas": [({"ntries": 2000, "temperatures": 4}, "gas", None),
                   ({"ntries": 500, "temperatures": 2, "show": "energy"}, "gas", None)],
    "anneal_ising": [({"ntries": 2000, "temperatures": 4, "t_end": 0.1}, "ising",
                      lambda a: abs(a["spins"].mean()) == 1.0),      # a ferromagnet orders
                     ({"ntries": 500, "temperatures": 2, "show": "magnetization"}, "ising", None)],
}
PLOT_KINDS = {"ldos": "structure_scalar", "density": "structure_scalar",
              "magnetization": "structure_vector", "real_space_chern": "structure_scalar",
              "fermi_surface": "heatmap", "spectral_function": "heatmap",
              "berry_curvature": "heatmap", "chern": "scalar", "gap": "scalar"}


@pytest.mark.parametrize("kind, case", [(k, i) for k in sorted(CALC_CASES)
                                        for i in range(len(CALC_CASES[k]))])
def test_calculation(pyqula, kind, case):
    params, name, check = CALC_CASES[kind][case]
    d, s, h = calc_system(name)
    c = d.do("add_calculation", system=s, kind=kind, params=params)
    progress = []
    result = run_calculation(d.document, c, progress=lambda f, text: progress.append(f))
    p = registry.get("calculation", kind).normalize_params(params)
    expected = DIRECT[kind](h, p)
    assert set(result.arrays) == set(expected)
    for key, value in expected.items():
        assert np.allclose(result.arrays[key], np.asarray(value), rtol=0, atol=1e-10), key
    if kind in PLOT_KINDS:
        assert result.plot["kind"] == PLOT_KINDS[kind]
    if result.plot["kind"].startswith("structure_"):       # drawn on the atoms it ran on
        assert np.allclose(result.structure["positions"], np.asarray(h.geometry.r))
    else:
        assert result.structure is None
    if kind == "surface_spectral_function":                # a curve in 1D, a map in 2D
        assert result.plot["kind"] == ("lines" if name == "chain" else "heatmap")
    if kind == "bands":
        assert progress and progress[-1] == pytest.approx(1.0)
        assert result.plot["kind"] == ("colored_scatter" if p["operator"] else "lines")
    if check is not None:
        assert check(result.arrays), result.arrays


def test_terms_above_a_pairing_are_applied_before_nambu(pyqula):
    """The Hamiltonian turns Nambu at the first entry that needs it, as in
    pyqula in the stack's order: a spin spiral and Kekule hopping above a
    pairing term apply (they cannot take a Nambu Hamiltonian); below it,
    the flag says why."""
    from pyqula import geometry
    d, s, (_, spiral, kekule, swave) = system(ops=[("supercell", {"n": [3, 3, 1]})], terms=[
        ("zeeman", {"m": [0, 0, 0.3]}), ("spin_spiral", {"axis": [0, 0, 1], "q": [0.5, 0, 0]}),
        ("kekule", {"t": 0.1}), ("swave", {"delta": 0.1})])
    built = build_system(d.document, s)
    terms = [r for r in built.reports if r["stage"] == "term"]
    assert [r["status"] for r in terms] == ["ok"] * 4, terms
    assert [r["mode"] for r in terms] == ["spinful"] * 3 + ["nambu"]
    h = geometry.honeycomb_lattice().get_supercell([3, 3, 1]).get_hamiltonian(has_spin=True)
    h.add_zeeman([0.0, 0.0, 0.3])
    h.generate_spin_spiral(vector=[0.0, 0.0, 1.0], qspiral=[0.5, 0.0, 0.0])
    h.add_kekule(0.1)
    h.add_swave(0.1)
    assert_same_hamiltonian(built.h, h)
    d.do("move", entry=swave, index=0)
    reports = {r["id"]: r for r in build_system(d.document, s).reports}
    assert reports[swave]["mode"] == "nambu"
    assert reports[spiral]["status"] == "invalid"
    assert "place it above the pairing term" in reports[spiral]["message"]


def test_optical_conductivity_of_a_sparse_construction(pyqula):
    """pyqula's k-space generator takes a dense Hamiltonian only: the entry
    hands it one, and the result is the dense construction's."""
    d, s, h = calc_system("haldane")
    c = d.do("add_calculation", system=s, kind="optical_conductivity",
             params={"ne": 5, "nk": 6, "component": "xy"})
    dense = run_calculation(d.document, c)
    d.do("set_construction", system=s, is_sparse=True)
    sparse = run_calculation(d.document, c)
    for key in ("omega", "real", "imag"):
        assert np.allclose(sparse.arrays[key], dense.arrays[key], rtol=0, atol=1e-10), key


# ---- classical systems (decision 13.5)
def classical(kind, lattice, n, terms=(), model_params=None, finite=False):
    """A classical system through commands."""
    d = Dispatcher()
    s = d.do("add_system", lattice=lattice, kind=kind, model_params=model_params)
    d.do("add_geometry_op", system=s, kind="supercell", params={"n": [n, n, 1]})
    if finite:
        d.do("add_geometry_op", system=s, kind="finite")
    ids = [d.do("add_term", system=s, kind=k, params=p) for k, p in terms]
    return d, s, ids


def direct_model(kind, lattice, n, seed=1, finite=False, **setup):
    """The same model built directly, its random start drawn from seed."""
    g = getattr(pq("geometry"), lattice)().get_supercell([n, n, 1])
    if finite:
        g.set_finite()
    np.random.seed(seed)
    random.seed(seed)
    if kind == "classical_spin":
        return pq("classicalspin").SpinModel(g)
    if kind == "lattice_gas":
        return pq("latticegas").LatticeGas(g, filling=setup.get("filling", 0.5))
    return pq("latticeising").LatticeIsing(g, m=setup.get("m", 0.0))


def assert_same_model(m1, m2):
    assert type(m1) is type(m2)
    for name in ("pairs", "j", "b", "mu", "den", "s", "theta", "phi"):
        if hasattr(m2, name):
            assert np.allclose(np.asarray(getattr(m1, name)), np.asarray(getattr(m2, name)),
                               rtol=0, atol=1e-12), name


MODEL_CASES = {
    "classical_spin": ({}, "triangular_lattice"),
    "lattice_gas": ({"filling": 0.25, "seed": 4}, "triangular_lattice"),
    "ising": ({"m": 0.4, "seed": 9}, "square_lattice"),
}


@pytest.mark.parametrize("kind", sorted(MODEL_CASES))
def test_model(pyqula, kind):
    params, lattice = MODEL_CASES[kind]
    d, s, _ = classical(kind, lattice, 4, model_params=params)
    built = build_system(d.document, s)
    assert built.mode == {"classical_spin": "classical spins", "lattice_gas": "lattice gas",
                          "ising": "Ising"}[kind]
    setup = {k: v for k, v in params.items() if k != "seed"}
    assert_same_model(built.h, direct_model(kind, lattice, 4, params.get("seed", 1), **setup))


def _tensor(model):
    fun = pq("classicalspin").generating_functions(name="DM", J=0.3, v=np.array([0., 0., 1.]))
    model.add_tensor(fun)


# kind: (system kind, lattice, params, the same term applied directly)
CLASSICAL_TERM_CASES = {
    "heisenberg": [("classical_spin", "triangular_lattice", {"J1": 1.0, "J2": 0.2},
                    lambda m: m.add_heisenberg(Jij=[1.0, 0.2], Jm=[1.0, 1.0, 1.0])),
                   ("classical_spin", "triangular_lattice", {"J1": -1.0, "anisotropy": [1, 1, 0.5]},
                    lambda m: m.add_heisenberg(Jij=[-1.0], Jm=[1.0, 1.0, 0.5]))],
    "spin_field": [("classical_spin", "triangular_lattice", {"b": [0.1, 0, "0.2*tanh(x)"]},
                    lambda m: setattr(m, "b", m.b + np.array(
                        [[0.1, 0.0, 0.2 * np.tanh(r[0])] for r in m.geometry.r])))],
    "spin_tensor": [("classical_spin", "triangular_lattice", {"coupling": "DM", "J": 0.3},
                     _tensor)],
    "gas_interaction": [("lattice_gas", "triangular_lattice", {"J1": 1.0, "J3": 0.5},
                         lambda m: m.add_interaction(Jij=[1.0, 0.0, 0.5]))],
    "chemical_potential": [("lattice_gas", "triangular_lattice", {"mu": "0.1*x"},
                            lambda m: setattr(m, "mu", m.mu + np.array(
                                [0.1 * r[0] for r in m.geometry.r])))],
    "ising_interaction": [("ising", "square_lattice", {"J1": 1.0},
                           lambda m: m.add_interaction(Jij=[1.0]))],
    "ising_field": [("ising", "square_lattice", {"b": 0.3},
                     lambda m: m.add_field(np.full(len(m.geometry.r), 0.3)))],
}


@pytest.mark.parametrize("kind, case", [(k, i) for k in sorted(CLASSICAL_TERM_CASES)
                                        for i in range(len(CLASSICAL_TERM_CASES[k]))])
def test_classical_term(pyqula, kind, case):
    system_kind, lattice, params, direct_term = CLASSICAL_TERM_CASES[kind][case]
    finite = kind == "spin_tensor"                 # every pair of sites: keep it finite
    d, s, (t,) = classical(system_kind, lattice, 3, [(kind, params)], finite=finite)
    built = build_system(d.document, s)
    assert all(r["status"] == "ok" for r in built.reports), built.reports
    direct = direct_model(system_kind, lattice, 3, finite=finite)
    direct_term(direct)
    assert_same_model(built.h, direct)


def test_a_tensor_with_the_neighbouring_cells_minimizes(pyqula):
    """pyqula's add_tensor_2d makes the couplings complex (with a zero
    imaginary part), which its energy cannot take: the entry keeps them
    real, and Minimize runs."""
    d, s, _ = classical("classical_spin", "triangular_lattice", 2,
                        [("spin_tensor", {"coupling": "Heisenberg", "J": 1.0, "images": True})])
    built = build_system(d.document, s)
    assert all(r["status"] == "ok" for r in built.reports), built.reports
    direct = direct_model("classical_spin", "triangular_lattice", 2)
    direct.add_tensor_2d(pq("classicalspin").generating_functions(
        name="Heisenberg", J=1.0, v=np.array([0.0, 0.0, 1.0])), ncells=1)
    direct.j = direct.j.real
    assert not np.iscomplexobj(built.h.j)
    assert_same_model(built.h, direct)
    c = d.do("add_calculation", system=s, kind="minimize_spins")
    assert np.isfinite(run_calculation(d.document, c).arrays["magnetization"]).all()


def test_a_term_of_another_kind_is_refused():
    d, s, _ = classical("ising", "square_lattice", 2)
    with pytest.raises(Exception, match="does not apply to a ising system"):
        d.do("add_term", system=s, kind="zeeman")
    with pytest.raises(Exception, match="does not apply to a ising system"):
        d.do("add_calculation", system=s, kind="bands")
    q, qs, _ = system()
    with pytest.raises(Exception, match="does not apply to a quantum system"):
        q.do("add_term", system=qs, kind="heisenberg")


def test_every_entry_has_a_case():
    covered = {"lattice": set(LATTICES), "geometry_op": set(OP_CASES),
               "term": set(TERM_CASES) | set(CLASSICAL_TERM_CASES),
               "meanfield": set(MEANFIELD_CASES), "model": set(MODEL_CASES),
               "calculation": set(CALC_CASES) | {"sweep"}}     # sweep: test_sweeps.py
    assert set(covered) == set(registry.base.FAMILIES)
    for family, kinds in covered.items():
        assert kinds == set(registry.kinds(family)), family
