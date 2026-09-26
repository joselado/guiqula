"""Calculations. Each adapter returns plain arrays (never figures, PLAN.md
3.3) and names the plot kind that draws them (PLAN.md 3.4)."""
from guiqula.registry.base import entry
from guiqula.registry.params import ChoiceParam, FloatParam, IntParam


def _bands(h, ctx):
    import numpy as np
    nk, operator = ctx.value("nk"), ctx.value("operator")
    kwargs = {"nk": nk, "write": False, "callback": ctx.progress_callback(nk)}
    if operator is not None:
        kwargs["operator"] = operator
    out = h.get_bands(**kwargs)
    k_index = np.unique(out[0])
    arrays = {"k": k_index, "energies": out[1].reshape(len(k_index), -1)}
    if operator is not None:
        arrays["weights"] = out[2].reshape(len(k_index), -1)
    return arrays


def _bands_script(ctx):
    operator = ctx.value("operator")
    op = "" if operator is None else f", operator={operator!r}"
    lines = [f"out = h.get_bands(nk={ctx.code('nk')}{op}, write=False)",
             "k = np.unique(out[0])",
             "energies = out[1].reshape(len(k), -1)"]
    if operator is None:
        lines.append("arrays = dict(k=k, energies=energies)")
    else:
        lines += ["weights = out[2].reshape(len(k), -1)",
                  "arrays = dict(k=k, energies=energies, weights=weights)"]
    return lines


def _bands_plot(params):
    plot = {"x": "k", "y": "energies", "xlabel": "k-path point", "ylabel": "energy"}
    if params.get("operator") is None:
        return dict(plot, kind="lines")
    return dict(plot, kind="colored_scatter", c="weights", clabel=params["operator"])


entry("calculation", "bands", "Band structure",
      IntParam("nk", 200, "k-points", "points along the k-path", minimum=2),
      ChoiceParam("operator", None, source="operators", optional=True, label="operator",
                  doc="colour the bands by this operator's expectation value"),
      group="Spectral", doc="Bands along the default high-symmetry path of the geometry.",
      apply=_bands, script=_bands_script, plot=_bands_plot)


def _dos(h, ctx):
    import numpy as np
    energies = np.linspace(ctx.value("emin"), ctx.value("emax"), ctx.value("ne"))
    kwargs = dict(energies=energies, delta=ctx.value("delta"), nk=ctx.value("nk"),
                  mode=ctx.value("mode"), write=False)
    if ctx.value("operator") is not None:
        kwargs["operator"] = ctx.value("operator")
    es, ds = h.get_dos(**kwargs)
    return {"energies": np.asarray(es, dtype=float), "dos": np.asarray(ds, dtype=float)}


def _dos_script(ctx):
    operator = ctx.value("operator")
    op = "" if operator is None else f", operator={operator!r}"
    return [f"es, ds = h.get_dos(energies=np.linspace({ctx.code('emin')}, {ctx.code('emax')}, "
            f"{ctx.code('ne')}), delta={ctx.code('delta')}, nk={ctx.code('nk')}, "
            f"mode={ctx.code('mode')}{op}, write=False)",
            "arrays = dict(energies=np.asarray(es, dtype=float), dos=np.asarray(ds, dtype=float))"]


entry("calculation", "dos", "Density of states",
      FloatParam("emin", -4.0, "lowest energy"),
      FloatParam("emax", 4.0, "highest energy"),
      IntParam("ne", 400, "energies", "number of energies", minimum=2),
      FloatParam("delta", 0.05, "broadening", "Lorentzian width", minimum=1e-9),
      IntParam("nk", 20, "k-points", "k-points per direction of the mesh", minimum=1),
      ChoiceParam("mode", "ED", choices=("ED", "Green"), label="method",
                  doc="ED: diagonalize on a k-mesh; Green: Green's function per energy"),
      ChoiceParam("operator", None, source="operators", optional=True, label="projection",
                  doc="project the DOS on this operator"),
      group="Spectral", doc="Density of states on an energy window.",
      apply=_dos, script=_dos_script,
      plot=lambda params: {"kind": "lines", "x": "energies", "y": "dos",
                           "xlabel": "energy", "ylabel": "DOS"})
