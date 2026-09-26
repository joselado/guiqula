"""The cost guard (PLAN.md 13.12): an order-of-magnitude estimate of how
long a calculation takes, from the Hilbert-space dimension the
interactive build reports and the calculation's parameters, so the window
can show it and ask before starting something that takes minutes.

The model counts dense diagonalizations, which is what bands and the ED
density of states do at every k-point, and what the mean field does at
every k-point of every iteration: seconds = count * (A N**3 + B) for a
dimension N. A and B were measured on the development machine under load
(2026-09-26: numpy eigh of a complex Hermitian matrix, two BLAS threads).
It tells a second from a minute from an hour, nothing finer.

pyqula-free and Qt-free: the UI process calls it with a build summary.
"""
from guiqula.registry import pipeline

A = 2e-9                 # seconds per N**3 of one dense diagonalization
B = 2e-4                 # seconds of overhead per k-point
DENSE_DIMENSION = 10000  # pyqula's limits.densedimension (the UI process cannot import pyqula)
SLOW = 60.0              # seconds above which the window asks before running


def diagonalization(dimension):
    return A * float(dimension) ** 3 + B


def kmesh(nk, dimensionality):
    """k-points of a mesh with nk per periodic direction."""
    return max(int(nk), 1) ** int(dimensionality)


def meanfield_iterations(params):
    """A guess: plain linear mixing converges in about 10/mix iterations
    (mix 0.1 when not given), the jax root finders in a few tens."""
    if params.get("engine") == "jax" and params.get("solver") not in ("linear_mixing",
                                                                      "fixed_point"):
        guess = 30
    else:
        guess = max(10, int(10 / (params.get("mix") or 0.1)))
    limit = params.get("maxite")
    return guess if limit is None else min(limit, guess)


def estimate(document, calc_id, builds):
    """{"seconds", "dimension", "sites", "dense_limit", "meanfield"} for a
    calculation, or None when its system is not built (or the calculation
    cannot run). meanfield: the seconds of the mean field in the total."""
    plan = pipeline.plan_calculation(document, calc_id)
    build = builds.get(plan.system_id)
    if plan.problem or build is None or plan.spec is None or plan.spec.cost is None:
        return None
    size = {"dimension": int(build["dimension"]), "dimensionality": int(build["dimensionality"]),
            "sites": int(build["sites"])}
    seconds = float(plan.spec.cost(plan.params, size))
    meanfield = 0.0
    stage = plan.system.meanfield
    if stage is not None and stage.applied and stage.spec.cost is not None:
        meanfield = float(stage.spec.cost(stage.params, size))
    return {"seconds": seconds + meanfield, "meanfield": meanfield,
            "dimension": size["dimension"], "sites": size["sites"],
            "dense_limit": size["dimension"] > DENSE_DIMENSION}


def describe(seconds):
    """A rough duration: "under a second", "about 20 s", "about 3 min"."""
    if seconds < 1:
        return "under a second"
    if seconds < 90:
        return f"about {seconds:.0f} s"
    if seconds < 90 * 60:
        return f"about {seconds / 60:.0f} min"
    if seconds < 48 * 3600:
        return f"about {seconds / 3600:.0f} h"
    return f"about {seconds / 86400:.0f} days"
