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
