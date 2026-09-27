"""Python nodes (PLAN.md 3.1, 13.7): a geometry op, a term or a calculation
given as Python source, the escape hatch to everything pyqula does that
has no registry entry yet. The code runs in the worker process, with
``np`` (numpy) and ``pyqula`` in scope (pyqula/__init__ exports nothing:
write ``from pyqula import geometry``), and only in a trusted document
(``runs_code``: the planner skips it otherwise). An error in the code
flags the node, with its line, and the stack carries on without it
(decision 14.3). What it prints is kept with the stage's report.

- op: ``g`` is the geometry so far (the node's own copy); change it in
  place or assign another geometry to ``g``;
- term: ``h`` is the Hamiltonian so far (``g`` its geometry); change it in
  place or assign another Hamiltonian to ``h``. ``needs`` declares the
  Hilbert space the code needs, so that the engine fixes it before the
  first term (pyqula would otherwise upgrade it in the middle, PLAN.md
  3.1);
- calculation: ``h`` is the system's Hamiltonian; the code sets
  ``arrays`` (a dict of numbers and arrays of numbers: what a project file
  keeps) and may set ``plot`` (a plot spec, PLAN.md 3.4, checked against
  the shapes its kind draws); without one, numbers only are shown as a
  table and otherwise the second array is drawn against the first 1-D one.

exit() in the code flags the node like any error: it does not end the
worker.

In a classical system (decision 13.5) the term and the calculation see
the classical model as ``model`` instead of ``h`` (a SpinModel,
LatticeGas or LatticeIsing), and ``needs`` does not matter.

The exported script holds the code as it is: it runs on the script's own
``g`` and ``h``.
"""
from guiqula.core.results import PLOT_KINDS
from guiqula.registry.base import ALL_SYSTEMS, entry
from guiqula.registry.params import ChoiceParam, CodeParam


class NodeError(RuntimeError):
    """The code of a Python node failed; the message has its line."""


def run_code(code, namespace, name="python node"):
    """Execute a node's code in namespace (numpy and pyqula added); an
    error comes back as NodeError naming the line of the node's code."""
    import sys
    import traceback

    import numpy as np
    import pyqula
    namespace.setdefault("np", np)
    namespace.setdefault("pyqula", pyqula)
    filename = f"<{name}>"
    try:
        exec(compile(code, filename, "exec"), namespace)
    except (Exception, SystemExit) as error:
        line = None
        for frame, number in traceback.walk_tb(sys.exc_info()[2]):
            if frame.f_code.co_filename == filename:
                line = number
        where = f" (line {line} of the code)" if line is not None else ""
        if isinstance(error, SystemExit):
            raise NodeError(f"the code called exit(){where}; a node cannot end the "
                            f"worker") from None
        raise NodeError(f"{type(error).__name__}: {error}{where}") from None
    return namespace


def _code_lines(ctx):
    return ctx.value("code").rstrip("\n").split("\n")


OP_CODE = """\
# g: the geometry built so far; change it in place or assign a new one, e.g.
# from pyqula import sculpt
# g = sculpt.intersec(g, lambda r: r[0]**2 + r[1]**2 < 9)
"""


def _op(g, ctx):
    namespace = run_code(ctx.value("code"), {"g": g}, "python op")
    return namespace["g"]


entry("geometry_op", "python", "Python op",
      CodeParam("code", OP_CODE, "code", "Python with g (the geometry), np and pyqula"),
      group="Python", doc="Python code that changes the geometry: anything pyqula can do "
                          "that has no op of its own. It runs only in a trusted document.",
      runs_code=True, apply=_op, script=_code_lines,
      guide=("guiqula: Python nodes, trust and the console",))

TERM_CODE = """\
# h: the Hamiltonian built so far (g its geometry); change it in place or
# assign a new one, e.g.
# h.add_kane_mele(0.05)
"""
NEEDS = {"nothing": (), "spin": ("spin",), "nambu": ("nambu",)}


def _names(obj):
    """What a node sees: h of a quantum system, model of a classical one."""
    name = "h" if hasattr(obj, "intra") else "model"
    return name, {name: obj, "g": obj.geometry}


def _term(obj, ctx):
    name, namespace = _names(obj)
    return run_code(ctx.value("code"), namespace, "python term")[name]


entry("term", "python", "Python term",
      CodeParam("code", TERM_CODE, "code", "Python with h (the Hamiltonian), g, np and pyqula"),
      ChoiceParam("needs", "nothing", choices=tuple(NEEDS), label="needs",
                  doc="the Hilbert space the code needs (spin for an exchange or spin-orbit "
                      "term, nambu for pairing); the Hamiltonian is built in it from the "
                      "start"),
      group="Python", doc="Python code that changes the Hamiltonian: any pyqula term that "
                          "has no entry of its own. It runs only in a trusted document.",
      requires=lambda params: NEEDS[params["needs"]], runs_code=True, apply=_term,
      script=_code_lines, systems=ALL_SYSTEMS,
      guide=("guiqula: Python nodes, trust and the console",))

CALCULATION_CODE = """\
# h: the Hamiltonian of the system; set arrays (a dict of numbers and arrays)
# and, if you like, plot (e.g. {"kind": "lines", "x": "k", "y": "energies"})
k, e = h.get_bands(nk=100, write=False)     # one entry per band at each k
k = np.unique(k)
arrays = {"k": k, "energies": e.reshape(len(k), -1)}     # a row of bands per k
"""

