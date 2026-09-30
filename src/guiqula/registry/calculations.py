"""Calculations. Each adapter returns plain arrays (never figures, PLAN.md
3.3) and names the plot kind that draws them (PLAN.md 3.4)."""
from guiqula.core.nearest import nearest_site
from guiqula.registry import cost
from guiqula.registry.base import entry
from guiqula.registry import kpaths
from guiqula.registry.params import (ChoiceParam, FloatParam, FloatVectorParam, IntParam,
                                     KPathParam, PositionsParam, SeedParam)


def _path(h, ctx, fraction=False):
    """{"kpath": the k-points, "ticks": vertex indices} of a calculation's
    k-path; for pyqula's default path {"kpath": its points} (kpaths.default_path:
    pyqula chooses them, so there are no vertices), and {} in 0D, which has no
    k. The names of the vertices, or of the high-symmetry points the default
    path goes through, go to the plot (the note "xticks"), at their indices,
    which is the k axis of the bands, or, with fraction, at their fraction of
    the path, index / number of points, which is the k axis pyqula gives a
    spectral function (kdos.write_kdos_bands)."""
    import numpy as np
    kpath, g = ctx.value("kpath"), h.geometry
    if kpath is None:
        ks = kpaths.default_path(g, ctx.value("nk"))
        if not len(ks):                        # a finite system
            return {}
    b, special = np.array([g.b1, g.b2, g.b3]), kpaths.special_points(g)
    if kpath is None:
        ticks, marks = None, kpaths.default_ticks(b, g.dimensionality, ks, special)
    else:
        ks, ticks = kpaths.path_points(b, kpaths.vertices_of(g, kpath), ctx.value("nk"))
        marks = list(zip(ticks, kpaths.tick_names(b, g.dimensionality, kpath, special)))
    scale = 1.0 / len(ks) if fraction else 1.0
    if marks:
        ctx.note("xticks", [[float(i) * scale, name] for i, name in marks])
    return {"kpath": ks} if ticks is None else {"kpath": ks, "ticks": ticks}


def _kpoints(h, path):
    """The reduced k (N, 3) of every point of a calculation's path, in
    units of the reciprocal lattice vectors (what a pick on the plot takes,
    core/picks.py): the points of _path; (0, 3) for a finite system, which
    has no k."""
    import numpy as np
    if int(h.geometry.dimensionality) == 0 or not path:
        return np.zeros((0, 3))
    return np.asarray(path["kpath"], dtype=float).reshape(-1, 3)


def _kpoints_script():
    """The line of an exported script that sets kpoints as _kpoints does."""
    return ["kpoints = np.zeros((0, 3)) if h.geometry.dimensionality == 0 else "
            "np.asarray(ks, dtype=float).reshape(-1, 3)"]


def _bands(h, ctx):
    import numpy as np
    nk, operator = ctx.value("nk"), ctx.value("operator")
    path = _path(h, ctx)
    kpoints = _kpoints(h, path)
    # the points walked: the path's, or one in 0D
    kwargs = {"nk": nk, "write": False, "callback": ctx.progress_callback(max(len(kpoints), 1))}
    if path:
        kwargs["kpath"] = path["kpath"]
    if operator is not None:
        kwargs["operator"] = operator
    out = h.get_bands(**kwargs)
    k_index = np.unique(out[0])
    arrays = {"k": k_index, "energies": out[1].reshape(len(k_index), -1), "kpoints": kpoints}
    if operator is not None:
        arrays["weights"] = out[2].reshape(len(k_index), -1)
    if "ticks" in path:
        arrays["ticks"] = path["ticks"]
    return arrays


def _path_script(ctx):
    """The lines that set ks, the points of the path, as _path does (None in
    0D, where pyqula's default path is a single point)."""
    kpath = ctx.value("kpath")
    if kpath is not None:
        return kpaths.script(kpath, ctx.value("nk"))
    return ["if h.geometry.dimensionality == 0:",
            "    ks = None                                  # a finite system has no k",
            "else:",
            f"    ks = np.asarray(h.geometry.get_kpath(None, nk={ctx.code('nk')}, write=False), "
            "dtype=float).reshape(-1, 3)",
            "    if h.geometry.dimensionality == 2:         # pyqula's path leaves out its "
            "opening Gamma",
            "        ks = np.vstack([np.zeros((1, 3)), ks])"]


