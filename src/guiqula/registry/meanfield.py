"""The mean-field block (PLAN.md section 5): interactions solved
self-consistently after the term stack, through pyqula's
Hamiltonian.get_mean_field_hamiltonian (VJinteraction: a Hubbard U,
density-density interactions V1..V3 and Heisenberg exchange J1..J3 between
the first three neighbour shells). pyqula returns a new Hamiltonian, or
None when the loop does not converge; the engine turns None into a failure
of the build, so a calculation never runs on a Hamiltonian that is not the
converged one.

Two engines: pyqula's numpy engine (plain linear mixing), or its jax engine
(use_jax=True) with one of the solvers pyqula lists
(densitydensity_jax.get_jax_solver_names()); the jax engine takes only
normal-state (not Nambu) Hamiltonians and a uniform filling, and pyqula
says so when asked otherwise. The filling is a Field: a function of
position fixes the occupation of every site (pyqula's per-site filling,
numpy engine only). The loop's settings (mixing, iterations, temperature)
left empty are not passed, so each engine uses its own default (numpy:
mix 0.1, 1000 iterations, T 1e-7; jax: 2000 iterations, T 1e-4, and only
the linear-mixing and Broyden solvers read the mixing).
"""
from guiqula.registry import cost
from guiqula.registry.base import entry
from guiqula.registry.params import (ChoiceParam, FieldParam, FloatParam, IntParam,
                                     SeedParam)

INTERACTIONS = ("U", "V1", "V2", "V3", "J1", "J2", "J3")
OPTIONAL = ("mix", "maxite", "T")          # None: the engine's own default


class MeanFieldError(RuntimeError):
    """The self-consistent loop did not converge."""


def _filling(ctx, h):
    """A number, or one filling per site (a Field of position)."""
    filling = ctx.value("filling")
    if not callable(filling):
        return filling
    import numpy as np
    return np.array([filling(r) for r in h.geometry.r], dtype=float)


def _kwargs(ctx, h):
    kwargs = {name: ctx.value(name) for name in INTERACTIONS}
    if ctx.value("fix") == "mu":
        kwargs["mu"] = ctx.value("mu")
    else:
        kwargs["filling"] = _filling(ctx, h)
    kwargs.update(mf=ctx.value("mf"), nk=ctx.value("nk"), maxerror=ctx.value("maxerror"))
    kwargs.update({name: ctx.value(name) for name in OPTIONAL if ctx.value(name) is not None})
    if ctx.value("engine") == "jax":
        kwargs.update(use_jax=True, solver=ctx.value("solver"))
    return kwargs


def _apply(h, ctx):
    h_mf, energy = h.get_mean_field_hamiltonian(return_total_energy=True, **_kwargs(ctx, h))
    if h_mf is None:
        limit = ctx.value("maxite")
        within = f"within {limit} iterations" if limit is not None else \
            "within the engine's iterations"
        raise MeanFieldError(f"the mean field did not converge {within} to "
                             f"{ctx.value('maxerror'):g}; raise the iterations, change the "
                             f"mixing or the solver, or try another initial guess")
    ctx.note("total_energy", float(energy))
    return h_mf


def _script(ctx):
    lines = []
    args = [f"U={ctx.code('U')}"]
    args += [f"{name}={ctx.code(name)}" for name in INTERACTIONS[1:] if ctx.value(name) != 0.0]
    if ctx.value("fix") == "mu":
        args.append(f"mu={ctx.code('mu')}")
    elif isinstance(ctx.value("filling"), float):
        args.append(f"filling={ctx.code('filling')}")
    else:
        lines.append(f"filling = np.array([({ctx.code('filling')})(r) for r in h.geometry.r])")
        args.append("filling=filling")
    args += [f"{name}={ctx.code(name)}" for name in ("mf", "nk", "maxerror")]
    args += [f"{name}={ctx.code(name)}" for name in OPTIONAL if ctx.value(name) is not None]
    if ctx.value("engine") == "jax":
        args += ["use_jax=True", f"solver={ctx.code('solver')}"]
    return lines + [f"h, total_energy = h.get_mean_field_hamiltonian({', '.join(args)}, "
                    f"return_total_energy=True)",
                    "if h is None:",
                    "    raise RuntimeError('the mean field did not converge')"]


def _cost(p, size):
    iterations = cost.meanfield_iterations(p)
    return iterations * cost.kmesh(p["nk"], size["dimensionality"]) \
        * cost.diagonalization(size["dimension"])


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
      FieldParam("filling", 0.5, "filling", "fraction of the states that are occupied (0.5: "
                                            "half filling); a function of position fixes the "
                                            "occupation of every site (numpy engine only)",
                 minimum=0.0, maximum=1.0),
      FloatParam("mu", 0.0, "chemical potential", "used when the chemical potential is fixed"),
      ChoiceParam("mf", "random", source="guesses", label="initial guess",
                  doc="the mean field the loop starts from (pyqula's meanfield guesses)"),
      SeedParam(doc="seed of a random initial guess"),
      IntParam("nk", 8, "k-points", "k-points per direction of the self-consistent mesh",
               minimum=1),
      ChoiceParam("engine", "numpy", choices=("numpy", "jax"), label="engine",
                  doc="numpy: pyqula's default engine, plain linear mixing; jax: the solvers "
                      "below (normal state and uniform filling only)"),
      ChoiceParam("solver", "newton", source="jax_solvers", label="jax solver",
                  doc="the root finder of the jax engine (ignored by the numpy engine)"),
      FloatParam("mix", None, "mixing", "fraction of the new mean field mixed in at each "
                                        "iteration; empty: the engine's default (numpy 0.1)",
                 minimum=1e-6, maximum=1.0, optional=True),
      FloatParam("maxerror", 1e-5, "tolerance", "convergence threshold on the mean field",
                 minimum=1e-14),
      IntParam("maxite", None, "iterations", "maximum number of iterations; empty: the "
                                             "engine's default (numpy 1000, jax 2000)",
               minimum=1, optional=True),
      FloatParam("T", None, "temperature", "smearing of the occupations; empty: the engine's "
                                           "default (numpy 1e-7, jax 1e-4)",
                 minimum=0.0, optional=True),
      group="Interactions",
      formula=r"U\sum_i n_{i\uparrow}n_{i\downarrow} + \sum_{ij} V_{ij}\, n_i n_j "
              r"+ \sum_{ij} J_{ij}\, \vec S_i\cdot\vec S_j",
      doc="Interactions solved at the mean-field level: the loop starts from the initial "
          "guess and iterates until the mean field is self-consistent. Runs with the "
          "calculations, not while editing.",
      requires=("spin",), apply=_apply, script=_script, cost=_cost,
      guide=("The collinear Hubbard model", "Non-collinear Hubbard model", "Long range interactions", "Setting a filling", "guiqula: The mean field"), pyqula=("h.get_mean_field_hamiltonian",))
