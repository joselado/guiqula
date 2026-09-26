"""The mean-field block (PLAN.md section 5): interactions solved
self-consistently after the term stack, through pyqula's
Hamiltonian.get_mean_field_hamiltonian (VJinteraction: a Hubbard U,
density-density interactions V1..V3 and Heisenberg exchange J1..J3 between
the first three neighbour shells). pyqula returns a new Hamiltonian, or
None when the loop does not converge; the engine turns None into a failure
of the build, so a calculation never runs on a Hamiltonian that is not the
converged one.

The loop's own settings are passed explicitly with the numpy engine's
defaults (mix 0.1, maxite 1000, T 1e-7): pyqula tells "not given" from any
value by sentinels, and the exported script must say what ran.
"""
from guiqula.registry import cost
from guiqula.registry.base import entry
from guiqula.registry.params import (ChoiceParam, FieldParam, FloatParam, IntParam,
                                     SeedParam)

INTERACTIONS = ("U", "V1", "V2", "V3", "J1", "J2", "J3")
SETTINGS = ("mf", "nk", "mix", "maxerror", "maxite", "T")


class MeanFieldError(RuntimeError):
    """The self-consistent loop did not converge."""


def _kwargs(ctx):
    kwargs = {name: ctx.value(name) for name in INTERACTIONS}
    if ctx.value("fix") == "mu":
        kwargs["mu"] = ctx.value("mu")
    else:
        kwargs["filling"] = ctx.value("filling")
    kwargs.update({name: ctx.value(name) for name in SETTINGS})
    return kwargs


def _apply(h, ctx):
    h_mf, energy = h.get_mean_field_hamiltonian(return_total_energy=True, **_kwargs(ctx))
    if h_mf is None:
        raise MeanFieldError(f"the mean field did not converge within {ctx.value('maxite')} "
                             f"iterations to {ctx.value('maxerror'):g}; raise the iterations, "
                             f"lower the mixing or try another initial guess")
    ctx.note("total_energy", float(energy))
    return h_mf


def _script(ctx):
    args = [f"U={ctx.code('U')}"]
    args += [f"{name}={ctx.code(name)}" for name in INTERACTIONS[1:] if ctx.value(name) != 0.0]
    args.append(f"mu={ctx.code('mu')}" if ctx.value("fix") == "mu"
                else f"filling={ctx.code('filling')}")
    args += [f"{name}={ctx.code(name)}" for name in SETTINGS]
    return [f"h, total_energy = h.get_mean_field_hamiltonian({', '.join(args)}, "
            f"return_total_energy=True)",
            "if h is None:",
            "    raise RuntimeError('the mean field did not converge')"]


entry("meanfield", "interactions", "Mean-field interactions",
      FieldParam("U", 1.0, "Hubbard U", "onsite repulsion between opposite spins (negative: "
                                        "attraction, superconductivity in Nambu form)"),
      FieldParam("V1", 0.0, "V first neighbours", "density-density interaction", native=False),
      FieldParam("V2", 0.0, "V second neighbours", "density-density interaction", native=False),
      FieldParam("V3", 0.0, "V third neighbours", "density-density interaction", native=False),
      FieldParam("J1", 0.0, "J first neighbours", "Heisenberg exchange", native=False),
      FieldParam("J2", 0.0, "J second neighbours", "Heisenberg exchange", native=False),
      FieldParam("J3", 0.0, "J third neighbours", "Heisenberg exchange", native=False),
      ChoiceParam("fix", "filling", choices=("filling", "mu"), label="keep fixed",
                  doc="the filling (the chemical potential follows it at every iteration), "
                      "or the chemical potential"),
      FloatParam("filling", 0.5, "filling", "fraction of the states that are occupied "
                                            "(0.5: half filling)", minimum=0.0, maximum=1.0),
      FloatParam("mu", 0.0, "chemical potential", "used when the chemical potential is fixed"),
      ChoiceParam("mf", "random", source="guesses", label="initial guess",
                  doc="the mean field the loop starts from (pyqula's meanfield guesses)"),
      SeedParam(doc="seed of a random initial guess"),
      IntParam("nk", 8, "k-points", "k-points per direction of the self-consistent mesh",
               minimum=1),
      FloatParam("mix", 0.1, "mixing", "fraction of the new mean field mixed in at each "
                                       "iteration", minimum=1e-6, maximum=1.0),
      FloatParam("maxerror", 1e-5, "tolerance", "convergence threshold on the mean field",
                 minimum=1e-14),
      IntParam("maxite", 1000, "iterations", "maximum number of iterations", minimum=1),
      FloatParam("T", 1e-7, "temperature", "smearing of the occupations", minimum=0.0),
      group="Interactions",
      formula=r"U\sum_i n_{i\uparrow}n_{i\downarrow} + \sum_{ij} V_{ij}\, n_i n_j "
              r"+ \sum_{ij} J_{ij}\, \vec S_i\cdot\vec S_j",
      doc="Interactions solved at the mean-field level: the loop starts from the initial "
          "guess and iterates until the mean field is self-consistent. Runs with the "
          "calculations, not while editing.",
      requires=("spin",), apply=_apply, script=_script,
      cost=lambda p, size: cost.meanfield_iterations(p)
      * cost.kmesh(p["nk"], size["dimensionality"]) * cost.diagonalization(size["dimension"]))
