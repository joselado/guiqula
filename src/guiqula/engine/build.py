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
  and then report it as "deferred".
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


class BuildCache:
    """Objects after each applied stage, keyed by stage key (LRU)."""

    def __init__(self, size=128):
        self.size = size
        self._items = OrderedDict()
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
        self._items[key] = (obj.copy(), dict(info))
        self._items.move_to_end(key)
        while len(self._items) > self.size:
            self._items.popitem(last=False)

    def clear(self):
        self._items.clear()


def mode_of(h):
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


def _apply_stage(stage, obj):
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

    ctx = ApplyContext(stage.spec, stage.params, region=stage.region, regions=stage.regions)
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
        else:
            stage.spec.apply(work, ctx)
        return work
    try:
        new, record["output"] = _run(step)
    except Exception as error:
        record["message"] = f"{type(error).__name__}: {error}"
        new = obj
    if stage.stage == "term":
        record["mode"] = mode_of(new)
    return new, record


def build_system(document, system_id, cache=None, meanfield=True):
    """Build one system; returns a Built with the Hamiltonian and a report
    per stage: status "ok", "disabled", "invalid" (with the message) or,
    for a mean field left out with meanfield=False, "deferred"."""
    vendoring.ensure_pyqula_on_path()
    plan = pipeline.plan_system(document, system_id)
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
        obj, info[stage.key] = _apply_stage(stage, obj)
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
            mode = record.get("mode") or mode
        if stage.stage in ("construction", "term", "meanfield"):
            report["mode"] = mode
        reports.append(report)
    return Built(system_id=system_id, h=obj, plan=plan, reports=reports,
                 mode=mode_of(obj), key=plan.key)
