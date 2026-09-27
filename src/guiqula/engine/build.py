"""Build a system's geometry and Hamiltonian from the Document (PLAN.md 3.3).

The plan (guiqula.registry.pipeline) says which stages run and gives each a
content key. Execution:

- the object after every applied stage is cached under its key, and the
  build resumes after the last cached stage; the cache stores and hands out
  copies, because pyqula's add_* mutate in place;
- the Hamiltonian is created once in the Hilbert space the plan fixed, so no
  term upgrades it in the middle of the stack;
- a stochastic entry has numpy's global generator (which pyqula uses)
  seeded with its seed right before it runs;
- an entry pyqula rejects is flagged with pyqula's message and skipped: it
  runs on a copy, and the object before it carries on (decision 14.3). Only
  a failing base lattice, construction or mean field stops the build: a
  mean field that does not converge must not quietly hand the calculation
  the non-interacting Hamiltonian;
- the mean field (the last stage) runs only when asked for: the
  calculations ask, the interactive builds do not (``meanfield=False``),
  and then report it as "deferred";
- the interactive builds (``sparse_above``, pyqula's dense limit) build a
  Hamiltonian larger than that with sparse matrices, whatever the
  construction says: they only check the terms and draw, and a dense
  matrix of 20,000 sites takes gigabytes and half a minute a rebuild; the
  calculations build it as the Document says, and the construction report
  says so (PLAN.md phase 5, part 3);
- a classical system builds its model from the geometry (the "model"
  stage, seeded like a stochastic term) and applies its terms to copies of
  the model; ``Built.h`` is then the model (it has ``geometry`` too).
"""
import contextlib
import io
import random
from collections import OrderedDict
from dataclasses import dataclass, field

from guiqula import vendoring
from guiqula.engine.context import ApplyContext, apply_call
from guiqula.registry import pipeline


class BuildError(RuntimeError):
    """The system cannot be built at all."""


def _memory_budget():
    """An eighth of the machine's memory (a session runs two or three
    workers), between 1 and 8 GB (2 GB when it cannot be told): what the
    cached objects of a worker may take."""
    import os
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):
        return 2e9
    return min(max(total / 8, 1e9), 8e9)


MEMORY = _memory_budget()


def nbytes(obj):
    """Roughly the memory of a geometry, Hamiltonian or model: its arrays
    and matrices (dense or sparse), and those of its hoppings."""
    total = 0
    parts = list(vars(obj).values()) if hasattr(obj, "__dict__") else []
    for value in parts + [getattr(h, "m", None) for h in getattr(obj, "hopping", None) or []
                          if hasattr(h, "m")]:
        if hasattr(value, "nbytes") and isinstance(getattr(value, "nbytes"), int):
            total += value.nbytes                                    # numpy
        elif hasattr(value, "data") and hasattr(value, "indices"):    # scipy sparse
            total += value.data.nbytes + value.indices.nbytes + value.indptr.nbytes
    return total


class BuildCache:
    """Objects after each applied stage, keyed by stage key (LRU), at most
    size of them and at most memory bytes together: a dense Hamiltonian of
    10,000 sites takes 1.5 GB, and a cache counting entries only grew by
    that much at every edit (PLAN.md phase 5, part 3). An object larger
    than the budget is not kept."""

    def __init__(self, size=128, memory=MEMORY):
        self.size = size
        self.memory = memory
        self._items = OrderedDict()
        self.bytes = 0
        self.hits = 0
        self.misses = 0

    def __len__(self):
        return len(self._items)

    def get(self, key):
        item = self._items.get(key)
        if item is None:
            self.misses += 1
            return None
        self.hits += 1
        self._items.move_to_end(key)
        return item[0].copy(), dict(item[1])

    def put(self, key, obj, info):
        size = nbytes(obj)
        if key in self._items:
            self.bytes -= self._items.pop(key)[2]
        if size > self.memory:
            return
        self._items[key] = (obj.copy(), dict(info), size)
        self.bytes += size
        while len(self._items) > self.size or self.bytes > self.memory:
            self.bytes -= self._items.popitem(last=False)[1][2]

    def clear(self):
        self._items.clear()
        self.bytes = 0