def _bands_script(ctx):
    operator = ctx.value("operator")
    op = "" if operator is None else f", operator={operator!r}"
    lines = _path_script(ctx) + [
        f"out = h.get_bands(nk={ctx.code('nk')}{op}, kpath=ks, write=False)",
        "k = np.unique(out[0])",
        "energies = out[1].reshape(len(k), -1)"] + _kpoints_script()
    if operator is None:
        lines.append("arrays = dict(k=k, energies=energies, kpoints=kpoints)")
    else:
        lines += ["weights = out[2].reshape(len(k), -1)",
                  "arrays = dict(k=k, energies=energies, weights=weights, kpoints=kpoints)"]
    if ctx.value("kpath") is not None:
        lines.append("arrays['ticks'] = ticks")
    return lines


def _with_ticks(plot, params, arrays):
    """A k-path's axis (its vertices become ticks: the engine adds them)."""
    if params.get("kpath") is not None and "ticks" in arrays:
        plot["xlabel"] = "k"
    return plot


def _bands_plot(params, arrays):
    plot = {"x": "k", "y": "energies", "xlabel": "k-path point", "ylabel": "energy",
            "picks": {"x": "kpath", "y": "energy"}}
    if params.get("operator") is None:
        return _with_ticks(dict(plot, kind="lines"), params, arrays)
    return _with_ticks(dict(plot, kind="colored_scatter", c="weights",
                            clabel=params["operator"]), params, arrays)


entry("calculation", "bands", "Band structure",
      IntParam("nk", 200, "k-points", "points along the k-path", minimum=2),
      ChoiceParam("operator", None, source="operators", optional=True, label="operator",
                  doc="colour the bands by this operator's expectation value"),
      KPathParam(doc="the vertices of the path (labels such as G, K, M, or reduced "
                     "coordinates); empty: pyqula's default path. The k-space tab edits it."),
      group="Spectral", doc="Bands along a path through the Brillouin zone (by default the "
                           "high-symmetry path pyqula chooses for the geometry).",
      apply=_bands, script=_bands_script, plot=_bands_plot,
      cost=lambda p, size: p["nk"] * cost.diagonalization(size["dimension"])
      * (2 if p["operator"] else 1),
      guide=("Electronic band structures", "guiqula: The k-space tab",
             "guiqula: Picking from a plot"), pyqula=("h.get_bands",))


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
                           "xlabel": "energy", "ylabel": "DOS", "picks": {"x": "energy"}},
      guide=("Density of states", "Chebyshev kernel polynomial (KPM) methods"), pyqula=("h.get_dos",))


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
           modules=(), guide=(), pyqula=()):
    """A calculation returning numbers: value(h, ctx) -> {name: number},
    code(ctx) -> the source of the same dict; rows: [[name, label]]."""
    entry("calculation", kind, label, *params, group=group, doc=doc, modules=modules,
          guide=guide, pyqula=pyqula,
          apply=lambda h, ctx: {k: float(v) for k, v in value(h, ctx).items()},
          script=lambda ctx: [f"arrays = {{k: float(v) for k, v in ({code(ctx)}).items()}}"],
          plot={"kind": "scalar", "rows": [list(r) for r in rows]}, cost=cost_)


# ---- real space
def _kpoint(name="k", doc=""):
    """A k-point in reduced coordinates, which a pick sets (quantity kpoint)."""
    return FloatVectorParam(name, None, "k-point", doc, length=3, optional=True,
                            quantity="kpoint")


