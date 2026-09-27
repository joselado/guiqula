"""Classical systems (decision 13.5, PLAN.md section 5): pyqula's
classicalspin.SpinModel (unit vectors, a tensor exchange and a field,
ground state by multistart minimization), latticegas.LatticeGas
(occupations 0/1, J n_i n_j and a chemical potential, Monte Carlo at fixed
filling) and latticeising.LatticeIsing (spins +-1, -J s_i s_j and a field,
Metropolis). Each takes the geometry and nothing of the quantum
Hamiltonian. The "model" entries build the model from the geometry (the
random initial configuration of the lattice gas and the Ising model is
drawn from the model's seed); the terms add to it; the calculations
anneal or minimize a copy and return its configuration.

In exported scripts the model is the variable ``model``. Couplings between
neighbour shells (J1, J2, J3) are constant-only Fields, as the mean
field's V and J are; a field or a chemical potential is a Field of the
position, evaluated on every site here (pyqula takes an array per site),
so it can be restricted to a region.
"""
from guiqula.registry import cost
from guiqula.registry.base import G, Call, entry
from guiqula.registry.params import (BoolParam, ChoiceParam, FieldParam, FloatParam, IntParam,
                                     SeedParam, VectorFieldParam)

SPINS, GAS, ISING = ("classical_spin",), ("lattice_gas",), ("ising",)

# ---- models
# pyqula's spin energy is a jax function, whose precision is double only after
# one of pyqula's jax modules switched jax to it (at import, globally); the
# engine always runs in double precision, and so does an exported script
DOUBLE_PRECISION = ("import jax",
                    "jax.config.update('jax_enable_x64', True)   # as guiqula's engine runs")

entry("model", "classical_spin", "Classical spins",
      group="Classical", systems=SPINS,
      doc="Classical unit vectors on the sites (pyqula's classicalspin.SpinModel), coupled "
          "by an exchange tensor and a field.",
      preamble=DOUBLE_PRECISION, call=Call("classicalspin.SpinModel", G),
      guide=("Classical spin models", "guiqula: Classical systems"))

entry("model", "lattice_gas", "Lattice gas",
      FloatParam("filling", 0.5, "filling", "fraction of the sites occupied (kept fixed by "
                                            "the Monte Carlo swaps)", minimum=0.0, maximum=1.0),
      SeedParam(doc="seed of the random initial occupation"),
      group="Classical", systems=GAS,
      doc="Classical particles that occupy a site or not (pyqula's latticegas.LatticeGas): "
          "J n_i n_j (positive J: repulsion) and a chemical potential.",
      call=Call("latticegas.LatticeGas", G, filling="filling"),
      guide=("Lattice gas models", "guiqula: Classical systems"))

entry("model", "ising", "Ising model",
      FloatParam("m", 0.0, "initial magnetization", "average spin of the random initial "
                                                    "configuration", minimum=-1.0, maximum=1.0),
      SeedParam(doc="seed of the random initial configuration"),
      group="Classical", systems=ISING,
      doc="Ising spins +-1 on the sites (pyqula's latticeising.LatticeIsing): -J s_i s_j "
          "(positive J: ferromagnetic) and a field.",
      call=Call("latticeising.LatticeIsing", G, m="m"),
      guide=("Ising models", "guiqula: Classical systems"))


# ---- shared helpers
def shells(ctx):
    """[J1, J2, J3] without the trailing zeros (at least J1), which is how
    pyqula reads a list of neighbour couplings."""
    values = [ctx.value(name) for name in ("J1", "J2", "J3")]
    while len(values) > 1 and values[-1] == 0.0:
        values.pop()
    return values


def shell_params(label, doc):
    return (FieldParam("J1", 1.0, f"{label} first neighbours", doc, native=False),
            FieldParam("J2", 0.0, f"{label} second neighbours", doc, native=False),
            FieldParam("J3", 0.0, f"{label} third neighbours", doc, native=False))


def site_values(field, positions):
    """A compiled scalar Field (a number or a function) on every site."""
    import numpy as np
    if not callable(field):
        return np.full(len(positions), float(field))
    return np.array([field(r) for r in positions], dtype=float)


def site_values_code(code):
    return (f"(lambda f: np.array([f(r) for r in model.geometry.r], dtype=float) if callable(f) "
            f"else np.full(len(model.geometry.r), f))({code})")


# ---- classical spin terms
def _heisenberg(model, ctx):
    model.add_heisenberg(Jij=shells(ctx), Jm=list(ctx.value("anisotropy")))


