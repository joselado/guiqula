"""Calculations. Each adapter returns plain arrays (never figures, PLAN.md
3.3) and names the plot kind that draws them (PLAN.md 3.4)."""
from guiqula.registry import cost
from guiqula.registry.base import entry
from guiqula.registry.params import ChoiceParam, FloatParam, IntParam, SeedParam


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
      apply=_bands, script=_bands_script, plot=_bands_plot,
      cost=lambda p, size: p["nk"] * cost.diagonalization(size["dimension"])
      * (2 if p["operator"] else 1))


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


def _dos_cost(p, size):
    points = cost.kmesh(p["nk"], size["dimensionality"])
    if p["mode"] == "Green":                  # an inversion per energy and k-point
        return p["ne"] * points * cost.diagonalization(size["dimension"]) / 3
    if p["mode"] == "KPM":                    # matrix-vector products, one per polynomial
        return points * cost.kpm(size["dimension"], 10.0 / p["delta"])
    return points * cost.diagonalization(size["dimension"]) * (2 if p["operator"] else 1)


entry("calculation", "dos", "Density of states",
      FloatParam("emin", -4.0, "lowest energy"),
      FloatParam("emax", 4.0, "highest energy"),
      IntParam("ne", 400, "energies", "number of energies", minimum=2),
      FloatParam("delta", 0.05, "broadening", "Lorentzian width", minimum=1e-9),
      IntParam("nk", 20, "k-points", "k-points per direction of the mesh", minimum=1),
      ChoiceParam("mode", "ED", choices=("ED", "Green", "KPM"), label="method",
                  doc="ED: diagonalize on a k-mesh; Green: Green's function per energy; KPM: "
                      "Chebyshev expansion with random vectors and k-points, for large systems"),
      ChoiceParam("operator", None, source="operators", optional=True, label="projection",
                  doc="project the DOS on this operator (a projector, for KPM)"),
      SeedParam(doc="seed of the random vectors and k-points of the KPM method"),
      group="Spectral", doc="Density of states on an energy window.",
      apply=_dos, script=_dos_script, cost=_dos_cost,
      plot=lambda params: {"kind": "lines", "x": "energies", "y": "dos",
                           "xlabel": "energy", "ylabel": "DOS"})


# ---- helpers shared by the first-wave calculations (phase 4)
def _energies_params(emin=-3.0, emax=3.0, ne=100):
    return (FloatParam("emin", emin, "lowest energy"),
            FloatParam("emax", emax, "highest energy"),
            IntParam("ne", ne, "energies", "number of energies", minimum=2))


def _energies(ctx):
    import numpy as np
    return np.linspace(ctx.value("emin"), ctx.value("emax"), ctx.value("ne"))


def _energies_code(ctx):
    return f"np.linspace({ctx.code('emin')}, {ctx.code('emax')}, {ctx.code('ne')})"


def _operator_kwarg(ctx):
    operator = ctx.value("operator")
    return {} if operator is None else {"operator": operator}


def _operator_code(ctx):
    operator = ctx.value("operator")
    return "" if operator is None else f", operator={operator!r}"


def _operator(label="projection", doc="weight the result by this operator"):
    return ChoiceParam("operator", None, source="operators", optional=True, label=label,
                       doc=doc)


def _mesh_cost(factor=1.0):
    """Seconds of a calculation diagonalizing on an nk mesh."""
    return lambda p, size: factor * cost.kmesh(p["nk"], size["dimensionality"]) \
        * cost.diagonalization(size["dimension"])


def scalar(kind, label, value, code, rows, params=(), cost_=None, group="Topology", doc="",
           modules=()):
    """A calculation returning numbers: value(h, ctx) -> {name: number},
    code(ctx) -> the source of the same dict; rows: [[name, label]]."""
    entry("calculation", kind, label, *params, group=group, doc=doc, modules=modules,
          apply=lambda h, ctx: {k: float(v) for k, v in value(h, ctx).items()},
          script=lambda ctx: [f"arrays = {{k: float(v) for k, v in ({code(ctx)}).items()}}"],
          plot={"kind": "scalar", "rows": [list(r) for r in rows]}, cost=cost_)


