"""Geometry operations: each takes the geometry built so far and returns a
new one (PLAN.md 3.1). pyqula's methods that change a geometry in place
(center, shift, set_finite, add_strain) are wrapped by in_place(): the
engine hands every op its own copy, so changing it and returning it is
the same as returning a new one."""
from guiqula.core.nearest import nearest_indices, nearest_site
from guiqula.registry.base import G, Call, entry
from guiqula.registry.params import (BoolParam, ConditionParam, FloatParam, FloatVectorParam,
                                     IntParam, IntVectorParam, PositionsParam)


def in_place(method, *names):
    """apply and script of an op calling g.<method>(*params) in place."""
    def apply(g, ctx):
        getattr(g, method)(*[ctx.value(name) for name in names])
        return g

    def script(ctx):
        return [f"g.{method}({', '.join(ctx.code(name) for name in names)})"]
    return {"apply": apply, "script": script, "pyqula": (f"g.{method}",)}


entry("geometry_op", "supercell", "Supercell",
      IntVectorParam("n", (1, 1, 1), "repetitions", "cells along each lattice vector", minimum=1),
      group="Cell", doc="Repeat the cell along the lattice vectors.",
      call=Call("g.get_supercell", "n"))

entry("geometry_op", "ribbon", "Ribbon",
      IntParam("n", 10, "width", "number of cells across the ribbon", minimum=1),
      IntVectorParam("boundary", (1, 0), "boundary", "direction of the edge, in lattice vectors"),
      group="Dimensionality", doc="Cut a two-dimensional lattice into a periodic ribbon.",
      call=Call("ribbon.bulk2ribbon", G, n="n", boundary="boundary"))

# pyqula builds a 7n x 7n supercell of the geometry it is given, centres it,
# and keeps the sites inside a regular polygon of inradius 1.5 n (in units of
# the first-neighbour distance), so the size does not depend on the cell.
# nedges is always passed: with geo= given, pyqula's default comes from
# name="square" (4), whatever the lattice.
entry("geometry_op", "island", "Island",
      FloatParam("n", 3.0, "size", "the polygon's inradius is 1.5 n", minimum=0.5),
      IntParam("nedges", 6, "edges", "number of edges of the polygon", minimum=3),
      FloatParam("rot", 0.0, "rotation", "rotation of the lattice before the cut, in radians"),
      BoolParam("clean", True, "clean edges", "remove sites with a single neighbour, repeatedly"),
      group="Dimensionality", doc="Cut a finite polygon-shaped flake out of a periodic "
                                  "geometry (pyqula.islands).",
      call=Call("islands.get_geometry", geo=G, n="n", nedges="nedges", rot="rot", clean="clean"))


# the sites are matched by core.nearest (a cell hash), never by an N x M
# array of distances: removing half of a 7,200-site flake took 1.7 GB; the
# exported script defines nearest_site, the same match one site at a time
def _remove_atoms(g, ctx):
    import numpy as np
    positions = np.array(ctx.value("positions"), dtype=float).reshape(-1, 3)
    if len(positions) == 0:
        return g.copy()
    picked = nearest_indices(positions, g.r, ctx.value("tol")) >= 0
    return g.remove([int(i) for i in np.nonzero(picked)[0]])


def _remove_atoms_script(ctx):
    return [f"removed = np.array({ctx.code('positions')}, dtype=float).reshape(-1, 3)",
            "if len(removed):",
            f"    find = nearest_site(removed, {ctx.code('tol')})",
            "    g = g.remove([i for i, r in enumerate(g.r) if find(r) >= 0])"]


entry("geometry_op", "remove_atoms", "Remove atoms",
      PositionsParam("positions", (), "positions", "sites to remove, by position"),
      FloatParam("tol", 0.05, "tolerance", "distance within which a site counts as picked",
                 minimum=1e-9),
      group="Sculpt", doc="Remove the sites at the stored positions (they survive a change "
                          "of the supercell upstream, indices would not).",
      apply=_remove_atoms, script=_remove_atoms_script, helpers=(nearest_site,),
      guide=("guiqula: Selections and regions",), pyqula=("g.remove",))


