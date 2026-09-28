"""What the structure canvas draws (PLAN.md section 4): the positions,
lattice vectors, sublattice and first-neighbour bonds of a built geometry,
and what the Hamiltonian puts on them (13.8: onsite energies, exchange
fields, pairing, and every hopping with its amplitude and phase), as numpy
arrays that cross the process boundary (the UI process never loads pyqula
or scipy, PLAN.md 13.15).

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


def frame(g):
    """The reciprocal vectors (rows, a_i . b_j = delta_ij, no 2 pi) of a
    periodic geometry and the matrix taking pyqula's Cartesian mesh
    coordinates (those of its Fermi surface and Berry maps) to reduced k,
    its k2K generator as a matrix (None in one dimension, where pyqula
    does not define it); None for a finite geometry."""
    if int(g.dimensionality) == 0:
        return None
    g = g.copy()
    g.update_reciprocal()
    reciprocal = np.array([g.b1, g.b2, g.b3], dtype=float)
    k2K = None                   # pyqula defines it in two and three dimensions
    if int(g.dimensionality) > 1:
        to_reduced = g.get_k2K_generator()
        k2K = np.column_stack([np.asarray(to_reduced(np.eye(3)[i]), dtype=float).real
                               for i in range(3)])
    return {"reciprocal": reciprocal, "k2K": k2K}


def kspace(g, nk=60):
    """What the Brillouin-zone canvas draws (decision 13.9), or None for a
    finite geometry: pyqula's reciprocal vectors (rows, a_i . b_j =
    delta_ij, no 2 pi), the matrix taking the Cartesian mesh coordinates of
    pyqula's Fermi surface and Berry maps to reduced k (its k2K generator),
    the high-symmetry points pyqula names for this geometry (reduced), and
    its default path (reduced points)."""
    from guiqula.registry import kpaths
    out = frame(g)
    if out is None:
        return None
    g = g.copy()
    g.update_reciprocal()
    special = kpaths.special_points(g)
    default = np.asarray(g.get_kpath(None, nk=nk), dtype=float).reshape(-1, 3)
    return dict(out, special=special, default_path=default)


HAMILTONIAN_LIMIT = 20000     # sites; above this the Hamiltonian view is not computed


def _coo(matrix):
    from scipy import sparse
    return sparse.coo_matrix(matrix)


def _site_diagonal(matrix, n, norb):
    """The norb x norb onsite blocks of a matrix, as an (n, norb, norb) array."""
    m = _coo(matrix)
    keep = (m.row // norb) == (m.col // norb)
    blocks = np.zeros((n, norb, norb), dtype=complex)
    np.add.at(blocks, (m.row[keep] // norb, m.row[keep] % norb, m.col[keep] % norb),
              m.data[keep])
    return blocks


def _positive(cell):
    """One of each pair of cells (cell, -cell), the central one included."""
    nonzero = [c for c in cell if c]
    return not nonzero or nonzero[0] > 0


def hamiltonian_view(h, limit=HAMILTONIAN_LIMIT):
    """What the terms did (PLAN.md 13.8), or None above limit sites or, for
    a dense Hamiltonian, above pyqula's limits.densedimension. It costs about as much as
    building the Hamiltonian (pyqula copies every dense cell matrix, and
    each is scanned: 3 s for 2450 sites, dimension 4900), so the
    interactive worker computes it only when the canvas shows it.

    onsite (N,): spin-averaged onsite energy; exchange (N, 3) or None:
    the exchange field (mx, my, mz) in pyqula's extract convention; pairing
    (N,) or None: |Delta| of the onsite singlet pairing (Nambu);
    hoppings (K, 5) rows (i, j, n1, n2, n3) listed once (i < j inside the
    cell, positive half of the other cells), with amplitude (K,) the norm of
    the orbital block per orbital (|t| for a spin-independent t), phase (K,)
    the argument of its spin-independent part, and spin (K,) the norm of its
    spin-dependent part (spin-orbit, per orbital)."""
    from pyqula.limits import densedimension
    n = len(h.geometry.r)
    if n > limit or (not h.is_sparse and h.intra.shape[0] > densedimension):
        return None
    pairing = None
    if getattr(h, "has_eh", False):
        blocks = _site_diagonal(h.intra, n, 4)
        pairing = np.abs(blocks[:, 0, 2])      # e-up with h-down, pyqula's extract.swave
        h = h.copy()
        h.remove_nambu()
    norb = 2 if h.has_spin else 1
    matrices = h.get_multihopping().get_dict()
    blocks = _site_diagonal(matrices[(0, 0, 0)], n, norb)
    onsite = np.real(np.trace(blocks, axis1=1, axis2=2)) / norb
    exchange = None
    if norb == 2:
        exchange = np.stack([blocks[:, 0, 1].real, -blocks[:, 0, 1].imag,
                             (blocks[:, 0, 0] - blocks[:, 1, 1]).real / 2], axis=1)
    rows, amplitude, phase, spin = [], [], [], []
    for cell, matrix in matrices.items():
        cell = tuple(int(c) for c in cell)
        if not _positive(cell):
            continue
        m = _coo(matrix)
        i, j = m.row // norb, m.col // norb
        keep = (i < j) if not any(cell) else np.ones(len(i), dtype=bool)
        keep &= np.abs(m.data) > 1e-12
        if not np.any(keep):
            continue
        i, j, data = i[keep], j[keep], m.data[keep]
        same = (m.row[keep] % norb) == (m.col[keep] % norb)
        pairs, index = np.unique(i * n + j, return_inverse=True)
        norm2 = np.bincount(index, weights=np.abs(data) ** 2, minlength=len(pairs))
        trace = (np.bincount(index, weights=np.where(same, data.real, 0.0), minlength=len(pairs))
                 + 1j * np.bincount(index, weights=np.where(same, data.imag, 0.0),
                                    minlength=len(pairs)))
        rows.append(np.column_stack([pairs // n, pairs % n,
                                     np.tile(np.array(cell), (len(pairs), 1))]))
        amplitude.append(np.sqrt(norm2 / norb))
        phase.append(np.where(np.abs(trace) > 1e-9, np.angle(trace), 0.0))
        spin.append(np.sqrt(np.maximum(norm2 - np.abs(trace) ** 2 / norb, 0.0) / norb))
    if rows:
        hoppings = np.concatenate(rows).astype(np.int64)
        amplitude, phase, spin = (np.concatenate(a) for a in (amplitude, phase, spin))
    else:
        hoppings = np.zeros((0, 5), dtype=np.int64)
        amplitude = phase = spin = np.zeros(0)
    return {"onsite": onsite, "exchange": exchange, "pairing": pairing, "hoppings": hoppings,
            "amplitude": amplitude, "phase": phase, "spin": spin}