def _ldos(h, ctx):
    k = ctx.value("k")
    extra = {} if k is None else {"ks": [k]}          # one diagonalization, at that k
    _, d = h.get_ldos(e=ctx.value("energy"), delta=ctx.value("delta"), nk=ctx.value("nk"),
                      nrep=1, write=False, return_rd=True, **_operator_kwarg(ctx), **extra)
    return {"ldos": d}


def _ldos_cost(p, size):
    if p["k"] is not None:
        return cost.diagonalization(size["dimension"])
    return _mesh_cost()(p, size)


entry("calculation", "ldos", "Local density of states",
      FloatParam("energy", 0.0, "energy", quantity="energy"),
      FloatParam("delta", 0.05, "broadening", "Lorentzian width", minimum=1e-9),
      IntParam("nk", 10, "k-points", "k-points per direction of the mesh (periodic systems)",
               minimum=1),
      _operator(),
      _kpoint(doc="reduced coordinates [k1, k2, k3] of one k-point, the states at that k "
                  "alone (a pick on the bands sets it); empty: the mesh of nk"),
      group="Real space", doc="Density of states at one energy on every site (pyqula's "
                             "get_ldos), drawn on the structure; over the k-mesh, or at one "
                             "k-point.",
      apply=_ldos, script=lambda ctx: [
          f"_, ldos = h.get_ldos(e={ctx.code('energy')}, delta={ctx.code('delta')}, "
          f"nk={ctx.code('nk')}, nrep=1, write=False, return_rd=True{_operator_code(ctx)}"
          + ("" if ctx.value("k") is None else f", ks=[{ctx.code('k')}]") + ")",
          "arrays = dict(ldos=ldos)"],
      plot={"kind": "structure_scalar", "values": "ldos", "clabel": "LDOS"},
      cost=_ldos_cost,
      guide=("Local density of states", "guiqula: Picking from a plot"), pyqula=("h.get_ldos",))


def _eigenstate(h, ctx):
    import numpy as np
    from pyqula.htk import eigenvectors
    energies, states = eigenvectors.get_eigenvectors(h, k=ctx.value("k"))
    energies = np.real(energies)
    band = ctx.value("band")
    if band is None:
        i = int(np.argmin(np.abs(energies - ctx.value("energy"))))
    elif band < len(energies):
        i = band
    else:
        raise ValueError(f"band {band}: there are {len(energies)} states (0 to "
                         f"{len(energies) - 1})")
    return {"weight": np.real(h.full2profile(np.abs(states[i]) ** 2)),
            "energy": np.array(energies[i]), "energies": energies}


def _eigenstate_script(ctx):
    band = ctx.value("band")
    pick = f"int(np.argmin(np.abs(energies - {ctx.code('energy')})))" if band is None else \
        repr(band)
    return [f"energies, states = eigenvectors.get_eigenvectors(h, k={ctx.code('k')})",
            "energies = np.real(energies)",
            f"i = {pick}",
            "arrays = dict(weight=np.real(h.full2profile(np.abs(states[i]) ** 2)), "
            "energy=np.array(energies[i]), energies=energies)"]


entry("calculation", "eigenstate", "Eigenstate",
      FloatVectorParam("k", (0.0, 0.0, 0.0), "k-point", "reduced coordinates [k1, k2, k3] "
                       "(a pick on the bands or a click in the k-space tab sets it); a "
                       "finite system has one k and ignores it", quantity="kpoint"),
      FloatParam("energy", 0.0, "energy", "the state nearest this energy is drawn",
                 quantity="energy"),
      IntParam("band", None, "band", "the state by its index at k, from the lowest (0); "
                                     "empty: the one nearest the energy", minimum=0,
               optional=True),
      group="Real space", doc="The weight of one eigenstate on every site, |psi(r)|^2 summed "
                             "over the spin and Nambu components (pyqula's get_eigenvectors "
                             "and full2profile): the state nearest an energy at a k-point.",
      modules=("htk.eigenvectors",), apply=_eigenstate, script=_eigenstate_script,
      plot=lambda params, arrays: {
          "kind": "structure_scalar", "values": "weight",
          "clabel": f"|ψ|² of the state at E = {float(arrays['energy']):.4g}"},
      cost=lambda p, size: cost.diagonalization(size["dimension"]),
      guide=("Electronic band structures", "Local density of states",
             "guiqula: Picking from a plot"),
      pyqula=("htk.eigenvectors.get_eigenvectors", "h.full2profile"))


