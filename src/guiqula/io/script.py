"""Script export: a runnable pyqula script reproducing a calculation
(PLAN.md 3.5), the successor of quantum-lattice's "pyqula code" tab.

It is generated from the same registry entries and the same plan the engine
executes (declarative Calls, Field code from guiqula.core.fields), so it
cannot drift from what the GUI computes; the engine tests run exported
scripts and compare their arrays. Disabled and invalid entries are written
as comments, stochastic entries are preceded by their seeds, and the
Hilbert space the engine fixed is passed to get_hamiltonian explicitly.
"""
import guiqula
from guiqula.core import fields
from guiqula.core import regions as region_tools
from guiqula.registry import pipeline
from guiqula.registry.base import G, H
from guiqula.registry.params import ConditionParam, FieldParam, VectorFieldParam


class ScriptContext:
    def __init__(self, spec, params, region=None, regions=None):
        self.spec = spec
        self.params = params
        self.weight = region_tools.code_indicator(region) if region else None
        self.regions = regions or {}

    def value(self, name):
        return self.params[name]

    def code(self, name):
        param = self.spec.param_map[name]
        value = self.params[name]
        weight = self.weight if getattr(param, "native", False) else None
        if isinstance(param, VectorFieldParam):
            return fields.code_vector(value, weight, self.regions)
        if isinstance(param, FieldParam):
            return fields.code_scalar(value, weight, self.regions)
        if isinstance(param, ConditionParam):
            return param.code(value)
        return repr(value)


def call_code(spec, ctx):
    call = spec.call

    def arg(a):
        if a is H:
            return "h"
        if a is G:
            return "g"
        return ctx.code(a)
    args = [arg(a) for a in call.args] + [f"{k}={arg(v)}" for k, v in call.kwargs.items()]
    target = call.target if call.module is None else call.module.split(".")[-1] + "." + \
        call.target.rsplit(".", 1)[1]
    return f"{target}({', '.join(args)})"


def _imports(stages, calc_spec):
    modules = {"geometry"}
    for stage in stages:
        if stage.spec is not None and stage.spec.call is not None and stage.spec.call.module:
            modules.add(stage.spec.call.module)
        if stage.spec is not None and stage.applied:
            modules.update(stage.spec.modules)
    if calc_spec is not None:
        modules.update(calc_spec.modules)
    lines = []
    if any(stage.applied and stage.spec is not None and stage.spec.runs_code
           for stage in stages) or (calc_spec is not None and calc_spec.runs_code):
        lines.append("import pyqula                      # the Python nodes may use it")
    plain = sorted(m for m in modules if "." not in m)
    if plain:
        lines.append(f"from pyqula import {', '.join(plain)}")
    for m in sorted(m for m in modules if "." in m):
        package, _, name = m.rpartition(".")
        lines.append(f"from pyqula.{package} import {name}")
    return lines


def _comment(stage, why):
    return [f"# {stage.id} {stage.kind}: {why}"]


def export_script(document, calc_id, skipped=None, trusted=True):
    """Source of a script that rebuilds the system of calculation calc_id,
    runs it and saves the arrays to result.npz. skipped: {entry id:
    message} of entries pyqula rejected at build time (from a Result's
    reports), written as comments like the ones the planner rejects.
    trusted: whether the Python nodes are written (else they are skipped,
    as the engine skips them)."""
    skipped = dict(skipped or {})
    plan = pipeline.plan_calculation(document, calc_id, trusted)
    if plan.problem:
        raise ValueError(f"{calc_id}: {plan.problem}")
    system = plan.system
    lines = [f'"""pyqula script exported by guiqula {guiqula.__version__}.',
             "",
             f"Calculation {calc_id} ({plan.kind}) on system {system.system_id}.",
             "Run it with pyqula importable; it writes result.npz in the current directory.",
             '"""',
             *(["import random", ""] if plan.spec.seed_param is not None or any(
                 st.applied and st.spec is not None and st.spec.seed_param is not None
                 for st in system.stages) else []),
             "import numpy as np",
             *_imports(system.stages, plan.spec),
             ""]
    for stage in system.stages:
        if stage.stage == "base":
            lines.append(f"g = {call_code(stage.spec, ScriptContext(stage.spec, stage.params))}")
            continue
        if stage.stage == "construction":
            c = stage.params
            args = [f"has_spin={c['has_spin']}"]
            if list(c["tij"]) != [1.0]:
                args.append(f"tij={list(c['tij'])!r}")
            if c["is_sparse"]:
                args.append("is_sparse=True")
            if system.upgraded_by:
                lines.append(f"# the Hilbert space is {system.mode} because of "
                             f"{', '.join(system.upgraded_by)}")
            lines.append(f"h = g.get_hamiltonian({', '.join(args)})")
            if c["nambu"]:
                lines.append("h.turn_nambu()")
            continue
        if not stage.enabled:
            if stage.stage != "meanfield":     # every system has one, disabled by default
                lines += _comment(stage, "disabled")
            continue
        if stage.problem or stage.id in skipped:
            lines += _comment(stage, f"skipped, {stage.problem or skipped[stage.id]}")
            continue
        ctx = ScriptContext(stage.spec, stage.params, stage.region, stage.regions)
        seed = stage.spec.seed_param
        if seed is not None:
            s = stage.params[seed.name]
            lines.append(f"np.random.seed({s}); random.seed({s})")
        if stage.spec.call is None:
            lines += stage.spec.script(ctx)
        elif stage.stage == "op":
            lines.append(f"g = {call_code(stage.spec, ctx)}")
        else:
            lines.append(call_code(stage.spec, ctx))
    lines.append("")
    if plan.spec.seed_param is not None:
        s = plan.params[plan.spec.seed_param.name]
        lines.append(f"np.random.seed({s}); random.seed({s})")
    lines += plan.spec.script(ScriptContext(plan.spec, plan.params))
    lines += ['np.savez("result.npz", **arrays)',
              'print({k: np.shape(v) for k, v in arrays.items()})', ""]
    return "\n".join(lines)
