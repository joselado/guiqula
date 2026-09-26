"""What the structure canvas draws (PLAN.md section 4): the positions,
lattice vectors, sublattice and first-neighbour bonds of a built geometry,
as numpy arrays that cross the process boundary (the UI process never
loads pyqula or scipy, PLAN.md 13.15).

Bonds are pyqula's own first neighbours (neighbor.find_first_neighbor,
distance 1 within 1%), the pairs the default hopping connects. Bonds to the
neighbouring cells of a periodic geometry are listed once, towards the
"positive" half of the cells (first nonzero lattice coordinate positive): a
bond (i, j, cell) joins site i of the central cell to site j of that cell,
and its mirror (j, i, -cell) is implied.
"""
import itertools

import numpy as np


def neighbour_cells(dimensionality):
    """Lattice coordinates of the positive half of the cells around the
    central one (one of each pair cell, -cell)."""
    ranges = [(-1, 0, 1)] * dimensionality + [(0,)] * (3 - dimensionality)
    return [cell for cell in itertools.product(*ranges)
            if any(cell) and next(c for c in cell if c) > 0]


def describe(g):
    """Arrays of a geometry: positions (N, 3), lattice (3, 3) with a1, a2,
    a3 as rows, dimensionality, sublattice (N,) or None, bonds (M, 2) with
    i < j inside the cell, image_bonds (K, 5) rows (i, j, n1, n2, n3)."""
    from pyqula import neighbor
    positions = np.array(g.r, dtype=float).real.reshape(-1, 3)
    dimensionality = int(g.dimensionality)
    lattice = np.array([g.a1, g.a2, g.a3], dtype=float).real
    pairs = np.asarray(neighbor.find_first_neighbor(positions, positions), dtype=np.int64)
    bonds = pairs[pairs[:, 0] < pairs[:, 1]] if len(pairs) else np.zeros((0, 2), np.int64)
    image_bonds = []
    for cell in neighbour_cells(dimensionality):
        shifted = positions + np.array(cell, dtype=float) @ lattice
        for i, j in np.asarray(neighbor.find_first_neighbor(positions, shifted), dtype=np.int64):
            image_bonds.append((i, j, *cell))
    sublattice = None
    if getattr(g, "has_sublattice", False):
        sublattice = np.array(g.sublattice, dtype=float).real.reshape(-1)
        if len(sublattice) != len(positions):
            sublattice = None
    return {"positions": positions, "lattice": lattice, "dimensionality": dimensionality,
            "sublattice": sublattice, "bonds": bonds,
            "image_bonds": np.array(image_bonds, dtype=np.int64).reshape(-1, 5)}
