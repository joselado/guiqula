"""Base lattices (pyqula.geometrytk.lattices via pyqula.geometry). The group
is the dimensionality; ribbons take their width."""
from guiqula.registry.base import Call, entry
from guiqula.registry.params import IntParam, TextParam

for kind, label, group, doc in [
    ("dimer", "Dimer", "0D", "Two sites, finite."),
    ("chain", "Chain", "1D", "One-dimensional chain, one site per cell."),
    ("bichain", "Bipartite chain", "1D", "Chain with two sites per cell (two sublattices)."),
    ("ladder", "Ladder", "1D", "Two-leg square ladder."),
    ("square_lattice", "Square lattice", "2D", "Square lattice, one site per cell."),
    ("square_lattice_bipartite", "Square lattice, bipartite cell", "2D",
     "Square lattice with a four-site cell and two sublattices (Neel order fits in it)."),
    ("honeycomb_lattice", "Honeycomb lattice", "2D", "Honeycomb lattice, two sublattices "
                                                    "(graphene)."),
    ("honeycomb_lattice_zigzag", "Honeycomb lattice, zigzag cell", "2D",
     "Honeycomb lattice in a rectangular four-site cell, zigzag along x."),
    ("honeycomb_lattice_armchair", "Honeycomb lattice, armchair cell", "2D",
     "Honeycomb lattice in a rectangular four-site cell, armchair along x."),
    ("honeycomb_lattice_square_cell", "Honeycomb lattice, square cell", "2D",
     "Honeycomb lattice in a rectangular four-site cell."),
    ("honeycomb_lattice_C6", "Honeycomb lattice, C6 cell", "2D",
     "Honeycomb lattice in a six-site cell (Kekule order fits in it)."),
    ("buckled_honeycomb_lattice", "Buckled honeycomb lattice", "2D",
     "Honeycomb lattice with the two sublattices at different heights (silicene)."),
    ("triangular_lattice", "Triangular lattice", "2D", "Triangular lattice, one site per cell."),
    ("triangular_lattice_tripartite", "Triangular lattice, three-site cell", "2D",
     "Triangular lattice in a three-site cell (the 120-degree order fits in it)."),
    ("kagome_lattice", "Kagome lattice", "2D", "Kagome lattice, three sites per cell."),
    ("rectangular_kagome_lattice", "Kagome lattice, rectangular cell", "2D",
     "Kagome lattice in a rectangular twelve-site cell."),
    ("lieb_lattice", "Lieb lattice", "2D", "Lieb lattice, three sites per cell."),
    ("tetrahedral_lattice", "Tetrahedral lattice", "2D",
     "Two-dimensional layer of corner-sharing tetrahedra, four sites per cell (not flat)."),
    ("cubic_lattice", "Cubic lattice", "3D", "Simple cubic lattice, one site per cell."),
    ("cubic_lattice_bipartite", "Cubic lattice, bipartite cell", "3D",
     "Simple cubic lattice in an eight-site cell with two sublattices."),
    ("cubic_lieb_lattice", "Cubic Lieb lattice", "3D", "Three-dimensional Lieb lattice."),
    ("diamond_lattice", "Diamond lattice", "3D", "Diamond lattice, two sites per cell."),
    ("cubic_diamond_lattice", "Diamond lattice, cubic cell", "3D",
     "Diamond lattice in its eight-site cubic cell."),
    ("pyrochlore_lattice", "Pyrochlore lattice", "3D",
     "Pyrochlore lattice of corner-sharing tetrahedra, four sites per cell."),
    ("hyperhoneycomb_lattice", "Hyperhoneycomb lattice", "3D",
     "Three-dimensional hyperhoneycomb lattice, four sites per cell."),
]:
    entry("lattice", kind, label, group=group, doc=doc, call=Call(f"geometry.{kind}"))

# ribbons: periodic along x, finite across; the width in pyqula's own units
for kind, argument, default, label, what in [
    ("honeycomb_zigzag_ribbon", "ntetramers", 10, "Honeycomb zigzag ribbon",
     "four-site units across the ribbon"),
    ("honeycomb_armchair_ribbon", "ntetramers", 10, "Honeycomb armchair ribbon",
     "four-site units across the ribbon"),
    ("square_ribbon", "natoms", 10, "Square-lattice ribbon", "sites across the ribbon"),
    ("triangular_ribbon", "n", 10, "Triangular-lattice ribbon", "sites across the ribbon"),
    ("kagome_ribbon", "n", 5, "Kagome ribbon", "cells across the ribbon"),
    ("lieb_ribbon", "n", 5, "Lieb ribbon", "cells across the ribbon"),
]:
    entry("lattice", kind, label,
          IntParam("width", default, "width", what, minimum=1),
          group="1D", doc=f"{label}: periodic along x, finite across ({what}).",
          call=Call(f"geometry.{kind}", **{argument: "width"}))


entry("lattice", "multilayer_graphene", "Multilayer graphene",
      TextParam("stacking", "AB", "stacking", "one letter per layer, A B or C (AB: Bernal, "
                                              "ABC: rhombohedral)",
                pattern="[ABC]+", hint="use the letters A, B and C"),
      group="Layered", doc="Stacked honeycomb layers, 3 apart along z (pyqula's "
                           "specialgeometry.multilayer_graphene); the interlayer hopping "
                           "needs a hopping list reaching that distance.",
      call=Call("specialgeometry.multilayer_graphene", l="stacking"))

entry("lattice", "twisted_bilayer", "Twisted bilayer graphene",
      IntParam("m", 3, "twist index", "commensurate twist with 6m**2 + 6m + 2 sites per layer; "
                                      "the twist angle decreases as m grows", minimum=1),
      group="Layered", doc="Commensurate twisted bilayer graphene (pyqula's "
                           "specialgeometry.twisted_bilayer); m = 3 gives 148 sites.",
      call=Call("specialgeometry.twisted_bilayer", "m"))