def mode_of(h):
    """spinless, spinful or nambu; None for a classical model."""
    if not hasattr(h, "intra"):
        return None
    if getattr(h, "has_eh", False):
        return "nambu"
    return "spinful" if h.has_spin else "spinless"


@dataclass
class Built:
    system_id: str
    h: object
    plan: object
    reports: list = field(default_factory=list)
    mode: str = ""
    key: str = ""
    sparse_for_canvas: bool = False    # built sparse against the construction (sparse_above)

    @property
    def g(self):
        return self.h.geometry


def _run(function):
    """Call function(), capturing what pyqula prints."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        value = function()
    return value, buffer.getvalue().strip()


def seed(spec, params):
    """Seed numpy's global generator (which pyqula draws from) and Python's
    with an entry's seed, if it has one (PLAN.md 3.3)."""
    seed_param = spec.seed_param
    if seed_param is not None:
        import numpy as np
        value = params[seed_param.name]
        np.random.seed(value)
        random.seed(value)


def _seed(stage):
    seed(stage.spec, stage.params)


def _apply_stage(stage, obj, sparse_above=None):
    """Returns (new object, record). record: message (None if fine),
    output (what pyqula printed), mode after the stage, notes of the entry."""
    record = {"message": None, "output": "", "mode": None, "notes": {}}
    if stage.stage == "base":
        ctx = ApplyContext(stage.spec, stage.params)
        try:
            g, record["output"] = _run(lambda: apply_call(stage.spec, ctx))
        except Exception as error:
            raise BuildError(f"base lattice {stage.kind}: {type(error).__name__}: {error}") from None
        return g, record
    if stage.stage == "construction":
        c = stage.params
        kwargs = {"has_spin": c["has_spin"], "is_sparse": c["is_sparse"]}
        dimension = len(obj.r) * (2 if c["has_spin"] else 1) * (2 if c["nambu"] else 1)
        if sparse_above is not None and not c["is_sparse"] and dimension > sparse_above:
            kwargs["is_sparse"] = True
            record["notes"]["sparse"] = (f"built with sparse matrices for the canvas (dimension "
                                         f"{dimension}, above pyqula's dense limit "
                                         f"{sparse_above}); the calculations build it dense, "
                                         f"as the construction says")
        if list(c["tij"]) != [1.0]:        # pyqula's default builder otherwise
            kwargs["tij"] = list(c["tij"])

        def construct():
            h = obj.get_hamiltonian(**kwargs)
            if c["nambu"]:
                h.turn_nambu()
            return h
        try:
            h, record["output"] = _run(construct)
        except Exception as error:
            raise BuildError(f"Hamiltonian construction: {type(error).__name__}: {error}") from None
        record["mode"] = mode_of(h)
        return h, record

    if stage.stage == "model":
        ctx = ApplyContext(stage.spec, stage.params)

        def model():
            _seed(stage)          # the initial configuration is random
            return apply_call(stage.spec, ctx, g=obj.copy())   # pyqula's models touch g
        try:
            new, record["output"] = _run(model)
        except Exception as error:
            raise BuildError(f"model {stage.kind}: {type(error).__name__}: {error}") from None
        return new, record
    ctx = ApplyContext(stage.spec, stage.params, region=stage.region, regions=stage.regions,
                       results=stage.results)
    if stage.stage == "meanfield":
        def solve():
            _seed(stage)
            return stage.spec.apply(obj, ctx)       # a new Hamiltonian; obj is untouched
        try:
            h, record["output"] = _run(solve)
        except Exception as error:
            raise BuildError(f"mean field: {type(error).__name__}: {error}") from None
        record["mode"], record["notes"] = mode_of(h), dict(ctx.notes)
        return h, record

    work = obj.copy()

    def step():
        _seed(stage)
        if stage.stage == "op":
            new = apply_call(stage.spec, ctx, g=work) if stage.spec.call else \
                stage.spec.apply(work, ctx)
            if new is None or not hasattr(new, "r"):
                raise TypeError(f"{stage.kind} returned {type(new).__name__}, not a geometry")
            return new
        if stage.spec.call:
            apply_call(stage.spec, ctx, h=work)
            return work
        new = stage.spec.apply(work, ctx)       # a term changes h, or returns a new one
        if new is None:
            return work
        if not hasattr(new, "intra"):
            raise TypeError(f"{stage.kind} returned {type(new).__name__}, not a Hamiltonian")
        return new
    try:
        new, record["output"] = _run(step)
    except Exception as error:
        record["message"] = f"{type(error).__name__}: {error}"
        new = obj
    if stage.stage == "term":
        record["mode"] = mode_of(new)
    return new, record