# ---- real space
def _ldos(h, ctx):
    _, d = h.get_ldos(e=ctx.value("energy"), delta=ctx.value("delta"), nk=ctx.value("nk"),
                      nrep=1, write=False, return_rd=True, **_operator_kwarg(ctx))
    return {"ldos": d}


entry("calculation", "ldos", "Local density of states",
      FloatParam("energy", 0.0, "energy"),
      FloatParam("delta", 0.05, "broadening", "Lorentzian width", minimum=1e-9),
      IntParam("nk", 10, "k-points", "k-points per direction of the mesh (periodic systems)",
               minimum=1),
      _operator(),
      group="Real space", doc="Density of states at one energy on every site (pyqula's "
                             "get_ldos), drawn on the structure.",
      apply=_ldos, script=lambda ctx: [
          f"_, ldos = h.get_ldos(e={ctx.code('energy')}, delta={ctx.code('delta')}, "
          f"nk={ctx.code('nk')}, nrep=1, write=False, return_rd=True{_operator_code(ctx)})",
          "arrays = dict(ldos=ldos)"],
      plot={"kind": "structure_scalar", "values": "ldos", "clabel": "LDOS"},
      cost=_mesh_cost())

entry("calculation", "density", "Electron density",
      IntParam("nk", 10, "k-points", "k-points per direction of the mesh (periodic systems)",
               minimum=1),
      group="Real space", doc="Electrons on every site, from the states below zero energy "
                             "(pyqula's get_vev), drawn on the structure.",
      apply=lambda h, ctx: {"density": h.get_vev(nk=ctx.value("nk"))},
      script=lambda ctx: [f"arrays = dict(density=h.get_vev(nk={ctx.code('nk')}))"],
      plot={"kind": "structure_scalar", "values": "density", "clabel": "electrons per site"},
      cost=_mesh_cost())

entry("calculation", "magnetization", "Magnetization",
      IntParam("nk", 10, "k-points", "k-points per direction of the mesh (periodic systems)",
               minimum=1),
      group="Real space", doc="Spin expectation value (<Sx>, <Sy>, <Sz>) on every site from "
                             "the states below zero energy (pyqula's get_magnetization); "
                             "arrows on the structure. Needs a spinful Hamiltonian.",
      apply=lambda h, ctx: {"magnetization": h.get_magnetization(nk=ctx.value("nk"))},
      script=lambda ctx: [
          f"arrays = dict(magnetization=h.get_magnetization(nk={ctx.code('nk')}))"],
      plot={"kind": "structure_vector", "vectors": "magnetization", "clabel": "magnetization"},
      cost=_mesh_cost(3.0))


def _real_space_chern(h, ctx):
    from pyqula import topology
    _, c = topology.real_space_chern(h)
    return {"marker": c}


entry("calculation", "real_space_chern", "Local Chern marker",
      group="Topology", doc="Chern marker on every site of a finite system (pyqula's "
                           "topology.real_space_chern): deep inside a large flake it "
                           "approaches the bulk Chern number, the edge carries the opposite "
                           "weight. Needs a finite (0D) system: an island or a flake made "
                           "finite.",
      modules=("topology",), apply=_real_space_chern,
      script=lambda ctx: ["_, marker = topology.real_space_chern(h)",
                          "arrays = dict(marker=marker)"],
      plot={"kind": "structure_scalar", "values": "marker", "clabel": "Chern marker",
            "symmetric": True},
      cost=lambda p, size: 4 * cost.diagonalization(size["dimension"]))


# ---- k space
def _fermi_surface(h, ctx):
    kx, ky, weight = h.get_fermi_surface(e=ctx.value("energy"), nk=ctx.value("nk"),
                                         delta=ctx.value("delta"), write=False,
                                         **_operator_kwarg(ctx))
    return {"kx": kx, "ky": ky, "weight": weight}