entry("term", "heisenberg", "Heisenberg exchange",
      *shell_params("J", "exchange S_i.J.S_j (positive: antiferromagnetic)"),
      VectorFieldParam("anisotropy", (1.0, 1.0, 1.0), "anisotropy (x, y, z)",
                       "factors of the diagonal of the exchange tensor (XXZ: 1, 1, Jz)",
                       native=False),
      group="Exchange", systems=SPINS,
      formula=r"\sum_{ij} J_{ij}\, \vec S_i\cdot \mathrm{diag}(a_x,a_y,a_z)\, \vec S_j",
      doc="Exchange between neighbour shells (pyqula's SpinModel.add_heisenberg).",
      apply=_heisenberg, script=lambda ctx: [
          f"model.add_heisenberg(Jij={shells(ctx)!r}, Jm={list(ctx.value('anisotropy'))!r})"],
      guide=("Classical spin models",), pyqula=("classicalspin.SpinModel.add_heisenberg",))


def _spin_field(model, ctx):
    import numpy as np
    b = np.stack([site_values(c, model.geometry.r) for c in ctx.value("b")], axis=1)
    model.b = model.b + b


entry("term", "spin_field", "Magnetic field",
      VectorFieldParam("b", (0.0, 0.0, 0.5), "field (bx, by, bz)", "field on every site"),
      group="Field", systems=SPINS, formula=r"\sum_i \vec b(\vec r_i)\cdot\vec S_i",
      doc="A field acting on the spins, uniform or a function of the position (it enters "
          "SpinModel.b, one vector per site).",
      apply=_spin_field, script=lambda ctx: [
          f"b = {ctx.code('b')}",
          "model.b = model.b + np.stack([" + site_values_code("c") + " for c in b], axis=1)"],
      guide=("Classical spin models",), pyqula=("classicalspin.SpinModel",))

TENSORS = ("Heisenberg", "Linear", "RKKYTI", "ZZ", "XYZ", "DM")


def _tensor(model, ctx):
    import numpy as np
    from pyqula import classicalspin
    fun = classicalspin.generating_functions(name=ctx.value("coupling"), J=ctx.value("J"),
                                             v=np.array(ctx.value("v"), dtype=float))
    if ctx.value("images") and model.geometry.dimensionality == 2:
        model.add_tensor_2d(fun, ncells=1)
    elif ctx.value("images") and model.geometry.dimensionality != 0:
        raise ValueError("couplings to the neighbouring cells are only available in two "
                         "dimensions (pyqula's add_tensor_2d); make the system finite, or two-"
                         "dimensional, or leave them out")
    else:
        model.add_tensor(fun)


def _tensor_script(ctx):
    call = "model.add_tensor_2d(fun, ncells=1)" if ctx.value("images") else "model.add_tensor(fun)"
    return [f"fun = classicalspin.generating_functions(name={ctx.code('coupling')}, "
            f"J={ctx.code('J')}, v=np.array({ctx.code('v')}, dtype=float))", call]


entry("term", "spin_tensor", "Exchange tensor",
      ChoiceParam("coupling", "DM", choices=TENSORS, label="coupling",
                  doc="Heisenberg and ZZ, XYZ between first neighbours; Linear: dipolar 1/r^3; "
                      "RKKYTI: RKKY on a topological-insulator surface; DM: "
                      "Dzyaloshinskii-Moriya with the vector v"),
      FieldParam("J", 0.2, "strength", "coupling constant", native=False),
      VectorFieldParam("v", (0.0, 0.0, 1.0), "vector v", "the DM vector's direction, or the "
                                                        "XYZ diagonal", native=False),
      BoolParam("images", False, "neighbouring cells", "include the couplings to the "
                                                       "neighbouring cells (two-dimensional "
                                                       "lattices)"),
      group="Exchange", systems=SPINS, formula=r"\sum_{ij} \vec S_i\cdot J_{ij}\,\vec S_j",
      doc="A coupling tensor from pyqula's classicalspin.generating_functions: "
          "Dzyaloshinskii-Moriya, dipolar, RKKY, Ising ZZ, anisotropic XYZ. Every pair of "
          "sites is visited, so large systems take long.",
      modules=("classicalspin",), apply=_tensor, script=_tensor_script,
      guide=("Classical spin models",), pyqula=("classicalspin.generating_functions", "classicalspin.SpinModel.add_tensor", "classicalspin.SpinModel.add_tensor_2d"))


