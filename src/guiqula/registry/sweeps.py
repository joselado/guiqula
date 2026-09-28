"""Sweeps (decision 13.10): a calculation that runs another calculation of
the same system at every value of one parameter, or on a grid of two, and
collects the numbers its results give (a gap, a Chern number, a total
energy, what a Python calculation sets): a curve, or a phase diagram as a
map. Section 11 left open whether sweeps are a calculation or a "study"
of their own; they are a calculation here, so they are planned, keyed,
run, stored, exported and drawn like any other.

The parameter is named by the entry that holds it (a term, an op or a
calculation id; <system>/meanfield, <system>/model; the system itself for
its lattice), its name and, for a vector, the component. It must hold a
number (a Field, or a plain number of a calculation or a lattice). Every
value runs on a copy of the Document with that parameter set, through the
same build cache, so only the stages after the swept one are built again.
The key of a sweep hashes its parameters and the key of the calculation it
runs, so any change to that system makes it stale.

pyqula-free: the planner checks the target here, the engine runs it
(document-level adapter), the exporter writes a loop over a function of
the value.
"""
from guiqula.core.document import DocumentError
from guiqula.registry import base as registry
from guiqula.registry.base import ALL_SYSTEMS, entry
from guiqula.registry.params import (FieldParam, FloatParam, IntParam, ParamError, TextParam,
                                     VectorFieldParam)


class SweepError(ValueError):
    pass


def locate(document, target):
    """(registry spec, params dict) of what holds a swept parameter."""
    if target.endswith("/meanfield") or target.endswith("/model"):
        system_id, what = target.split("/", 1)
        system = document.system(system_id)
        block = system.hamiltonian.meanfield if what == "meanfield" and system.hamiltonian \
            else system.model if what == "model" else None
        if block is None:
            raise SweepError(f"{system_id} has no {what}")
        return registry.get("meanfield" if what == "meanfield" else "model", block.kind), \
            block.params
    family, _, _, _, obj = document.find(target)
    if family == "system":
        return registry.get("lattice", obj.geometry.base.kind), obj.geometry.base.params
    families = {"op": "geometry_op", "term": "term", "calculation": "calculation"}
    if family not in families:
        raise SweepError(f"{target} is a {family}, which has no parameters to sweep")
    return registry.get(families[family], obj.kind), obj.params


def check_target(document, target, param, component):
    """None if the parameter can be swept, else why not."""
    try:
        spec, params = locate(document, target)
    except (DocumentError, SweepError, registry.RegistryError) as error:
        return str(error).strip("\"'")
    declared = spec.param_map.get(param)
    if declared is None:
        return f"{target} has no parameter {param!r}; it has {list(spec.param_map)}"
    if isinstance(declared, VectorFieldParam):
        if component is None or not 0 <= component < declared.length:
            return f"{param} is a vector: give the component (0 to {declared.length - 1})"
    elif component is not None:
        return f"{param} is not a vector: leave the component empty"
    elif not isinstance(declared, (FieldParam, FloatParam)):
        return f"{param} does not hold a number that can be swept"
    return None


def _set(params, param, component, value):
    if component is None:
        params[param] = value
    else:
        current = list(params.get(param) or [0.0, 0.0, 0.0])
        current[component] = value
        params[param] = current


def command(document, target, param, component, value):
    """(mutation, arguments) that set one parameter of the Document to a
    number, as a slider or a pick on a sweep does: set_param on an entry
    (or on a system, its lattice), set_meanfield or set_model on
    <system>/meanfield and <system>/model; a component of a vector is set
    in the vector the entry holds."""
    value = float(value)
    if component is not None:
        current = list(locate(document, target)[1].get(param) or [0.0, 0.0, 0.0])
        current[component] = value
        value = current
    if target.endswith("/meanfield"):
        return "set_meanfield", {"system": target.split("/")[0], "params": {param: value}}
    if target.endswith("/model"):
        return "set_model", {"system": target.split("/")[0], "params": {param: value}}
    return "set_param", {"entry": target, "name": param, "value": value}


def with_value(document, target, param, component, value):
    """A copy of the Document with one parameter set to value."""
    document = document.copy_deep()
    _, params = locate(document, target)
    _set(params, param, component, value)
    return document


def check_values(document, target, param, component, values):
    """None if the entry takes every value, else why not: a value outside
    the parameter's bounds (a filling above 1) would make the entry
    invalid at that point, and the point would be computed without it."""
    spec, params = locate(document, target)
    declared = spec.param_map[param]
    for value in values:
        changed = dict(params)
        _set(changed, param, component, float(value))
        try:
            declared.normalize(changed[param])
        except ParamError as error:
            return f"{target} cannot take every value of the sweep: {error}"
    return None