entry("calculation", "fermi_surface", "Fermi surface",
      FloatParam("energy", 0.0, "energy"),
      FloatParam("delta", 0.05, "broadening", "Lorentzian width", minimum=1e-9),
      IntParam("nk", 60, "k-points", "k-points per direction", minimum=2),
      _operator(),
      group="Spectral", doc="Spectral weight at one energy over the Brillouin zone of a "
                           "two-dimensional system (pyqula's get_fermi_surface).",
      apply=_fermi_surface, script=lambda ctx: [
          f"kx, ky, weight = h.get_fermi_surface(e={ctx.code('energy')}, nk={ctx.code('nk')}, "
          f"delta={ctx.code('delta')}, write=False{_operator_code(ctx)})",
          "arrays = dict(kx=kx, ky=ky, weight=weight)"],
      plot={"kind": "heatmap", "x": "kx", "y": "ky", "c": "weight", "xlabel": "kx",
            "ylabel": "ky", "clabel": "spectral weight", "equal": True},
      cost=lambda p, size: p["nk"] ** 2 * cost.diagonalization(size["dimension"]))


def _spectral_function(h, ctx):
    from pyqula import kdos
    out = kdos.kdos_bands(h, energies=_energies(ctx), delta=ctx.value("delta"),
                          nk=ctx.value("nk"), mode=ctx.value("mode"), **_operator_kwarg(ctx))
    return {"k": out[0], "energies": out[1], "weight": out[2]}


entry("calculation", "spectral_function", "Spectral function",
      *_energies_params(),
      FloatParam("delta", 0.05, "broadening", "Lorentzian width", minimum=1e-9),
      IntParam("nk", 100, "k-points", "points along the k-path", minimum=2),
      ChoiceParam("mode", "ED", choices=("ED", "green"), label="method",
                  doc="ED: from the eigenstates; green: from the Green's function"),
      _operator(),
      group="Spectral", doc="Momentum-resolved spectral function A(k, E) along the default "
                           "k-path (pyqula's kdos.kdos_bands): broadened bands, weighted by "
                           "an operator if one is chosen.",
      modules=("kdos",), apply=_spectral_function, script=lambda ctx: [
          f"out = kdos.kdos_bands(h, energies={_energies_code(ctx)}, delta={ctx.code('delta')}, "
          f"nk={ctx.code('nk')}, mode={ctx.code('mode')}{_operator_code(ctx)})",
          "arrays = dict(k=out[0], energies=out[1], weight=out[2])"],
      plot={"kind": "heatmap", "x": "k", "y": "energies", "c": "weight",
            "xlabel": "k-path point", "ylabel": "energy", "clabel": "A(k, E)"},
      cost=lambda p, size: p["nk"] * cost.diagonalization(size["dimension"])
      * (1 if p["mode"] == "ED" else p["ne"] / 3))


def _surface(h, ctx):
    k, energies, surface, bulk = h.get_surface_kdos(
        energies=_energies(ctx), delta=ctx.value("delta"), nk=ctx.value("nk"), write=False,
        **_operator_kwarg(ctx))
    return {"k": k, "energies": energies, "surface": surface, "bulk": bulk}


def _surface_plot(params, arrays):
    import numpy as np
    if len(np.unique(np.round(arrays["k"], 10))) < 2:        # one-dimensional: no k
        return {"kind": "lines", "x": "energies", "y": "surface", "xlabel": "energy",
                "ylabel": "surface DOS"}
    return {"kind": "heatmap", "x": "k", "y": "energies", "c": "surface",
            "xlabel": "k along the surface", "ylabel": "energy",
            "clabel": "surface spectral function"}


