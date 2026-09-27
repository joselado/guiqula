"""Script export: a runnable pyqula script reproducing a calculation
(PLAN.md 3.5), the successor of quantum-lattice's "pyqula code" tab.

It is generated from the same registry entries and the same plan the engine
executes (declarative Calls, Field code from guiqula.core.fields), so it
cannot drift from what the GUI computes; the engine tests run exported
scripts and compare their arrays. Disabled and invalid entries are written
as comments, stochastic entries are preceded by their seeds, and the
Hilbert space the engine fixed is passed to get_hamiltonian explicitly.
A classical system's model is the variable ``model``.
"""
import inspect

import guiqula
from guiqula.core import fields
from guiqula.core import regions as region_tools
from guiqula.registry import pipeline
from guiqula.registry.base import G, H
from guiqula.registry.params import ConditionParam, FieldParam, VectorFieldParam


class ScriptContext:
    def __init__(self, spec, params, region=None, regions=None, results=None):
        self.spec = spec
        self.params = params
        self.weight = region_tools.code_indicator(region) if region else None
        self.regions = regions or {}
        self.results = results or {}

    def value(self, name):
        return self.params[name]

    def code(self, name):
        param = self.spec.param_map[name]
        value = self.params[name]
        weight = self.weight if getattr(param, "native", False) else None
        if isinstance(param, VectorFieldParam):
            return fields.code_vector(value, weight, self.regions, self.results)
        if isinstance(param, FieldParam):
            return fields.code_scalar(value, weight, self.regions, self.results)
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


def export_script(document, calc_id, skipped=None, trusted=True, results=None):
    """Source of a script that rebuilds the system of calculation calc_id,
    runs it and saves the arrays to result.npz. skipped: {entry id:
    message} of entries pyqula rejected at build time (from a Result's
    reports), written as comments like the ones the planner rejects.
    trusted: whether the Python nodes are written (else they are skipped,
    as the engine skips them); results: {calculation id: ResultRef} the
    from_result Fields read, whose values the script holds. A sweep
    writes a loop over a function of the swept value."""
    plan = pipeline.plan_calculation(document, calc_id, trusted, results)
    if plan.problem:
        raise ValueError(f"{calc_id}: {plan.problem}")
    if plan.spec.document_level:
        return _export_sweep(document, plan, skipped, trusted, results)
    head, body = _parts(plan, skipped)
    return "\n".join(_docstring(plan) + head + body + _footer())


def _docstring(plan, what=None):
    return [f'"""pyqula script exported by guiqula {guiqula.__version__}.',
            "",
            what or f"Calculation {plan.calc_id} ({plan.kind}) on system {plan.system_id}.",
            "Run it with pyqula importable; it writes result.npz in the current directory.",
            '"""']


def _footer():
    return ['np.savez("result.npz", **arrays)',
            'print({k: np.shape(v) for k, v in arrays.items()})', ""]


def _parts(plan, skipped=None):
    """(the imports and definitions, the lines that build the system and set
    arrays) of the script of a calculation plan."""
    skipped = dict(skipped or {})
    system = plan.system
    head = [*(["import random", ""] if plan.spec.seed_param is not None or any(
                st.applied and st.spec is not None and st.spec.seed_param is not None
                for st in system.stages) else []),
            "import numpy as np",
            *_imports(system.stages, plan.spec),
            ""]
    preamble = []
    for stage in system.stages:
        if stage.applied and stage.spec is not None:
            preamble += [line for line in stage.spec.preamble if line not in preamble]
    if preamble:
        head += preamble + [""]
    helpers = set()
    for stage in system.stages:
        if stage.applied and stage.params is not None:
            helpers |= fields.helpers_of(stage.params)
    for helper in sorted(helpers, key=lambda f: f.__name__):   # site_field, painted_field...
        head += ["", inspect.getsource(helper).rstrip(), "", ""]
    lines = []
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
        if stage.stage == "model":
            seed = stage.spec.seed_param
            if seed is not None:
                s = stage.params[seed.name]
                lines.append(f"np.random.seed({s}); random.seed({s})   # the initial "
                             f"configuration is random")
            lines.append(f"model = {call_code(stage.spec, ScriptContext(stage.spec, stage.params))}")
            continue
        if not stage.enabled:
            if stage.stage != "meanfield":     # every system has one, disabled by default
                lines += _comment(stage, "disabled")
            continue
        if stage.turn_nambu:                   # the first entry that needs it (the engine's)
            lines.append("h.turn_nambu()")
        if stage.problem or stage.id in skipped:
            lines += _comment(stage, f"skipped, {stage.problem or skipped[stage.id]}")
            continue
        ctx = ScriptContext(stage.spec, stage.params, stage.region, stage.regions, stage.results)
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
    return head, lines


# values the swept parameters take while their script is generated; they are
# then replaced by the loop variables
SENTINELS = (0.123456789012345, 0.234567890123456)


def _export_sweep(document, plan, skipped, trusted, results):
    """A function of the swept value(s) that builds and runs the inner
    calculation, called on every value; the arrays are those the engine
    gives (value, value2, one array per number)."""
    from guiqula.registry import sweeps
    grid = sweeps.axes(plan.params)
    swept = document
    for (target, param, component, _), sentinel in zip(grid, SENTINELS):
        swept = sweeps.with_value(swept, target, param, component, sentinel)
    inner = pipeline.plan_calculation(swept, plan.params["calculation"], trusted, results)
    if inner.problem:
        raise ValueError(f"{plan.calc_id}: {inner.problem}")
    head, body = _parts(inner, skipped)
    text = "\n".join(body)
    names = ["value", "value2"][:len(grid)]
    for sentinel, name in zip(SENTINELS, names):
        if repr(sentinel) not in text:
            raise ValueError(f"{plan.calc_id}: the swept parameter does not reach the script")
        text = text.replace(repr(sentinel), name)
    function = [f"def compute({', '.join(names)}):",
                *["    " + line if line else "" for line in text.split("\n")],
                "    return arrays", "", ""]
    axes = [f"values = np.linspace({grid[0][3][0]!r}, {grid[0][3][-1]!r}, {len(grid[0][3])})"]
    if len(grid) == 2:
        axes.append(f"values2 = np.linspace({grid[1][3][0]!r}, {grid[1][3][-1]!r}, "
                    f"{len(grid[1][3])})")
        loop = ["outs = [[compute(v, w) for w in values2] for v in values]",
                "first = outs[0][0]",
                "arrays = dict(value=values, value2=values2)",
                "for name in first:",
                "    if np.ndim(first[name]) == 0:",
                "        arrays[name] = np.array([[float(np.real(o[name])) for o in row] "
                "for row in outs])"]
    else:
        loop = ["outs = [compute(v) for v in values]",
                "arrays = dict(value=values)",
                "for name in outs[0]:",
                "    if np.ndim(outs[0][name]) == 0:",
                "        arrays[name] = np.array([float(np.real(o[name])) for o in outs])"]
    what = (f"Sweep {plan.calc_id}: {plan.params['calculation']} at every value of "
            + " and ".join(sweeps.label(t, p, c) for t, p, c, _ in grid) + ".")
    return "\n".join(_docstring(plan, what) + head + function + axes + loop + [""] + _footer())