# ---- lattice gas and Ising terms
def _interaction(model, ctx):
    model.add_interaction(Jij=shells(ctx))


for kind, systems, sign, formula in [
        ("gas_interaction", GAS, "positive: repulsion", r"\sum_{ij} J_{ij}\, n_i n_j"),
        ("ising_interaction", ISING, "positive: ferromagnetic", r"-\sum_{ij} J_{ij}\, s_i s_j")]:
    entry("term", kind, "Interaction",
          *shell_params("J", sign),
          group="Interaction", systems=systems, formula=formula,
          doc=f"Coupling between neighbour shells ({sign}; pyqula's add_interaction counts "
              f"each bond in both directions).",
          apply=_interaction, script=lambda ctx: [f"model.add_interaction(Jij={shells(ctx)!r})"])


def _chemical_potential(model, ctx):
    model.mu = model.mu + site_values(ctx.value("mu"), model.geometry.r)


entry("term", "chemical_potential", "Chemical potential",
      FieldParam("mu", 0.2, "potential", "energy of an occupied site"),
      group="Field", systems=GAS, formula=r"\sum_i \mu(\vec r_i)\, n_i",
      doc="A site-dependent energy of the occupied sites (LatticeGas.mu): it matters for the "
          "arrangement at fixed filling when it varies in space.",
      apply=_chemical_potential,
      script=lambda ctx: [f"model.mu = model.mu + {site_values_code(ctx.code('mu'))}"],
      guide=("Lattice gas models",), pyqula=("latticegas.LatticeGas",))


def _ising_field(model, ctx):
    model.add_field(site_values(ctx.value("b"), model.geometry.r))


entry("term", "ising_field", "Field",
      FieldParam("b", 0.1, "field", "field on every site"),
      group="Field", systems=ISING, formula=r"-\sum_i b(\vec r_i)\, s_i",
      doc="A field on the Ising spins, uniform or a function of the position "
          "(LatticeIsing.add_field).",
      apply=_ising_field,
      script=lambda ctx: [f"model.add_field({site_values_code(ctx.code('b'))})"],
      guide=("Ising models",), pyqula=("latticeising.LatticeIsing.add_field",))


# ---- calculations
def _minimize(model, ctx):
    import numpy as np
    model.minimize_energy(tries=ctx.value("tries"))
    return {"magnetization": np.asarray(model.magnetization),
            "local_energy": np.asarray(model.get_local_energy(), dtype=float),
            "energy": float(model.energy())}


def _minimize_plot(params):
    if params["show"] == "local energy":
        return {"kind": "structure_scalar", "values": "local_energy", "clabel": "local energy",
                "symmetric": False}
    return {"kind": "structure_vector", "vectors": "magnetization", "clabel": "spin"}


entry("calculation", "minimize_spins", "Minimize the energy",
      IntParam("tries", 10, "tries", "random starting points; the lowest energy is kept",
               minimum=1),
      SeedParam(doc="seed of the random starting points"),
      ChoiceParam("show", "texture", choices=("texture", "local energy"), label="show"),
      group="Classical", systems=SPINS,
      doc="Ground state of the classical spins: local minimizations from random starting "
          "angles, the lowest kept (SpinModel.minimize_energy). Arrows (the in-plane part) "
          "and dots (z) on the structure, or the energy of every site.",
      apply=_minimize, script=lambda ctx: [
          f"model.minimize_energy(tries={ctx.code('tries')})",
          "arrays = dict(magnetization=np.asarray(model.magnetization), "
          "local_energy=np.asarray(model.get_local_energy(), dtype=float), "
          "energy=float(model.energy()))"],
      plot=_minimize_plot,
      cost=lambda p, size: p["tries"] * (0.05 + 2e-5 * size["sites"] ** 2),
      guide=("Classical spin models",), pyqula=("classicalspin.SpinModel.minimize_energy",))


def _anneal_params(show):
    return (FloatParam("t_start", 2.0, "first temperature", minimum=0.0),
            FloatParam("t_end", 0.05, "last temperature", minimum=0.0),
            IntParam("temperatures", 10, "temperatures", "steps of the geometric cooling "
                                                         "schedule", minimum=1),
            IntParam("ntries", 10000, "moves per temperature", minimum=1),
            SeedParam(doc="seed of the Monte Carlo moves"),
            ChoiceParam("show", show[0], choices=show, label="show"))