entry("calculation", "surface_spectral_function", "Surface spectral function",
      *_energies_params(-2.0, 2.0, 100),
      FloatParam("delta", 0.02, "broadening", "imaginary part of the energy", minimum=1e-9),
      IntParam("nk", 60, "k-points", "points along the surface", minimum=2),
      _operator(),
      group="Spectral", doc="Spectral function on the surface of the semi-infinite system "
                           "(pyqula's get_surface_kdos, Green's function renormalization): "
                           "edge and surface states. A one-dimensional system gives the "
                           "density of states at its end.",
      apply=_surface, script=lambda ctx: [
          f"k, energies, surface, bulk = h.get_surface_kdos(energies={_energies_code(ctx)}, "
          f"delta={ctx.code('delta')}, nk={ctx.code('nk')}, write=False{_operator_code(ctx)})",
          "arrays = dict(k=k, energies=energies, surface=surface, bulk=bulk)"],
      plot=_surface_plot,
      cost=lambda p, size: 20 * p["nk"] * p["ne"] * cost.diagonalization(size["dimension"]) / 3)


# ---- topology
def _berry_map(h, ctx):
    import numpy as np
    kx, ky, b = h.get_berry_curvature(nk=ctx.value("nk"), write=False)
    return {"kx": np.asarray(kx), "ky": np.asarray(ky), "berry": np.asarray(b)}


entry("calculation", "berry_curvature", "Berry curvature map",
      IntParam("nk", 40, "k-points", "k-points per direction", minimum=2),
      group="Topology", doc="Berry curvature of the states below zero energy over the "
                           "Brillouin zone of a two-dimensional system (pyqula's "
                           "get_berry_curvature, Wilson loops).",
      apply=_berry_map, script=lambda ctx: [
          f"kx, ky, b = h.get_berry_curvature(nk={ctx.code('nk')}, write=False)",
          "arrays = dict(kx=np.asarray(kx), ky=np.asarray(ky), berry=np.asarray(b))"],
      plot={"kind": "heatmap", "x": "kx", "y": "ky", "c": "berry", "xlabel": "kx",
            "ylabel": "ky", "clabel": "Berry curvature", "symmetric": True, "equal": True},
      cost=lambda p, size: 3 * p["nk"] ** 2 * cost.diagonalization(size["dimension"]))


def _berry_path(h, ctx):
    from pyqula import topology
    k, b = topology.get_berry_curvature_path(h, nk=ctx.value("nk"))
    return {"k": k, "berry": b}


entry("calculation", "berry_curvature_path", "Berry curvature along the path",
      IntParam("nk", 200, "k-points", "points along the k-path", minimum=2),
      group="Topology", doc="Berry curvature of the states below zero energy along the "
                           "default k-path of a two-dimensional system.",
      modules=("topology",), apply=_berry_path, script=lambda ctx: [
          f"k, b = topology.get_berry_curvature_path(h, nk={ctx.code('nk')})",
          "arrays = dict(k=k, berry=b)"],
      plot={"kind": "lines", "x": "k", "y": "berry", "xlabel": "k-path point",
            "ylabel": "Berry curvature"},
      cost=lambda p, size: 3 * p["nk"] * cost.diagonalization(size["dimension"]))

scalar("chern", "Chern number",
       lambda h, ctx: {"chern": h.get_chern(nk=ctx.value("nk"))},
       lambda ctx: f"dict(chern=h.get_chern(nk={ctx.code('nk')}))",
       [["chern", "Chern number"]],
       (IntParam("nk", 40, "k-points", "k-points per direction", minimum=2),),
       cost_=lambda p, size: 3 * p["nk"] ** 2 * cost.diagonalization(size["dimension"]),
       doc="Chern number of the states below zero energy of a two-dimensional system "
           "(pyqula's get_chern, Berry curvature summed on a mesh).")

scalar("spin_chern", "Spin Chern number",
       lambda h, ctx: {"spin_chern": h.get_spin_chern(nk=ctx.value("nk"))},
       lambda ctx: f"dict(spin_chern=h.get_spin_chern(nk={ctx.code('nk')}))",
       [["spin_chern", "spin Chern number"]],
       (IntParam("nk", 30, "k-points", "k-points per direction", minimum=2),),
       cost_=lambda p, size: 6 * p["nk"] ** 2 * cost.diagonalization(size["dimension"]),
       doc="Spin Chern number (C+ - C-)/2 of the states below zero energy, split by the sign "
           "of the projected sz (pyqula's get_spin_chern); quantum spin Hall insulators.")