def _projector(h, positions, tol):
    """A diagonal matrix with 1 on every component (spin, Nambu) of the
    sites within tol of the positions: the operator of a DOS on sites. Not
    pyqula's get_operator of a function of position, which builds it with
    add_onsite and so carries opposite signs on the hole block of a Nambu
    Hamiltonian, where it is no projector."""
    import numpy as np
    from scipy import sparse
    r = np.asarray(h.geometry.r, dtype=float)
    find = nearest_site(positions, tol)
    sites = [i for i, p in enumerate(r) if find(p) >= 0]
    if not sites:
        raise ValueError(f"no site is within {tol} of the positions")
    size = h.intra.shape[0]
    block = size // len(r)
    diagonal = np.zeros(size)
    for i in sites:
        diagonal[block * i:block * (i + 1)] = 1.0
    return sparse.diags(diagonal, format="csc")


def _site_dos(h, ctx):
    import numpy as np
    P = _projector(h, ctx.value("positions"), ctx.value("tol"))
    es, ds = h.get_dos(energies=_energies(ctx), delta=ctx.value("delta"), nk=ctx.value("nk"),
                       operator=P, write=False)
    return {"energies": np.asarray(es, dtype=float), "dos": np.asarray(ds, dtype=float)}


def _site_dos_script(ctx):
    return [
        "from scipy import sparse",
        "r = np.asarray(h.geometry.r, dtype=float)",
        f"find = nearest_site({ctx.code('positions')}, {ctx.code('tol')})",
        "sites = [i for i, p in enumerate(r) if find(p) >= 0]",
        "block = h.intra.shape[0] // len(r)",
        "diagonal = np.zeros(h.intra.shape[0])",
        "for i in sites:",
        "    diagonal[block * i:block * (i + 1)] = 1.0",
        f"es, ds = h.get_dos(energies={_energies_code(ctx)}, delta={ctx.code('delta')}, "
        f"nk={ctx.code('nk')}, operator=sparse.diags(diagonal, format='csc'), write=False)",
        "arrays = dict(energies=np.asarray(es, dtype=float), dos=np.asarray(ds, dtype=float))"]


entry("calculation", "site_dos", "DOS on sites",
      PositionsParam("positions", (), "sites", "the positions of the sites (a pick on a result "
                                               "drawn on the atoms, or the canvas selection, "
                                               "sets them)", quantity="sites"),
      FloatParam("tol", 0.05, "tolerance", "a site this close to a position is one of them",
                 minimum=1e-6),
      *_energies_params(-4.0, 4.0, 200),
      FloatParam("delta", 0.05, "broadening", "Lorentzian width", minimum=1e-9),
      IntParam("nk", 20, "k-points", "k-points per direction of the mesh", minimum=1),
      group="Real space", doc="Density of states projected on chosen sites (pyqula's get_dos "
                             "with the projector on them as the operator): the local spectrum "
                             "an STM tip sees there.",
      apply=_site_dos, script=_site_dos_script, helpers=(nearest_site,),
      plot={"kind": "lines", "x": "energies", "y": "dos", "xlabel": "energy",
            "ylabel": "DOS on the sites", "picks": {"x": "energy"}},
      cost=_mesh_cost(2.0),
      guide=("Density of states", "guiqula: Picking from a plot"), pyqula=("h.get_dos",))