def _temperatures(ctx):
    import numpy as np
    return np.geomspace(max(ctx.value("t_start"), 1e-12), max(ctx.value("t_end"), 1e-12),
                        ctx.value("temperatures"))


def _temperatures_code(ctx):
    return (f"np.geomspace(max({ctx.code('t_start')}, 1e-12), max({ctx.code('t_end')}, 1e-12), "
            f"{ctx.code('temperatures')})")


def _anneal_cost(p, size):
    return p["temperatures"] * p["ntries"] * 2e-5


def _gas(model, ctx):
    import numpy as np
    es = model.anneal(temps=_temperatures(ctx), ntries=ctx.value("ntries"))
    return {"occupation": np.asarray(model.den, dtype=float),
            "local_energy": np.asarray(model.get_local_energy(), dtype=float),
            "step": np.arange(len(es)), "energy": np.asarray(es, dtype=float)}


GAS_SHOW = ("occupation", "local energy", "energy")


def _gas_plot(params):
    return {"occupation": {"kind": "structure_scalar", "values": "occupation",
                           "clabel": "occupation", "symmetric": False},
            "local energy": {"kind": "structure_scalar", "values": "local_energy",
                             "clabel": "local energy", "symmetric": False},
            "energy": {"kind": "lines", "x": "step", "y": "energy", "xlabel": "Monte Carlo move",
                       "ylabel": "energy"}}[params["show"]]


entry("calculation", "anneal_gas", "Anneal",
      *_anneal_params(GAS_SHOW),
      group="Classical", systems=GAS,
      doc="Simulated annealing of the lattice gas over a decreasing temperature schedule, "
          "keeping the best configuration (LatticeGas.anneal); the occupation, the local "
          "energy, or the energy along the anneal.",
      apply=_gas, script=lambda ctx: [
          f"es = model.anneal(temps={_temperatures_code(ctx)}, ntries={ctx.code('ntries')})",
          "arrays = dict(occupation=np.asarray(model.den, dtype=float), "
          "local_energy=np.asarray(model.get_local_energy(), dtype=float), "
          "step=np.arange(len(es)), energy=np.asarray(es, dtype=float))"],
      plot=_gas_plot, cost=_anneal_cost,
      guide=("Lattice gas models",), pyqula=("latticegas.LatticeGas.anneal",))


def _ising(model, ctx):
    import numpy as np
    es, ms = model.anneal(temps=_temperatures(ctx), ntries=ctx.value("ntries"))
    return {"spins": np.asarray(model.s, dtype=float),
            "local_energy": np.asarray(model.get_local_energy(), dtype=float),
            "local_field": np.asarray(model.get_local_field(), dtype=float),
            "step": np.arange(len(es)), "energy": np.asarray(es, dtype=float),
            "magnetization": np.asarray(ms, dtype=float)}


ISING_SHOW = ("spins", "local energy", "local field", "energy", "magnetization")


def _ising_plot(params):
    on_sites = {"spins": ("spins", True), "local energy": ("local_energy", False),
                "local field": ("local_field", True)}
    show = params["show"]
    if show in on_sites:
        name, symmetric = on_sites[show]
        return {"kind": "structure_scalar", "values": name, "clabel": show,
                "symmetric": symmetric}
    return {"kind": "lines", "x": "step", "y": show, "xlabel": "Monte Carlo move",
            "ylabel": show if show == "energy" else "total magnetization"}


entry("calculation", "anneal_ising", "Anneal",
      *_anneal_params(ISING_SHOW),
      group="Classical", systems=ISING,
      doc="Simulated annealing of the Ising spins with single-spin flips over a decreasing "
          "temperature schedule, keeping the best configuration (LatticeIsing.anneal); the "
          "spins, the local energy or field, or the energy and the magnetization along it.",
      apply=_ising, script=lambda ctx: [
          f"es, ms = model.anneal(temps={_temperatures_code(ctx)}, ntries={ctx.code('ntries')})",
          "arrays = dict(spins=np.asarray(model.s, dtype=float), "
          "local_energy=np.asarray(model.get_local_energy(), dtype=float), "
          "local_field=np.asarray(model.get_local_field(), dtype=float), "
          "step=np.arange(len(es)), energy=np.asarray(es, dtype=float), "
          "magnetization=np.asarray(ms, dtype=float))"],
      plot=_ising_plot, cost=_anneal_cost,
      guide=("Ising models",), pyqula=("latticeising.LatticeIsing.anneal",))
