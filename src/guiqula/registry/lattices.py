"""Base lattices (pyqula.geometrytk.lattices via pyqula.geometry)."""
from guiqula.registry.base import Call, entry

for kind, label, doc in [
    ("chain", "Chain", "One-dimensional chain, one site per cell."),
    ("square_lattice", "Square lattice", "Square lattice, one site per cell."),
    ("honeycomb_lattice", "Honeycomb lattice", "Honeycomb lattice, two sublattices (graphene)."),
    ("triangular_lattice", "Triangular lattice", "Triangular lattice, one site per cell."),
    ("kagome_lattice", "Kagome lattice", "Kagome lattice, three sites per cell."),
    ("lieb_lattice", "Lieb lattice", "Lieb lattice, three sites per cell."),
]:
    entry("lattice", kind, label, group="2D" if kind != "chain" else "1D", doc=doc,
          call=Call(f"geometry.{kind}"))