entry("calculation", "density", "Electron density",
      IntParam("nk", 10, "k-points", "k-points per direction of the mesh (periodic systems)",
               minimum=1),
      group="Real space", doc="Electrons on every site, from the states below zero energy "
                             "(pyqula's get_vev), drawn on the structure.",
      apply=lambda h, ctx: {"density": h.get_vev(nk=ctx.value("nk"))},
      script=lambda ctx: [f"arrays = dict(density=h.get_vev(nk={ctx.code('nk')}))"],
      plot={"kind": "structure_scalar", "values": "density", "clabel": "electrons per site"},
      cost=_mesh_cost(),
      pyqula=("h.get_vev",))

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
      cost=_mesh_cost(3.0), guide=("guiqula: Drawing in 3D",),
      pyqula=("h.get_magnetization",))


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
      cost=lambda p, size: 4 * cost.diagonalization(size["dimension"]),
      guide=("Chern number in real-space", "Topological markers"), pyqula=("topology.real_space_chern",))


# ---- k space
def _fermi_surface(h, ctx):
    kx, ky, weight = h.get_fermi_surface(e=ctx.value("energy"), nk=ctx.value("nk"),
                                         delta=ctx.value("delta"), write=False,
                                         **_operator_kwarg(ctx))
    return {"kx": kx, "ky": ky, "weight": weight}


entry("calculation", "fermi_surface", "Fermi surface",
      FloatParam("energy", 0.0, "energy", quantity="energy"),
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
            "ylabel": "ky", "clabel": "spectral weight", "equal": True,
            "picks": {"x": "kmesh", "y": "kmesh", "fixed": {"energy": "energy"}}},
      cost=lambda p, size: p["nk"] ** 2 * cost.diagonalization(size["dimension"]),
      extra={"dimensions": (2,)},        # a pick offers it on two-dimensional systems only
      guide=("Fermi surfaces", "guiqula: Picking from a plot"), pyqula=("h.get_fermi_surface",))


def _qpi(h, ctx):
    import numpy as np
    q, _, qpi = h.get_qpi(energies=[ctx.value("energy")], nk=ctx.value("nk"),
                          delta=ctx.value("delta"), mode=ctx.value("mode"), write=False)
    q = np.asarray(q, dtype=float)
    return {"qx": q[:, 0], "qy": q[:, 1], "qpi": np.asarray(qpi, dtype=float)[0]}


entry("calculation", "qpi", "Quasiparticle interference",
      FloatParam("energy", 0.0, "energy", quantity="energy"),
      IntParam("nk", 20, "k-points", "k-points per direction", minimum=2),
      FloatParam("delta", 0.1, "broadening", "Lorentzian width", minimum=1e-9),
      ChoiceParam("mode", "response", choices=("response", "pm"), label="method",
                  doc="response: the joint density of states of the clean bands; pm: the "
                      "autoconvolution of the k-resolved spectral weight, slower"),
      group="Spectral", doc="The quasiparticle interference pattern at one energy of a "
                           "two-dimensional system over q (pyqula's get_qpi): what the Fourier "
                           "transform of an STM conductance map around a defect shows.",
      apply=_qpi, script=lambda ctx: [
          f"q, _, qpi = h.get_qpi(energies=[{ctx.code('energy')}], nk={ctx.code('nk')}, "
          f"delta={ctx.code('delta')}, mode={ctx.code('mode')}, write=False)",
          "q = np.asarray(q, dtype=float)",
          "arrays = dict(qx=q[:, 0], qy=q[:, 1], qpi=np.asarray(qpi, dtype=float)[0])"],
      plot={"kind": "heatmap", "x": "qx", "y": "qy", "c": "qpi", "xlabel": "qx",
            "ylabel": "qy", "clabel": "QPI", "equal": True,
            "picks": {"fixed": {"energy": "energy"}}},      # q is not a k-point of the system
      cost=lambda p, size: cost.kmesh(p["nk"], 2) * cost.diagonalization(size["dimension"])
      * (4 if p["mode"] == "pm" else 1) + 1e-7 * (2 * p["nk"]) ** 2 * p["nk"] ** 2,
      extra={"dimensions": (2,)},
      guide=("Quasiparticle interference", "guiqula: Picking from a plot"),
      pyqula=("h.get_qpi",))


