"""Run a calculation: build its system, call the registry adapter, and wrap
the arrays in a Result (PLAN.md 3.3, 3.4)."""
import time

import numpy as np

import guiqula
from guiqula import vendoring
from guiqula.core.results import Result
from guiqula.engine import structure
from guiqula.engine.build import build_system, seed
from guiqula.engine.context import ApplyContext
from guiqula.registry import pipeline

STRUCTURE_PLOTS = ("structure_scalar", "structure_vector")   # drawn on the atoms


class CalculationError(RuntimeError):
    pass


def provenance():
    """Which pyqula ran: origin, path, version and, for the vendored copy in
    a checkout, the upstream commit recorded in vendor/VENDOR.md."""
    import re
    from pathlib import Path

    import pyqula
    out = {"origin": None, "path": None, "version": getattr(pyqula, "__version__", None),
           "commit": None}
    if vendoring.location is not None:
        out["origin"], out["path"] = vendoring.location[0], str(vendoring.location[1])
        vendor_md = Path(vendoring.location[1]) / "VENDOR.md"
        if vendor_md.is_file():
            match = re.search(r"Upstream HEAD at copy time: `([0-9a-f]+)`", vendor_md.read_text())
            out["commit"] = match.group(1) if match else None
    return out


def plot_spec(spec, params, arrays):
    """The plot of a result: a dict, or a callable of the parameters, or of
    the parameters and the arrays (when the drawing depends on what came
    out, a curve for a one-dimensional system and a map otherwise)."""
    import inspect
    plot = spec.plot
    if not callable(plot):
        return dict(plot)
    if len(inspect.signature(plot).parameters) == 2:
        return plot(params, arrays)
    return plot(params)


def run_calculation(document, calc_id, cache=None, progress=None, trusted=True, results=None):
    """Returns a Result; raises CalculationError or BuildError. trusted:
    whether Python nodes run (PLAN.md 13.7); results: {calculation id:
    ResultRef} the from_result Fields read."""
    vendoring.ensure_pyqula_on_path()
    plan = pipeline.plan_calculation(document, calc_id, trusted, results)
    if plan.problem:
        raise CalculationError(f"{calc_id}: {plan.problem}")
    start = time.perf_counter()
    built = build_system(document, plan.system_id, cache, trusted=trusted, results=results)
    build_seconds = time.perf_counter() - start
    ctx = ApplyContext(plan.spec, plan.params, progress=progress)
    start = time.perf_counter()
    try:
        seed(plan.spec, plan.params)
        arrays = plan.spec.apply(built.h, ctx)
    except Exception as error:
        raise CalculationError(f"{plan.spec.label}: {type(error).__name__}: {error}") from error
    seconds = time.perf_counter() - start
    from pyqula import parallel
    arrays = {k: np.asarray(v) for k, v in arrays.items()}
    plot = ctx.notes.get("plot") or plot_spec(plan.spec, plan.params, arrays)
    geometry = structure.describe(built.g) if plot["kind"] in STRUCTURE_PLOTS else None
    return Result(calculation=calc_id, kind=plan.kind, key=plan.key, params=plan.params,
                  arrays=arrays, plot=plot,
                  reports=built.reports, mode=built.mode, document=document.to_json(),
                  structure=geometry,
                  meta={"seconds": seconds, "build_seconds": build_seconds,
                        "cores": parallel.cores,
                        "guiqula": guiqula.__version__, "pyqula": provenance()})