def axes(params):
    """[(target, param, component, values)] of a sweep: one or two axes."""
    import numpy as np
    out = [(params["entry"], params["param"], params["component"],
            np.linspace(params["start"], params["stop"], params["steps"]))]
    if params["entry2"]:
        out.append((params["entry2"], params["param2"], params["component2"],
                    np.linspace(params["start2"], params["stop2"], params["steps2"])))
    return out


def _numbers(result):
    import numpy as np
    return {name: float(np.real(value)) for name, value in result.arrays.items()
            if np.ndim(value) == 0}


def _sweep(document, ctx, run):
    """Run the inner calculation at every value; the arrays are the values
    ("value", "value2") and one array per number of its result. A point at
    which a swept entry is skipped (pyqula rejects the value) fails the
    sweep: it would be computed without it. The other entries skipped at
    some point are the sweep's reports (ctx.note "reports"), as those of a
    calculation are."""
    import numpy as np
    grid = axes(ctx.params)
    shape = tuple(len(axis[3]) for axis in grid)
    total, collected, done, skipped = int(np.prod(shape)), {}, 0, {}
    swept_ids = {target for target, _, _, _ in grid}
    for index in np.ndindex(*shape):
        swept = document
        for (target, param, component, values), i in zip(grid, index):
            swept = with_value(swept, target, param, component, float(values[i]))
        point = ", ".join(f"{label(t, p, c)} = {float(values[i]):g}"
                          for (t, p, c, values), i in zip(grid, index))
        result = run(swept)
        for report in result.skipped:
            if report["id"] in swept_ids:
                raise SweepError(f"{report['id']} is skipped at {point} ({report['message']}), "
                                 f"so that point would be computed without it")
            skipped.setdefault(report["id"], dict(report, message=f"at {point}: "
                                                                   f"{report['message']}"))
        numbers = _numbers(result)
        if not numbers:
            raise SweepError(f"{ctx.params['calculation']} gives no number to collect (its "
                             f"arrays are not scalars); sweep a gap, a Chern number, an energy, "
                             f"or a Python calculation that sets numbers")
        for name, value in numbers.items():
            collected.setdefault(name, np.full(shape, np.nan))[index] = value
        done += 1
        ctx.progress(done / total)
    ctx.note("reports", list(skipped.values()))
    arrays = {"value": grid[0][3]}
    if len(grid) == 2:
        arrays["value2"] = grid[1][3]
    arrays.update(collected)
    return arrays


def label(target, param, component):
    return f"{target} {param}" + ("" if component is None else f"[{'xyz'[component]}]")


def _plot(params, arrays):
    """A curve, or a map of two parameters; its axes yield the swept
    parameters' values to a pick ("parameters": what each axis sets)."""
    names = [n for n in arrays if n not in ("value", "value2")]
    output = params["output"] if params["output"] in names else names[0]
    first = [params["entry"], params["param"], params["component"]]
    x = label(*first)
    if "value2" in arrays:
        second = [params["entry2"], params["param2"], params["component2"]]
        return {"kind": "heatmap", "x": "value", "y": "value2", "c": output, "xlabel": x,
                "ylabel": label(*second), "clabel": output,
                "picks": {"x": "parameter", "y": "parameter"},
                "parameters": {"x": first, "y": second}}
    return {"kind": "lines", "x": "value", "y": output, "xlabel": x, "ylabel": output,
            "picks": {"x": "parameter"}, "parameters": {"x": first}}


entry("calculation", "sweep", "Sweep",
      TextParam("calculation", "", "calculation", "the calculation run at every value; its "
                                                  "numbers are collected"),
      TextParam("entry", "", "entry", "what holds the parameter: a term, op or calculation id, "
                                      "<system>/meanfield, <system>/model, or the system (its "
                                      "lattice)"),
      TextParam("param", "", "parameter", "its name"),
      IntParam("component", None, "component", "0, 1, 2 for a vector (x, y, z)", minimum=0,
               maximum=2, optional=True),
      FloatParam("start", 0.0, "from"),
      FloatParam("stop", 1.0, "to"),
      IntParam("steps", 11, "values", minimum=2),
      TextParam("entry2", "", "second entry", "a second parameter makes a map (optional)"),
      TextParam("param2", "", "second parameter"),
      IntParam("component2", None, "second component", minimum=0, maximum=2, optional=True),
      FloatParam("start2", 0.0, "second from"),
      FloatParam("stop2", 1.0, "second to"),
      IntParam("steps2", 11, "second values", minimum=2),
      TextParam("output", "", "draw", "the number drawn (empty: the first one); all are kept"),
      group="Sweeps", systems=ALL_SYSTEMS, document_level=True,
      doc="Run a calculation at every value of a parameter (or on a grid of two) and draw the "
          "numbers it gives: the gap against a field, the Chern number against two couplings.",
      apply=_sweep, script=lambda ctx: [], plot=_plot,
      guide=("guiqula: Sweeps and sliders",))