def _spectral_function(h, ctx):
    from pyqula import kdos
    path = _path(h, ctx, fraction=True)        # pyqula's k axis: index / number of points
    extra = {"kpath": path["kpath"]} if path else {}
    kpoints = _kpoints(h, path)
    out = kdos.kdos_bands(h, energies=_energies(ctx), delta=ctx.value("delta"),
                          nk=ctx.value("nk"), mode=ctx.value("mode"), **_operator_kwarg(ctx),
                          **extra)
    arrays = {"k": out[0], "energies": out[1], "weight": out[2], "kpoints": kpoints}
    if "ticks" in path:
        arrays["ticks"] = path["ticks"]
    return arrays


entry("calculation", "spectral_function", "Spectral function",
      *_energies_params(),
      FloatParam("delta", 0.05, "broadening", "Lorentzian width", minimum=1e-9),
      IntParam("nk", 100, "k-points", "points along the k-path", minimum=2),
      ChoiceParam("mode", "ED", choices=("ED", "green"), label="method",
                  doc="ED: from the eigenstates; green: from the Green's function"),
      _operator(),
      KPathParam(doc="the vertices of the path (labels or reduced coordinates); empty: "
                     "pyqula's default path"),
      group="Spectral", doc="Momentum-resolved spectral function A(k, E) along a k-path "
                           "(pyqula's kdos.kdos_bands): broadened bands, weighted by an "
                           "operator if one is chosen.",
      modules=("kdos",), apply=_spectral_function, script=lambda ctx: _path_script(ctx) + [
          f"out = kdos.kdos_bands(h, energies={_energies_code(ctx)}, delta={ctx.code('delta')}, "
          f"nk={ctx.code('nk')}, mode={ctx.code('mode')}{_operator_code(ctx)}, kpath=ks)"]
      + _kpoints_script() + ["arrays = dict(k=out[0], energies=out[1], weight=out[2], "
                             "kpoints=kpoints)"]
      + (["arrays['ticks'] = ticks"] if ctx.value("kpath") is not None else []),
      plot=lambda params, arrays: _with_ticks(
          {"kind": "heatmap", "x": "k", "y": "energies", "c": "weight",
           "xlabel": "k-path point", "ylabel": "energy", "clabel": "A(k, E)",
           "picks": {"x": "kpath", "y": "energy"}}, params, arrays),
      cost=lambda p, size: p["nk"] * cost.diagonalization(size["dimension"])
      * (1 if p["mode"] == "ED" else p["ne"] / 3),
      guide=("Momentum resolved spectral functions",), pyqula=("kdos.kdos_bands",))


def _surface(h, ctx):
    k, energies, surface, bulk = h.get_surface_kdos(
        energies=_energies(ctx), delta=ctx.value("delta"), nk=ctx.value("nk"), write=False,
        **_operator_kwarg(ctx))
    return {"k": k, "energies": energies, "surface": surface, "bulk": bulk}


def _surface_plot(params, arrays):
    import numpy as np
    if len(np.unique(np.round(arrays["k"], 10))) < 2:        # one-dimensional: no k
        return {"kind": "lines", "x": "energies", "y": "surface", "xlabel": "energy",
                "ylabel": "surface DOS", "picks": {"x": "energy"}}
    # its k runs along the surface, 0 to 1: not a k-point of the system
    return {"kind": "heatmap", "x": "k", "y": "energies", "c": "surface",
            "xlabel": "k along the surface", "ylabel": "energy",
            "clabel": "surface spectral function", "picks": {"y": "energy"}}


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
      cost=lambda p, size: 20 * p["nk"] * p["ne"] * cost.diagonalization(size["dimension"]) / 3,
      guide=("Surface spectral functions",), pyqula=("h.get_surface_kdos",))


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
            "ylabel": "ky", "clabel": "Berry curvature", "symmetric": True, "equal": True,
            "picks": {"x": "kmesh", "y": "kmesh"}},
      cost=lambda p, size: 3 * p["nk"] ** 2 * cost.diagonalization(size["dimension"]),
      guide=("Chern number",), pyqula=("h.get_berry_curvature",))


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
      cost=lambda p, size: 3 * p["nk"] * cost.diagonalization(size["dimension"]),
      guide=("Chern number",), pyqula=("topology.get_berry_curvature_path",))

