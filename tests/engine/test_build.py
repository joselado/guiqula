"""Engine semantics (PLAN.md 3.1, 3.3): cache, mode pre-scan, skipped
entries, seeds, upstream edits re-applying downstream."""
import numpy as np

from guiqula.commands import Dispatcher
from guiqula.engine.build import BuildCache, build_system

from .conftest import assert_same_hamiltonian


def graphene():
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    op = d.do("add_geometry_op", system=s, kind="supercell", params={"n": [2, 2, 1]})
    t1 = d.do("add_term", system=s, kind="zeeman", params={"m": [0, 0, 0.2]})
    t2 = d.do("add_term", system=s, kind="rashba", params={"c": 0.1})
    return d, s, op, t1, t2


def test_cache_resumes_and_hands_out_copies(pyqula):
    d, s, op, t1, t2 = graphene()
    cache = BuildCache()
    first = build_system(d.document, s, cache)
    stored = len(cache)
    first.h.add_onsite(5.0)                          # mutating the result ...
    again = build_system(d.document, s, cache)       # ... does not reach the cache
    assert not np.allclose(first.h.intra, again.h.intra)
    assert len(cache) == stored and cache.hits >= 1
    d.do("set_param", entry=t2, name="c", value=0.3)  # only the last stage re-runs
    misses = cache.misses
    build_system(d.document, s, cache)
    # one lookup misses (the changed stage), the stage before it hits
    assert len(cache) == stored + 1 and cache.misses == misses + 1


def test_upstream_edit_replays_terms(pyqula):
    """Requirement 2: change the geometry, the Hamiltonian follows."""
    from pyqula import geometry
    d, s, op, t1, t2 = graphene()
    cache = BuildCache()
    build_system(d.document, s, cache)
    d.do("set_param", entry=op, name="n", value=[3, 2, 1])
    h = geometry.honeycomb_lattice().get_supercell([3, 2, 1]).get_hamiltonian(has_spin=True)
    h.add_zeeman([0.0, 0.0, 0.2])
    h.add_rashba(0.1)
    assert_same_hamiltonian(build_system(d.document, s, cache).h, h)


def test_mode_is_fixed_before_the_first_term(pyqula):
    """A spinless request with a Zeeman term later in the stack is built
    spinful from the start, not upgraded mid-stack, and says so."""
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_construction", system=s, has_spin=False)
    t1 = d.do("add_term", system=s, kind="onsite", params={"mu": 0.1})
    t2 = d.do("add_term", system=s, kind="zeeman")
    built = build_system(d.document, s)
    assert built.mode == "spinful" and built.plan.upgraded_by == [t2]
    modes = {r["id"]: r["mode"] for r in built.reports if r["stage"] == "term"}
    assert modes == {t1: "spinful", t2: "spinful"}


def test_invalid_entry_is_skipped_and_the_rest_builds(pyqula):
    from pyqula import geometry
    d = Dispatcher()
    s = d.do("add_system", lattice="square_lattice")
    bad = d.do("add_term", system=s, kind="sublattice_imbalance")
    ok = d.do("add_term", system=s, kind="onsite", params={"mu": 0.3})
    off = d.do("add_term", system=s, kind="rashba", enabled=False)
    built = build_system(d.document, s)
    status = {r["id"]: (r["status"], r["message"]) for r in built.reports if r["id"]}
    assert status[bad][0] == "invalid" and "sublattice" in status[bad][1]
    assert status[ok] == ("ok", None) and status[off][0] == "disabled"
    h = geometry.square_lattice().get_hamiltonian(has_spin=True)
    h.add_onsite(0.3)
    assert_same_hamiltonian(built.h, h)


def test_seeded_disorder_reproduces_and_differs_by_seed(pyqula):
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_geometry_op", system=s, kind="supercell", params={"n": [3, 3, 1]})
    t = d.do("add_term", system=s, kind="anderson_disorder", params={"seed": 3})
    a = build_system(d.document, s).h
    np.random.rand(100)                             # disturb the global generator
    b = build_system(d.document, s).h
    assert_same_hamiltonian(a, b)
    d.do("set_param", entry=t, name="seed", value=4)
    c = build_system(d.document, s).h
    assert not np.allclose(a.intra, c.intra)


def test_interactive_builds_are_sparse_above_the_dense_limit(pyqula):
    """PLAN.md phase 5, part 3: a Hamiltonian above the limit is built sparse
    for the canvas (and says so), the same Hamiltonian as the dense one."""
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_geometry_op", system=s, kind="supercell", params={"n": [3, 3, 1]})
    d.do("add_term", system=s, kind="zeeman", params={"m": [0.0, 0.0, "0.1*x"]})
    dense = build_system(d.document, s)
    assert not dense.h.is_sparse                     # 18 sites spinful: 36
    sparse = build_system(d.document, s, sparse_above=30)
    assert sparse.h.is_sparse
    construction = next(r for r in sparse.reports if r["stage"] == "construction")
    assert "sparse matrices for the canvas (dimension 36" in construction["warnings"][0]
    assert_same_hamiltonian(dense.h, sparse.h)
    assert sparse.sparse_for_canvas and not dense.sparse_for_canvas
    assert not build_system(d.document, s, sparse_above=36).h.is_sparse


def test_the_cache_is_bounded_by_memory(pyqula):
    """A dense Hamiltonian of 10,000 sites is 1.5 GB: the cache counts bytes
    (PLAN.md phase 5, part 3)."""
    from guiqula.engine.build import nbytes
    d, s, op, t1, t2 = graphene()
    built = build_system(d.document, s)
    size = nbytes(built.h)
    assert size >= built.h.intra.nbytes > 0 and nbytes(built.g) > 0
    cache = BuildCache(memory=2.5 * size)
    cache.put("a", built.h, {})
    cache.put("b", built.h, {})
    assert len(cache) == 2 and cache.bytes == 2 * size
    cache.put("c", built.h, {})                      # the oldest goes
    assert len(cache) == 2 and cache.get("a") is None and cache.get("b") is not None
    cache.put("b", built.h, {})                      # again: counted once
    assert cache.bytes == 2 * size
    small = BuildCache(memory=size / 2)
    small.put("big", built.h, {})                    # larger than the budget: not kept
    assert len(small) == 0 and small.bytes == 0
    small.put("geometry", built.g, {})
    assert len(small) == 1