def double_precision():
    """Run jax in double precision. pyqula switches jax to it globally when
    one of its jax modules is imported (the workers import one at start,
    to list the jax solvers), and its classical spin energy is a jax
    function: without this, the same model minimizes to another texture
    depending on what was imported before."""
    import jax
    jax.config.update("jax_enable_x64", True)


def build_system(document, system_id, cache=None, meanfield=True, trusted=True, results=None,
                 sparse_above=None):
    """Build one system; returns a Built with the Hamiltonian and a report
    per stage: status "ok", "disabled", "invalid" (with the message) or,
    for a mean field left out with meanfield=False, "deferred". trusted:
    whether Python nodes run (PLAN.md 13.7); results: {calculation id:
    ResultRef} the from_result Fields read; sparse_above: a Hilbert
    dimension above which the Hamiltonian is built sparse (the interactive
    builds; a cache must only ever see one rule)."""
    vendoring.ensure_pyqula_on_path()
    double_precision()
    plan = pipeline.plan_system(document, system_id, trusted, results)
    if plan.problem:
        raise BuildError(plan.problem)
    stages = plan.stages if meanfield else [s for s in plan.stages if s.stage != "meanfield"]
    obj, info, resume = None, {}, -1
    if cache is not None:
        for i in reversed([i for i, s in enumerate(stages) if s.applied]):
            hit = cache.get(stages[i].key)
            if hit is not None:
                obj, info = hit
                resume = i
                break
    for i, stage in enumerate(stages):
        if i <= resume or not stage.applied:
            continue
        obj, info[stage.key] = _apply_stage(stage, obj, sparse_above)
        if cache is not None:
            cache.put(stage.key, obj, info)

    reports, mode, executed = [], None, {id(s) for s in stages}
    for stage in plan.stages:
        report = {"id": stage.id, "stage": stage.stage, "kind": stage.kind,
                  "status": "ok", "message": None, "output": ""}
        if not stage.enabled:
            report["status"] = "disabled"
        elif stage.problem:
            report.update(status="invalid", message=stage.problem)
        elif id(stage) not in executed:
            report.update(status="deferred", message="runs with the calculations")
        else:
            record = info.get(stage.key, {})
            if record.get("message"):
                report.update(status="invalid", message=record["message"])
            report["output"] = record.get("output", "")
            if record.get("notes"):
                report["notes"] = record["notes"]
            if record.get("notes", {}).get("sparse"):
                report.setdefault("warnings", []).append(record["notes"]["sparse"])
            mode = record.get("mode") or mode
        if stage.stage in ("construction", "term", "meanfield") and plan.kind == "quantum":
            report["mode"] = mode
        if stage.warnings:
            report["warnings"] = list(stage.warnings) + report.get("warnings", [])
        reports.append(report)
    return Built(system_id=system_id, h=obj, plan=plan, reports=reports,
                 mode=mode_of(obj) or plan.mode, key=plan.key,
                 sparse_for_canvas=any(record.get("notes", {}).get("sparse")
                                       for record in info.values()))
