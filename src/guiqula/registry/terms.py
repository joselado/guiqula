"""Hamiltonian terms (``Hamiltonian.add_*``). Every numeric parameter is a
Field (PLAN.md 3.8); pyqula calls each of these with a function of one
position when the Field is not constant (onsite and exchange per site,
Rashba, Haldane, Kekule and pairing at the bond midpoint). The terms whose
pyqula call takes numbers only (valley exchange, crystal field, the
orbital magnetic fields, phase disorder) declare their Fields
``native=False``, so they are constant and cannot be restricted to a
region.
"""
from guiqula.registry.base import H, Call, entry
from guiqula.registry.params import ChoiceParam, FieldParam, SeedParam, VectorFieldParam


def vector_function(components):
    """A vector Field as pyqula's vector arguments take it: the list when
    every component is a number, else one function returning the vector
    (pyqula reads a list of functions as something else)."""
    if not any(callable(c) for c in components):
        return list(components)
    return lambda r, c=components: [f(r) if callable(f) else f for f in c]


def vector_function_code(code):
    """Script counterpart of vector_function, for the source of a list."""
    return (f"(lambda c: c if not any(callable(f) for f in c) else "
            f"(lambda r: [f(r) if callable(f) else f for f in c]))({code})")

entry("term", "onsite", "Onsite energy",
      FieldParam("mu", 0.2, "onsite energy", "energy added on every site"),
      group="Onsite", formula=r"\sum_i \mu(\vec r_i)\, c^\dagger_i c_i",
      doc="Onsite energy; a constant shifts the bands rigidly (chemical potential).",
      call=Call("h.add_onsite", "mu"),
      guide=("Including an onsite energy",))

entry("term", "sublattice_imbalance", "Sublattice imbalance",
      FieldParam("mass", 0.1, "mass", "staggered onsite energy, +mass on A and -mass on B"),
      group="Onsite", formula=r"\sum_i m(\vec r_i)\, \tau_z c^\dagger_i c_i",
      doc="Staggered onsite energy between two sublattices; needs a bipartite geometry.",
      call=Call("h.add_sublattice_imbalance", "mass"))

entry("term", "zeeman", "Zeeman / exchange field",
      VectorFieldParam("m", (0.0, 0.0, 0.1), "field (mx, my, mz)", "exchange field"),
      group="Magnetism", formula=r"\sum_i \vec m(\vec r_i)\cdot\vec\sigma_i",
      doc="Local exchange field acting on the spin; breaks time-reversal symmetry.",
      requires=("spin",), call=Call("h.add_zeeman", "m"),
      guide=("Including an external Zeeman field",))

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
      call=Call("h.add_haldane", "t"),
      guide=("Chern number",))

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
      requires=("spin",), call=Call("h.add_kane_mele", "t"),
      guide=("Spin Chern number and mirror Chern number", "Z2 invariant"))

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
      requires=("spin",), apply=_antiferromagnetism, script=_antiferromagnetism_script,
      pyqula=("h.add_antiferromagnetism",))

entry("term", "swave", "s-wave pairing",
      FieldParam("delta", 0.1, "pairing", "singlet pairing amplitude on every site"),
      group="Superconductivity", formula=r"\sum_i \Delta(\vec r_i)\, c^\dagger_{i\uparrow} "
                                         r"c^\dagger_{i\downarrow} + h.c.",
      doc="Onsite spin-singlet superconducting pairing; turns the Hamiltonian into Nambu form.",
      requires=("nambu",), call=Call("h.add_swave", "delta"),
      guide=("s-wave superconductivity",))

entry("term", "anti_kane_mele", "Anti Kane-Mele coupling",
      FieldParam("t", 0.05, "strength", "second-neighbour spin-orbit coupling of opposite sign "
                                        "on the two sublattices, at the bond midpoint"),
      group="Spin-orbit", formula=r"i\lambda \sum_{\langle\langle ij\rangle\rangle} \tau_i "
                                  r"\nu_{ij} c^\dagger_i \sigma_z c_j",
      doc="Kane-Mele coupling whose sign alternates between the sublattices (pyqula's "
          "add_anti_kane_mele); needs a geometry with sublattices, does nothing without.",
      requires=("spin",), call=Call("h.add_anti_kane_mele", "t"))

