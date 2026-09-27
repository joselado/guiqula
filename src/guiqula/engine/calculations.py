"""Run a calculation: build its system, call the registry adapter, and wrap
the arrays in a Result (PLAN.md 3.3, 3.4)."""
import time

import numpy as np

import guiqula
from guiqula import vendoring
from guiqula.core.results import Result, ResultRef
from guiqula.engine import structure
from guiqula.engine.build import BuildError, build_system, seed
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


def _run_document_level(document, plan, cache, progress, trusted, results):
    """A sweep: its adapter runs another calculation on changed copies of
    the Document, through the same build cache."""
    from pyqula import parallel
    ctx = ApplyContext(plan.spec, plan.params, progress=progress)
    inner = plan.params["calculation"]

    def run(changed):
        return run_calculation(changed, inner, cache, None, trusted, results)
    start = time.perf_counter()
    try:
        arrays = plan.spec.apply(document, ctx, run)
    except (CalculationError, BuildError) as error:
        raise CalculationError(f"{plan.spec.label}: {error}") from error
    except Exception as error:
        raise CalculationError(f"{plan.spec.label}: {type(error).__name__}: {error}") from error
    arrays = {k: np.asarray(v) for k, v in arrays.items()}
    return Result(calculation=plan.calc_id, kind=plan.kind, key=plan.key, params=plan.params,
                  arrays=arrays, plot=plot_spec(plan.spec, plan.params, arrays),
                  reports=ctx.notes.get("reports", []),
                  mode=plan.system.mode, document=document.to_json(), reads=reads(plan.system),
                  meta={"seconds": time.perf_counter() - start, "cores": parallel.cores,
                        "guiqula": guiqula.__version__, "pyqula": provenance()})


def reads(system_plan):
    """{calculation id: ResultRef} the from_result Fields of a system read
    (the applied entries', with the arrays they read only): a result keeps
    them, so that its script can be exported as it was computed after that
    calculation ran again."""
    names, refs = {}, {}
    for stage in system_plan.stages:
        if stage.applied and stage.results:
            refs.update(stage.results)
            _arrays_read(stage.params, names)
    return {calc: ResultRef(ref.key, ref.positions,
                            {k: v for k, v in ref.arrays.items() if k in names.get(calc, ())})
            for calc, ref in refs.items()}


def _arrays_read(value, out):
    """Collect {calculation: set of array names} the from_result Fields read."""
    if isinstance(value, dict) and value.get("kind") == "from_result":
        out.setdefault(value["calculation"], set()).add(value["array"])
    elif isinstance(value, dict):
        for v in value.values():
            _arrays_read(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _arrays_read(v, out)


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
    if plan.spec.document_level:
        return _run_document_level(document, plan, cache, progress, trusted, results)
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
    if ctx.notes.get("xticks"):            # the vertices of a k-path, named
        plot["xticks"] = ctx.notes["xticks"]
    geometry = structure.describe(built.g) if plot["kind"] in STRUCTURE_PLOTS else None
    return Result(calculation=calc_id, kind=plan.kind, key=plan.key, params=plan.params,
                  arrays=arrays, plot=plot,
                  reports=built.reports, mode=built.mode, document=document.to_json(),
                  structure=geometry, reads=reads(built.plan),
                  meta={"seconds": seconds, "build_seconds": build_seconds,
                        "cores": parallel.cores,
                        "guiqula": guiqula.__version__, "pyqula": provenance()})