entry("geometry_op", "keep_where", "Keep sites where",
      ConditionParam("condition", "x**2 + y**2 < 25", "condition",
                     "an expression of x, y, z, r; the sites where it is true are kept"),
      group="Sculpt", doc="Keep only the sites where a condition on the position holds: cut "
                          "a shape (a disk: x**2 + y**2 < 25; a stripe: abs(y) < 3).",
      call=Call("sculpt.intersec", G, "condition"),
      guide=("guiqula: Selections and regions",))

entry("geometry_op", "remove_where", "Remove sites where",
      ConditionParam("condition", "x > 0", "condition",
                     "an expression of x, y, z, r; the sites where it is true are removed"),
      group="Sculpt", doc="Remove the sites where a condition on the position holds.",
      call=Call("g.remove", "condition"),
      guide=("guiqula: Selections and regions",))

entry("geometry_op", "clean", "Remove dangling sites",
      BoolParam("iterative", True, "repeat", "repeat until no site with a single neighbour is "
                                             "left"),
      group="Sculpt", doc="Remove the sites with fewer than two first neighbours (dangling "
                          "edge atoms).",
      call=Call("g.clean", iterative="iterative"))

entry("geometry_op", "finite", "Make finite",
      group="Dimensionality", doc="Drop the periodicity: the cell becomes a finite flake "
                                  "(its bonds across the cell boundary are cut).",
      **in_place("set_finite"))

entry("geometry_op", "film", "Film",
      IntParam("nz", 3, "layers", "unit cells stacked along the third lattice vector",
               minimum=1),
      group="Dimensionality", doc="Cut a three-dimensional lattice into a two-dimensional film "
                                  "(slab) nz cells thick, laid in the xy plane.",
      call=Call("films.geometry_film", G, nz="nz"))

entry("geometry_op", "orthorhombic", "Orthorhombic cell",
      group="Cell", doc="Redefine the cell as the smallest one with orthogonal lattice "
                        "vectors (same lattice).",
      call=Call("supercell.turn_orthorhombic", G))

entry("geometry_op", "rotate", "Rotate",
      FloatParam("angle", 30.0, "angle", "in degrees, clockwise about z"),
      group="Transform", doc="Rotate the sites and the lattice vectors about the z axis "
                             "(geometries up to two dimensions).",
      call=Call("g.rotate", "angle"))


def _shift(g, ctx):
    import numpy as np
    g.shift(-np.array(ctx.value("d"), dtype=float))      # pyqula's shift(r0) moves by -r0
    return g


entry("geometry_op", "shift", "Shift",
      FloatVectorParam("d", (0.5, 0.0, 0.0), "displacement", "added to every position; in a "
                                                              "periodic geometry the sites are "
                                                              "then wrapped into the cell"),
      group="Transform", doc="Move every site by a displacement.",
      apply=_shift, script=lambda ctx: [f"g.shift(-np.array({ctx.code('d')}, dtype=float))"],
      pyqula=("g.shift",))

entry("geometry_op", "center", "Center",
      group="Transform", doc="Move the geometry so that the average position is the origin.",
      **in_place("center"))

entry("geometry_op", "uniaxial_strain", "Uniaxial strain",
      FloatParam("s", 0.05, "strain", "the first lattice vector is stretched by 1 + s, the "
                                      "second by 1 - s", minimum=-0.9, maximum=0.9),
      group="Transform", doc="Strain a two-dimensional lattice: stretch a1 and compress a2 "
                             "(pyqula's Geometry.add_strain); the hoppings follow the "
                             "distances only through the construction's hopping list.",
      **in_place("add_strain", "s"))