# the names each plot kind needs (ui/plots.py draws them)
PLOT_NEEDS = {"lines": ("y",), "colored_scatter": ("x", "y", "c"), "heatmap": ("x", "y", "c"),
              "structure_scalar": ("values",), "structure_vector": ("vectors",),
              "scalar": ("rows",)}


def default_plot(arrays):
    """The plot of a Python calculation that set none: a table of the
    numbers, or the first array that is not the x axis against the first
    1-D one (the numbers are left out of the plot)."""
    import numpy as np
    names = list(arrays)
    lists = [n for n in names if np.ndim(arrays[n]) > 0]
    if not lists:
        return {"kind": "scalar", "rows": [[n, n] for n in names]}
    x = next((n for n in lists if np.ndim(arrays[n]) == 1 and np.size(arrays[n])), None)
    others = [n for n in lists if n != x]
    if x is not None and others and np.size(arrays[others[0]]) % np.size(arrays[x]) == 0:
        return {"kind": "lines", "x": x, "y": others[0], "xlabel": x, "ylabel": others[0]}
    return {"kind": "lines", "y": lists[0], "xlabel": "index", "ylabel": lists[0]}


def check_plot(plot, arrays, sites=None):
    """Refuse a plot spec the result cannot be drawn with: the arrays it
    names must exist, with the shapes its kind draws (sites: the number of
    sites a plot on the atoms needs a value for)."""
    import numpy as np
    if not isinstance(plot, dict) or plot.get("kind") not in PLOT_KINDS:
        raise NodeError(f"plot must be a dict whose kind is one of {list(PLOT_KINDS)}")
    kind = plot["kind"]
    lacking = [k for k in PLOT_NEEDS[kind] if k not in plot]
    if lacking:
        raise NodeError(f"a {kind} plot names {' and '.join(lacking)}")
    rows = plot.get("rows", [])
    if not isinstance(rows, (list, tuple)) or \
            not all(isinstance(r, (list, tuple)) and len(r) == 2 for r in rows):
        raise NodeError("the rows of a scalar plot are [array, label] pairs")
    named = [plot[k] for k in ("x", "y", "c", "values", "vectors") if k in plot]
    named += [row[0] for row in rows]
    missing = [n for n in named if n not in arrays]
    if missing:
        raise NodeError(f"plot names {missing}, which arrays does not have")
    a = {n: np.asarray(arrays[n]) for n in named}

    def refuse(why):
        raise NodeError(f"a {kind} plot cannot draw these arrays: {why}")

    if kind in ("lines", "colored_scatter"):
        y = a[plot["y"]]
        if plot.get("x"):
            x = a[plot["x"]]
            if x.ndim != 1 or not x.size:
                refuse(f"x ({plot['x']}) must be a list of numbers, not of shape {x.shape}")
        elif y.ndim == 0:
            refuse(f"{plot['y']} is a single number")
        n = len(x) if plot.get("x") else len(y)
        if not y.size or y.size % n:
            refuse(f"{plot['y']} has {y.size} values: not a row of values for each of {n} x")
        if kind == "colored_scatter" and a[plot["c"]].size != y.size:
            refuse(f"{plot['c']} needs a value for each of the {y.size} values of {plot['y']}")
    elif kind == "heatmap":
        x, y, c = (a[plot[k]] for k in ("x", "y", "c"))
        if x.ndim != 1 or y.ndim != 1 or not c.size or not (
                (c.ndim == 1 and len(c) == len(x) == len(y)) or c.shape == (len(x), len(y))):
            refuse(f"c ({plot['c']}) needs a value for each point (x, y), or a (len(x), "
                   f"len(y)) grid")
    elif kind == "structure_scalar" and sites is not None and a[plot["values"]].size != sites:
        refuse(f"{plot['values']} needs one value for each of the {sites} sites")
    elif kind == "structure_vector" and sites is not None and \
            a[plot["vectors"]].size != 3 * sites:
        refuse(f"{plot['vectors']} needs one vector for each of the {sites} sites")
    elif kind == "scalar" and any(not a[name].size for name, _ in rows):
        refuse("an array of the table is empty")
    return plot


def _calculation(obj, ctx):
    import numpy as np
    namespace = run_code(ctx.value("code"), _names(obj)[1], "python calculation")
    arrays = namespace.get("arrays")
    if not isinstance(arrays, dict) or not arrays:
        raise NodeError("the code must set arrays, a dict of numbers and arrays of numbers")
    out = {}
    for key, value in arrays.items():
        try:
            array = np.asarray(value)
        except ValueError as error:          # a ragged list
            raise NodeError(f"arrays[{key!r}]: {error}") from None
        if array.dtype.kind not in "biufc":  # a project file keeps numbers only
            raise NodeError(f"arrays[{key!r}] is {type(value).__name__}, not a number or an "
                            f"array of numbers (a label goes into plot)")
        out[str(key)] = array
    plot = namespace.get("plot")
    plot = default_plot(out) if plot is None else dict(plot)
    ctx.note("plot", check_plot(plot, out, len(obj.geometry.r)))
    return out


entry("calculation", "python", "Python calculation",
      CodeParam("code", CALCULATION_CODE, "code", "Python with h, g, np and pyqula that sets "
                                                   "arrays"),
      group="Python", doc="Python code that computes anything pyqula can from the system's "
                          "Hamiltonian; the arrays it sets are the result. It runs only in a "
                          "trusted document.",
      runs_code=True, apply=_calculation, script=_code_lines, systems=ALL_SYSTEMS,
      plot=lambda params: {"kind": "lines", "x": "x", "y": "y"},
      guide=("guiqula: Python nodes, trust and the console",))
