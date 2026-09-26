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

entry("term", "kane_mele", "Kane-Mele spin-orbit coupling",
      FieldParam("t", 0.05, "strength", "intrinsic spin-orbit coupling between second neighbours, "
                                        "at the bond midpoint"),
      group="Spin-orbit", formula=r"i\lambda_{SO} \sum_{\langle\langle ij\rangle\rangle} \nu_{ij} "
                                  r"c^\dagger_i \sigma_z c_j",
      doc="Intrinsic spin-orbit coupling of the Kane-Mele model: a Haldane coupling of opposite "
          "sign for each spin; preserves time reversal.",
      requires=("spin",), call=Call("h.add_kane_mele", "t"))

def _antiferromagnetism(h, ctx):
    components = ctx.value("m")
    h.add_antiferromagnetism(lambda r, c=components: [f(r) if callable(f) else f for f in c])


def _antiferromagnetism_script(ctx):
    return [f"afm = {ctx.code('m')}",
            "h.add_antiferromagnetism(lambda r: [f(r) if callable(f) else f for f in afm])"]


# pyqula reads a list as one value per site, so the exchange vector always
# goes in as a function of position returning (mx, my, mz)
entry("term", "antiferromagnetism", "Antiferromagnetic exchange",
      VectorFieldParam("m", (0.0, 0.0, 0.1), "exchange (mx, my, mz)",
                       "staggered exchange field: +m on sublattice A, -m on B"),
      group="Magnetism", formula=r"\sum_i \tau_i\, \vec m(\vec r_i)\cdot\vec\sigma_i",
      doc="Exchange field whose sign alternates between the two sublattices (Neel "
          "order); needs a bipartite geometry.",
      requires=("spin",), apply=_antiferromagnetism, script=_antiferromagnetism_script)

entry("term", "swave", "s-wave pairing",
      FieldParam("delta", 0.1, "pairing", "singlet pairing amplitude on every site"),
      group="Superconductivity", formula=r"\sum_i \Delta(\vec r_i)\, c^\dagger_{i\uparrow} "
                                         r"c^\dagger_{i\downarrow} + h.c.",
      doc="Onsite spin-singlet superconducting pairing; turns the Hamiltonian into Nambu form.",
      requires=("nambu",), call=Call("h.add_swave", "delta"))