entry("term", "modified_haldane", "Modified (anti) Haldane coupling",
      FieldParam("t", 0.05, "strength", "second-neighbour imaginary hopping of opposite sign on "
                                        "the two sublattices, at the bond midpoint"),
      group="Topology", formula=r"i t \sum_{\langle\langle ij\rangle\rangle} \tau_i \nu_{ij} "
                                r"c^\dagger_i c_j",
      doc="Haldane coupling whose sign alternates between the sublattices (the anti-Haldane "
          "or modified Haldane model); needs a geometry with sublattices.",
      call=Call("h.add_modified_haldane", "t"))

entry("term", "kekule", "Kekule hopping",
      FieldParam("t", 0.1, "strength", "hopping added on the Kekule bonds, at the bond "
                                       "midpoint"),
      group="Hopping", formula=r"\sum_{\langle ij\rangle \in K} t(\vec r_{ij})\, "
                               r"c^\dagger_i c_j",
      doc="Kekule bond order on the honeycomb lattice: extra hopping on one bond in three, "
          "tripling the cell (use a supercell or the C6 cell that holds the pattern).",
      call=Call("h.add_kekule", "t"))


def _strain(h, ctx):
    s = ctx.value("s")
    h.add_strain(s if callable(s) else (lambda r, c=s: c))


def _strain_script(ctx):
    s = ctx.code("s")
    return [f"h.add_strain({s})" if s.startswith("lambda") else f"h.add_strain(lambda r: {s})"]


entry("term", "strain", "Hopping modulation",
      FieldParam("s", 1.1, "factor", "multiplies every matrix element at the bond midpoint "
                                     "(onsite energies at the site)"),
      group="Hopping", formula=r"H_{ij} \to s\left(\frac{\vec r_i+\vec r_j}{2}\right) H_{ij}",
      doc="Scale the matrix elements already in the Hamiltonian by a factor that depends on "
          "the position (pyqula's add_strain, scalar mode): a strain or a smooth "
          "hopping modulation. It acts on the terms above it.",
      apply=_strain, script=_strain_script, regions=False,
      pyqula=("h.add_strain",))

entry("term", "valley_exchange", "Valley exchange",
      VectorFieldParam("v", (0.0, 0.0, 0.1), "field (vx, vy, vz)", "valley-pseudospin field",
                       native=False),
      group="Valley", formula=r"\vec v\cdot\vec\tau",
      doc="Exchange field acting on the valley pseudospin (the valley analogue of a Zeeman "
          "field), from pyqula's in-plane valley operators: honeycomb lattices, periodic ones "
          "in a supercell whose size is a multiple of 3 (the Kekule pattern must fit).",
      call=Call("h.add_valley_exchange", "v"))

entry("term", "crystal_field", "Crystal field",
      FieldParam("v", 0.1, "strength", "largest onsite energy difference it creates",
                 native=False),
      FieldParam("rcut", 6.0, "cutoff", "sites within this distance contribute", native=False,
                 minimum=0.1),
      group="Onsite", formula=r"\sum_i V_i c^\dagger_i c_i,\ V_i \propto \sum_{j} 1/|r_i-r_j|",
      doc="Electrostatic onsite energy from the neighbouring sites (pyqula's crystalfield."
          "hartree): edge and defect sites get a different onsite energy; normalized to v.",
      call=Call("h.add_crystal_field", "v", rcut="rcut"))


def _electric_field(h, ctx):
    import numpy as np
    e = np.array(ctx.value("E"), dtype=float)
    h.add_onsite(lambda r, e=e: float(np.dot(e, r)))


entry("term", "electric_field", "Electric field",
      VectorFieldParam("E", (0.0, 0.0, 0.1), "field (Ex, Ey, Ez)",
                       "onsite energy gradient, E per unit length", native=False),
      group="Fields", formula=r"\sum_i (\vec E\cdot\vec r_i)\, c^\dagger_i c_i",
      doc="A uniform potential gradient: the onsite energy grows as E.r (a gate bias across "
          "layers, with E along z).",
      apply=_electric_field,
      script=lambda ctx: [f"h.add_onsite(lambda r: float(np.dot(np.array({ctx.code('E')}), r)))"],
      guide=("Including an onsite energy",), pyqula=("h.add_onsite",))

