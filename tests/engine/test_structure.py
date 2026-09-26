"""The geometry arrays the structure canvas draws (engine/structure.py)."""
import numpy as np

from guiqula.commands import Dispatcher
from guiqula.engine import structure
from guiqula.engine.build import build_system


def built(lattice, *ops):
    d = Dispatcher()
    s = d.do("add_system", lattice=lattice)
    for kind, params in ops:
        d.do("add_geometry_op", system=s, kind=kind, params=params)
    return build_system(d.document, s).g


def coordination(info):
    """Number of first neighbours of each site, counting bonds to images."""
    n = np.zeros(len(info["positions"]), dtype=int)
    for i, j in info["bonds"]:
        n[i] += 1
        n[j] += 1
    for i, j, *_ in info["image_bonds"]:
        n[i] += 1
        n[j] += 1
    return n


def test_neighbour_cells():
    assert structure.neighbour_cells(0) == []
    assert structure.neighbour_cells(1) == [(1, 0, 0)]
    assert sorted(structure.neighbour_cells(2)) == [(0, 1, 0), (1, -1, 0), (1, 0, 0), (1, 1, 0)]
    assert len(structure.neighbour_cells(3)) == 13


def test_honeycomb_supercell(pyqula):
    info = structure.describe(built("honeycomb_lattice", ("supercell", {"n": [3, 2, 1]})))
    assert info["positions"].shape == (12, 3) and info["dimensionality"] == 2
    assert np.allclose(info["lattice"][0], 3 * np.array([1.5, np.sqrt(3) / 2, 0]))
    assert sorted(set(info["sublattice"])) == [-1.0, 1.0]
    assert (coordination(info) == 3).all()             # periodic: every site has 3 bonds
    # a bond joins sites of opposite sublattice, at distance 1
    r, lattice = info["positions"], info["lattice"]
    for i, j in info["bonds"]:
        assert np.isclose(np.linalg.norm(r[i] - r[j]), 1.0)
        assert info["sublattice"][i] == -info["sublattice"][j]
    for i, j, *cell in info["image_bonds"]:
        assert np.isclose(np.linalg.norm(r[j] + np.array(cell) @ lattice - r[i]), 1.0)


def test_square_chain_bonds_to_own_image(pyqula):
    info = structure.describe(built("chain"))
    assert len(info["bonds"]) == 0 and info["image_bonds"].tolist() == [[0, 0, 1, 0, 0]]
    assert info["sublattice"] is None or len(info["sublattice"]) == 1


def test_island_has_no_images(pyqula):
    info = structure.describe(built("honeycomb_lattice", ("island", {"n": 2.0})))
    assert info["dimensionality"] == 0 and len(info["image_bonds"]) == 0
    assert 1 < coordination(info).min() and coordination(info).max() == 3   # cleaned edges


def test_cost_guard_uses_pyqulas_dense_limit(pyqula):
    """registry/cost.py copies limits.densedimension by hand (the UI process
    cannot import pyqula); a vendor refresh that changes it must fail here."""
    from pyqula import limits

    from guiqula.registry import cost
    assert cost.DENSE_DIMENSION == limits.densedimension


def test_hamiltonian_view_against_pyqula(pyqula):
    """PLAN.md 13.8: onsite and exchange as pyqula's extract gives them, one
    row per hopping pair with |t| and the phase of its spin-independent
    part, the pairing of a Nambu Hamiltonian."""
    from pyqula import geometry
    h = geometry.honeycomb_lattice().get_supercell([2, 1, 1]).get_hamiltonian(has_spin=True)
    h.add_onsite(lambda r: 0.1 * r[0])
    h.add_zeeman([0.1, 0.2, 0.3])
    h.add_haldane(0.1)
    h.add_rashba(0.2)
    view = structure.hamiltonian_view(h)
    assert np.allclose(view["onsite"], h.extract("onsite"))
    assert np.allclose(view["exchange"], np.stack([h.extract(c) for c in ("mx", "my", "mz")], 1))
    first = np.isclose(view["phase"], 0.0)
    assert first.sum() == 3 * 4 // 2                      # first neighbours: 3 per site
    assert np.allclose(view["spin"][first], view["spin"][first][0]) and view["spin"].max() > 0
    assert np.allclose(np.abs(view["phase"][~first]), np.pi / 2)    # Haldane, 6 per site
    assert (~first).sum() == 6 * 4 // 2 and view["pairing"] is None
    h.add_swave(0.3)
    nambu = structure.hamiltonian_view(h)
    assert np.allclose(nambu["pairing"], 0.3) and np.allclose(nambu["onsite"], view["onsite"])
