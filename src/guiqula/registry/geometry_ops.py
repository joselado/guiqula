"""Geometry operations: each takes the geometry built so far and returns a
new one (PLAN.md 3.1)."""
from guiqula.registry.base import G, Call, entry
from guiqula.registry.params import FloatParam, IntParam, IntVectorParam, PositionsParam

entry("geometry_op", "supercell", "Supercell",
      IntVectorParam("n", (1, 1, 1), "repetitions", "cells along each lattice vector", minimum=1),
      group="Cell", doc="Repeat the cell along the lattice vectors.",
      call=Call("g.get_supercell", "n"))

entry("geometry_op", "ribbon", "Ribbon",
      IntParam("n", 10, "width", "number of cells across the ribbon", minimum=1),
      IntVectorParam("boundary", (1, 0), "boundary", "direction of the edge, in lattice vectors"),
      group="Dimensionality", doc="Cut a two-dimensional lattice into a periodic ribbon.",
      call=Call("ribbon.bulk2ribbon", G, n="n", boundary="boundary"))


def _remove_atoms(g, ctx):
    import numpy as np
    positions = np.array(ctx.value("positions"), dtype=float).reshape(-1, 3)
    tol = ctx.value("tol")
    if len(positions) == 0:
        return g.copy()
    d = np.linalg.norm(np.asarray(g.r)[:, None, :] - positions[None, :, :], axis=2)
    return g.remove([int(i) for i in np.nonzero(d.min(axis=1) < tol)[0]])


def _remove_atoms_script(ctx):
    return [f"removed = np.array({ctx.code('positions')}, dtype=float).reshape(-1, 3)",
            "if len(removed):",
            "    d = np.linalg.norm(np.asarray(g.r)[:, None, :] - removed[None, :, :], axis=2)",
            f"    g = g.remove([int(i) for i in np.nonzero(d.min(axis=1) < {ctx.code('tol')})[0]])"]


entry("geometry_op", "remove_atoms", "Remove atoms",
      PositionsParam("positions", (), "positions", "sites to remove, by position"),
      FloatParam("tol", 0.05, "tolerance", "distance within which a site counts as picked",
                 minimum=1e-9),
      group="Sculpt", doc="Remove the sites at the stored positions (they survive a change "
                          "of the supercell upstream, indices would not).",
      apply=_remove_atoms, script=_remove_atoms_script)