entry("term", "orbital_field", "Orbital magnetic field",
      FieldParam("B", 0.01, "field", "flux through a unit area in units of the flux quantum",
                 native=False),
      ChoiceParam("gauge", "Landau", choices=("Landau", "symmetric"), label="gauge"),
      group="Fields", formula=r"t_{ij} \to t_{ij}\, e^{i\frac{2\pi}{\Phi_0}"
                              r"\int_{\vec r_j}^{\vec r_i}\vec A\cdot d\vec l}",
      doc="Out-of-plane magnetic field as Peierls phases on the hoppings (pyqula's "
          "add_peierls); a periodic system needs a supercell that holds a whole flux quantum, "
          "or it is not periodic.",
      call=Call("h.add_peierls", "B", gauge="gauge"),
      guide=("Including an external orbital field",))

entry("term", "inplane_field", "In-plane magnetic field",
      FieldParam("b", 0.1, "field", "in units of the flux quantum", native=False),
      FieldParam("phi", 0.0, "direction", "angle of the field in the plane, in units of pi",
                 native=False),
      group="Fields", formula=r"t_{ij} \to t_{ij}\, e^{i 4\pi b z_{ij} "
                              r"(\Delta x \sin\phi\pi - \Delta y \cos\phi\pi)}",
      doc="In-plane magnetic field as Peierls phases, for layered systems: the phase grows "
          "with the height z of the bond (pyqula's add_inplane_bfield).",
      call=Call("h.add_inplane_bfield", b="b", phi="phi"))

entry("term", "spin_spiral", "Spin spiral",
      VectorFieldParam("axis", (0.0, 0.0, 1.0), "rotation axis", "the spins turn about it",
                       native=False),
      VectorFieldParam("q", (0.5, 0.0, 0.0), "wavevector", "in units of the reciprocal "
                                                           "lattice vectors", native=False),
      group="Magnetism", formula=r"U(\vec r) = e^{i (\vec q\cdot\vec r)\, "
                                 r"\hat n\cdot\vec\sigma/2}",
      doc="Rotate the spin of the terms above by an angle q.r about an axis (pyqula's "
          "generate_spin_spiral): an exchange field above turns into a spin spiral.",
      requires=("spin",), call=Call("h.generate_spin_spiral", vector="axis", qspiral="q"))


def _pairing(h, ctx):
    h.add_pairing(delta=ctx.value("delta"), mode=ctx.value("mode"),
                  d=vector_function(ctx.value("d")))


entry("term", "pairing", "Superconducting pairing",
      FieldParam("delta", 0.1, "amplitude", "pairing amplitude, at the bond midpoint"),
      ChoiceParam("mode", "swave", source="pairing_modes", label="symmetry",
                  doc="the pairing symmetry, from pyqula's list (sctk.pairing)"),
      VectorFieldParam("d", (0.0, 0.0, 1.0), "d-vector (dx, dy, dz)",
                       "direction of a triplet pairing; the singlet modes ignore it"),
      group="Superconductivity", formula=r"\sum_{ij} \Delta(\vec r_{ij})\, "
                                         r"c^\dagger_i \hat\Delta_{ij} c^\dagger_j + h.c.",
      doc="Pairing of any symmetry pyqula knows (s, extended s, p, d, f, chiral, triplet "
          "with a d-vector); turns the Hamiltonian into Nambu form.",
      requires=("nambu",), apply=_pairing,
      script=lambda ctx: [f"h.add_pairing(delta={ctx.code('delta')}, mode={ctx.code('mode')}, "
                          f"d={vector_function_code(ctx.code('d'))})"],
      guide=("Spin-triplet d-vector and non-unitary superconductivity",), pyqula=("h.add_pairing",))


def _phase_disorder(h, ctx):
    from pyqula import disorder
    h.intra = disorder.phase(h, w=ctx.value("w")).intra


entry("term", "phase_disorder", "Phase disorder",
      FieldParam("w", 0.2, "strength", "random hopping phases in [-w pi, w pi]", native=False),
      SeedParam(),
      group="Disorder", formula=r"t_{ij} \to t_{ij}\, e^{i\pi\epsilon_{ij}},\ "
                                r"\epsilon_{ij}\in[-w,w]",
      doc="Random phases on the hoppings inside the cell (pyqula.disorder.phase); spinless "
          "normal-state Hamiltonians only; reproducible through the seed.",
      modules=("disorder",), apply=_phase_disorder, script=lambda ctx: [
          f"h.intra = disorder.phase(h, w={ctx.code('w')}).intra"],
      pyqula=("disorder.phase",))