def _z2(h, ctx):
    from pyqula import topology
    return {"z2": topology.z2_invariant(h, nk=ctx.value("nk"), nt=ctx.value("nt"))}


scalar("z2", "Z2 invariant", _z2,
       lambda ctx: f"dict(z2=topology.z2_invariant(h, nk={ctx.code('nk')}, "
                   f"nt={ctx.code('nt')}))",
       [["z2", "Z2 parity (-1: topological, +1: trivial)"]],
       (IntParam("nk", 40, "k-points", "points of each Wilson loop", minimum=2),
        IntParam("nt", 40, "pumping steps", "points along the pumping direction", minimum=2)),
       cost_=lambda p, size: p["nk"] * p["nt"] * cost.diagonalization(size["dimension"]),
       modules=("topology",),
       doc="Z2 invariant of a two-dimensional time-reversal-symmetric system as a parity, "
           "-1 for a quantum spin Hall insulator and +1 for a trivial one, from the pumping "
           "of the hybrid Wannier centres (pyqula's topology.z2_invariant).")

scalar("gap", "Gap",
       lambda h, ctx: {"gap": h.get_gap()},
       lambda ctx: "dict(gap=h.get_gap())",
       [["gap", "gap"]], group="Spectral",
       cost_=lambda p, size: 400 * cost.diagonalization(size["dimension"]),
       doc="Smallest distance between the states below and above zero energy over the "
           "Brillouin zone (pyqula's get_gap, an indirect gap from a minimization).")

scalar("total_energy", "Total energy",
       lambda h, ctx: {"energy": h.get_total_energy(nk=ctx.value("nk"))},
       lambda ctx: f"dict(energy=h.get_total_energy(nk={ctx.code('nk')}))",
       [["energy", "total energy per cell"]],
       (IntParam("nk", 20, "k-points", "k-points per direction of the mesh", minimum=1),),
       group="Energetics", cost_=_mesh_cost(),
       doc="Energy of the states below zero energy, per unit cell (pyqula's "
           "get_total_energy).")


# ---- response
COMPONENTS = ("xx", "xy", "yx", "yy")


def _optical(h, ctx):
    import numpy as np
    omega, sigma = h.get_optical_conductivity(energies=_energies(ctx), nk=ctx.value("nk"),
                                              T=ctx.value("T"), delta=ctx.value("delta"))
    a, b = ("xyz".index(c) for c in ctx.value("component"))
    return {"omega": np.asarray(omega), "real": sigma[:, a, b].real,
            "imag": sigma[:, a, b].imag}


entry("calculation", "optical_conductivity", "Optical conductivity",
      *_energies_params(0.0, 4.0, 100),
      IntParam("nk", 40, "k-points", "k-points per direction of the mesh", minimum=1),
      FloatParam("T", 0.02, "temperature", minimum=0.0),
      FloatParam("delta", 0.05, "broadening", minimum=1e-9),
      ChoiceParam("component", "xx", choices=COMPONENTS, label="component",
                  doc="sigma_ab: xx is the absorption (its real part), xy the Hall response"),
      group="Response", doc="Kubo-Greenwood optical conductivity sigma_ab(omega) in units "
                           "of e^2/hbar (pyqula's get_optical_conductivity); one- and "
                           "two-dimensional systems.",
      apply=_optical, script=lambda ctx: [
          f"omega, sigma = h.get_optical_conductivity(energies={_energies_code(ctx)}, "
          f"nk={ctx.code('nk')}, T={ctx.code('T')}, delta={ctx.code('delta')})",
          f"a, b = ('xyz'.index(c) for c in {ctx.code('component')})",
          "arrays = dict(omega=np.asarray(omega), real=sigma[:, a, b].real, "
          "imag=sigma[:, a, b].imag)"],
      plot=lambda params: {"kind": "lines", "x": "omega", "y": "real", "xlabel": "frequency",
                           "ylabel": f"Re sigma_{params['component']}"},
      cost=lambda p, size: 3 * cost.kmesh(p["nk"], size["dimensionality"])
      * cost.diagonalization(size["dimension"]))
