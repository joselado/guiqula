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
  ``arrays`` (a dict of arrays or numbers) and may set ``plot`` (a plot
  spec, PLAN.md 3.4); without one, numbers only are shown as a table and
  otherwise the second array is drawn against the first.

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
    except Exception as error:
        line = None
        for frame, number in traceback.walk_tb(sys.exc_info()[2]):
            if frame.f_code.co_filename == filename:
                line = number
        where = f" (line {line} of the code)" if line is not None else ""
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
# h: the Hamiltonian of the system; set arrays (a dict of arrays or numbers)
# and, if you like, plot (e.g. {"kind": "lines", "x": "k", "y": "energies"})
k, energies = h.get_bands(nk=100, write=False)
arrays = {"k": k, "energies": energies}
"""


def default_plot(arrays):
    """The plot of a Python calculation that set none."""
    import numpy as np
    names = list(arrays)
    if all(np.ndim(arrays[n]) == 0 for n in names):
        return {"kind": "scalar", "rows": [[n, n] for n in names]}
    if len(names) >= 2:
        return {"kind": "lines", "x": names[0], "y": names[1], "xlabel": names[0],
                "ylabel": names[1]}
    return {"kind": "lines", "y": names[0], "xlabel": "index", "ylabel": names[0]}


def check_plot(plot, arrays):
    """Refuse a plot spec the result cannot be drawn with."""
    if not isinstance(plot, dict) or plot.get("kind") not in PLOT_KINDS:
        raise NodeError(f"plot must be a dict whose kind is one of {list(PLOT_KINDS)}")
    named = [plot[k] for k in ("x", "y", "c", "values", "vectors") if k in plot]
    named += [row[0] for row in plot.get("rows", [])]
    missing = [n for n in named if n not in arrays]
    if missing:
        raise NodeError(f"plot names {missing}, which arrays does not have")
    return plot


def _calculation(obj, ctx):
    import numpy as np
    namespace = run_code(ctx.value("code"), _names(obj)[1], "python calculation")
    arrays = namespace.get("arrays")
    if not isinstance(arrays, dict) or not arrays:
        raise NodeError("the code must set arrays, a dict of arrays or numbers")
    arrays = {str(k): np.asarray(v) for k, v in arrays.items()}
    plot = namespace.get("plot")
    plot = default_plot(arrays) if plot is None else dict(plot)
    ctx.note("plot", check_plot(plot, arrays))
    return arrays


entry("calculation", "python", "Python calculation",
      CodeParam("code", CALCULATION_CODE, "code", "Python with h, g, np and pyqula that sets "
                                                   "arrays"),
      group="Python", doc="Python code that computes anything pyqula can from the system's "
                          "Hamiltonian; the arrays it sets are the result. It runs only in a "
                          "trusted document.",
      runs_code=True, apply=_calculation, script=_code_lines, systems=ALL_SYSTEMS,
      plot=lambda params: {"kind": "lines", "x": "x", "y": "y"},
      guide=("guiqula: Python nodes, trust and the console",))
