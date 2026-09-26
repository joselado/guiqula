"""Run a calculation: build its system, call the registry adapter, and wrap
the arrays in a Result (PLAN.md 3.3, 3.4)."""
import time

import numpy as np

import guiqula
from guiqula import vendoring
from guiqula.core.results import Result
from guiqula.engine.build import build_system
from guiqula.engine.context import ApplyContext
from guiqula.registry import pipeline


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


def run_calculation(document, calc_id, cache=None, progress=None):
    """Returns a Result; raises CalculationError or BuildError."""
    vendoring.ensure_pyqula_on_path()
    plan = pipeline.plan_calculation(document, calc_id)
    if plan.problem:
        raise CalculationError(f"{calc_id}: {plan.problem}")
    start = time.perf_counter()
    built = build_system(document, plan.system_id, cache)
    build_seconds = time.perf_counter() - start
    ctx = ApplyContext(plan.spec, plan.params, progress=progress)
    start = time.perf_counter()
    try:
        arrays = plan.spec.apply(built.h, ctx)
    except Exception as error:
        raise CalculationError(f"{plan.spec.label}: {type(error).__name__}: {error}") from error
    seconds = time.perf_counter() - start
    from pyqula import parallel
    plot = plan.spec.plot(plan.params) if callable(plan.spec.plot) else dict(plan.spec.plot)
    return Result(calculation=calc_id, kind=plan.kind, key=plan.key, params=plan.params,
                  arrays={k: np.asarray(v) for k, v in arrays.items()}, plot=plot,
                  reports=built.reports, mode=built.mode, document=document.to_json(),
                  meta={"seconds": seconds, "build_seconds": build_seconds,
                        "cores": parallel.cores,
                        "guiqula": guiqula.__version__, "pyqula": provenance()})
