"""Hamiltonian terms (``Hamiltonian.add_*``). Every numeric parameter is a
Field (PLAN.md 3.8); pyqula calls each of these with a function of one
position when the Field is not constant (onsite and exchange per site,
Rashba and Haldane at the bond midpoint)."""
from guiqula.registry.base import H, Call, entry
from guiqula.registry.params import FieldParam, SeedParam, VectorFieldParam

entry("term", "onsite", "Onsite energy",
      FieldParam("mu", 0.2, "onsite energy", "energy added on every site"),
      group="Onsite", formula=r"\sum_i \mu(\vec r_i)\, c^\dagger_i c_i",
      doc="Onsite energy; a constant shifts the bands rigidly (chemical potential).",
      call=Call("h.add_onsite", "mu"))

entry("term", "sublattice_imbalance", "Sublattice imbalance",
      FieldParam("mass", 0.1, "mass", "staggered onsite energy, +mass on A and -mass on B"),
      group="Onsite", formula=r"\sum_i m(\vec r_i)\, \tau_z c^\dagger_i c_i",
      doc="Staggered onsite energy between two sublattices; needs a bipartite geometry.",
      call=Call("h.add_sublattice_imbalance", "mass"))

entry("term", "zeeman", "Zeeman / exchange field",
      VectorFieldParam("m", (0.0, 0.0, 0.1), "field (mx, my, mz)", "exchange field"),
      group="Magnetism", formula=r"\sum_i \vec m(\vec r_i)\cdot\vec\sigma_i",
      doc="Local exchange field acting on the spin; breaks time-reversal symmetry.",
      requires=("spin",), call=Call("h.add_zeeman", "m"))

entry("term", "rashba", "Rashba spin-orbit coupling",
      FieldParam("c", 0.1, "strength", "Rashba coupling, evaluated at the bond midpoint"),
      group="Spin-orbit", formula=r"i\lambda_R \sum_{\langle ij\rangle} c^\dagger_i "
                                  r"(\vec\sigma\times\vec d_{ij})_z c_j",
      doc="Rashba spin-orbit coupling between first neighbours; breaks inversion.",
      requires=("spin",), call=Call("h.add_rashba", "c"))

entry("term", "haldane", "Haldane coupling",
      FieldParam("t", 0.05, "strength", "second-neighbour imaginary hopping, at the bond midpoint"),
      group="Topology", formula=r"i t_H \sum_{\langle\langle ij\rangle\rangle} \nu_{ij} c^\dagger_i c_j",
      doc="Second-neighbour imaginary hopping of the Haldane model; breaks time reversal.",
      call=Call("h.add_haldane", "t"))

entry("term", "anderson_disorder", "Anderson disorder",
      FieldParam("w", 0.5, "strength", "onsite energies drawn uniformly in [-w, w]", native=False),
      FieldParam("p", 1.0, "probability", "probability that a site gets an impurity", native=False),
      SeedParam(),
      group="Disorder", formula=r"\sum_i \epsilon_i c^\dagger_i c_i,\ \epsilon_i\in[-w,w]",
      doc="Random onsite energies (pyqula.disorder.anderson); reproducible through the seed.",
      call=Call("disorder.anderson", H, w="w", p="p"))
