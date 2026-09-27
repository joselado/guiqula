"""An example guiqula plugin: one Hamiltonian term, the chiral Kekule
hopping of pyqula (``h.add_chiral_kekule``), which guiqula itself does not
offer.

guiqula imports this module in the window (to build its palettes and
forms) and in its worker processes (to run the entries), right after its
own registry. Two rules follow:

- import pyqula inside functions only (the window never loads pyqula; a
  ``Call`` names the pyqula call as a string, so this module needs none);
- every numeric parameter of a term is a Field (``FieldParam``): a number,
  an expression of the position, a value per region... A pyqula call that
  takes plain numbers only declares ``native=False``, which keeps the
  Field constant.

What one ``entry(...)`` declares gives the palette entry, the form, the
tooltip, the engine step, the line of the exported script and the help
(F1: the formula, the parameters, the pyqula code with the current values,
pyqula's docstring of the call, and the sections of pyqula's user guide
named by ``guide=``). Families: "lattice", "geometry_op", "term",
"meanfield", "model" and "calculation"; see guiqula/registry/*.py for
examples of each, and ``apply=``/``script=`` for an entry that needs more
than one pyqula call.
"""
from guiqula.registry import Call, entry
from guiqula.registry.params import FieldParam

entry("term", "chiral_kekule", "Chiral Kekule hopping",
      FieldParam("t1", 0.1, "t1", "first complex component of the Kekule modulation",
                 native=False),
      FieldParam("t2", 0.0, "t2", "second component of the Kekule modulation", native=False),
      group="Hopping", formula=r"\sum_{\langle ij\rangle} \delta t_{ij}(t_1, t_2)\, "
                               r"c^\dagger_i c_j",
      doc="Bond-direction-aware (chiral) Kekule modulation of the first-neighbour hopping of "
          "a honeycomb lattice; the cell must hold the Kekule pattern (a 3x3 supercell).",
      call=Call("h.add_chiral_kekule", t1="t1", t2="t2"),
      guide=("h.add_kekule() / h.add_chiral_kekule()",))