scalar("chern", "Chern number",
       lambda h, ctx: {"chern": h.get_chern(nk=ctx.value("nk"))},
       lambda ctx: f"dict(chern=h.get_chern(nk={ctx.code('nk')}))",
       [["chern", "Chern number"]],
       (IntParam("nk", 40, "k-points", "k-points per direction", minimum=2),),
       cost_=lambda p, size: 3 * p["nk"] ** 2 * cost.diagonalization(size["dimension"]),
       doc="Chern number of the states below zero energy of a two-dimensional system "
           "(pyqula's get_chern, Berry curvature summed on a mesh).",
       guide=("Chern number",), pyqula=("h.get_chern",))

scalar("spin_chern", "Spin Chern number",
       lambda h, ctx: {"spin_chern": h.get_spin_chern(nk=ctx.value("nk"))},
       lambda ctx: f"dict(spin_chern=h.get_spin_chern(nk={ctx.code('nk')}))",
       [["spin_chern", "spin Chern number"]],
       (IntParam("nk", 30, "k-points", "k-points per direction", minimum=2),),
       cost_=lambda p, size: 6 * p["nk"] ** 2 * cost.diagonalization(size["dimension"]),
       doc="Spin Chern number (C+ - C-)/2 of the states below zero energy, split by the sign "
           "of the projected sz (pyqula's get_spin_chern); quantum spin Hall insulators.",
       guide=("Spin Chern number and mirror Chern number",), pyqula=("h.get_spin_chern",))


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
           "of the hybrid Wannier centres (pyqula's topology.z2_invariant).",
       guide=("Z2 invariant",), pyqula=("topology.z2_invariant",))

scalar("gap", "Gap",
       lambda h, ctx: {"gap": h.get_gap()},
       lambda ctx: "dict(gap=h.get_gap())",
       [["gap", "gap"]], group="Spectral",
       cost_=lambda p, size: 400 * cost.diagonalization(size["dimension"]),
       doc="Smallest distance between the states below and above zero energy over the "
           "Brillouin zone (pyqula's get_gap, an indirect gap from a minimization).",
       pyqula=("h.get_gap",))

scalar("total_energy", "Total energy",
       lambda h, ctx: {"energy": h.get_total_energy(nk=ctx.value("nk"))},
       lambda ctx: f"dict(energy=h.get_total_energy(nk={ctx.code('nk')}))",
       [["energy", "total energy per cell"]],
       (IntParam("nk", 20, "k-points", "k-points per direction of the mesh", minimum=1),),
       group="Energetics", cost_=_mesh_cost(),
       doc="Energy of the states below zero energy, per unit cell (pyqula's "
           "get_total_energy).",
       pyqula=("h.get_total_energy",))


# ---- response
COMPONENTS = ("xx", "xy", "yx", "yy")


def _optical(h, ctx):
    import numpy as np
    h = h.get_dense()          # pyqula's k-space generator fails on a sparse construction
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
          "h = h.get_dense()",
          f"omega, sigma = h.get_optical_conductivity(energies={_energies_code(ctx)}, "
          f"nk={ctx.code('nk')}, T={ctx.code('T')}, delta={ctx.code('delta')})",
          f"a, b = ('xyz'.index(c) for c in {ctx.code('component')})",
          "arrays = dict(omega=np.asarray(omega), real=sigma[:, a, b].real, "
          "imag=sigma[:, a, b].imag)"],
      plot=lambda params: {"kind": "lines", "x": "omega", "y": "real", "xlabel": "frequency",
                           "ylabel": f"Re sigma_{params['component']}",
                           "picks": {"x": "frequency"}},
      cost=lambda p, size: 3 * cost.kmesh(p["nk"], size["dimensionality"])
      * cost.diagonalization(size["dimension"]),
      guide=("Optical conductivity",), pyqula=("h.get_optical_conductivity",))
