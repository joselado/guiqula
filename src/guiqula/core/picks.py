"""Picks (PLAN.md phase 7): a point of a plot read as the physical values
it stands for, in a closed vocabulary of quantities, so that any
calculation whose parameters take them can be started from the point or
moved to it (registry/picks.py lists what a pick can do, the window's
pick and pick_to actions do it).

A calculation's plot spec names what its axes carry in ``picks`` (AXES):

- ``{"x": "kpath", "y": "energy"}``: a band structure or a spectral
  function; the x of a point is its place along the path, and the result's
  ``kpoints`` array holds the reduced k of every point of the path;
- ``{"x": "energy"}``: a density of states; ``{"y": "energy"}``: the
  surface spectral function, whose k runs along the surface and is not a
  k-point of the system;
- ``{"x": "kmesh", "y": "kmesh"}``: a map over the Brillouin zone in
  pyqula's mesh coordinates, which the result's ``kspace`` (its ``k2K``
  matrix) takes to reduced k;
- ``{"x": "parameter"}`` or two of them: a sweep, whose spec says in
  ``parameters`` what each axis sets ([entry, param, component]);
- ``{"x": "frequency"}``: the optical conductivity;
- ``"fixed": {quantity: parameter}``: a value the calculation holds, part
  of every point of it (a Fermi surface is at one energy, so a click on it
  is a k-point and that energy);

and a result drawn on the atoms yields ``sites`` by its kind, stored by
position (never by index, so that a pick survives a change upstream as
far as it is meaningful).

numpy only, like nearest.py: the window, the remote API and the tests
share it.
"""
import numpy as np

QUANTITIES = ("energy", "kpoint", "sites", "parameter", "frequency")
# what an axis of a plot carries -> the quantity a pick on it yields
AXES = {"energy": "energy", "frequency": "frequency", "kpath": "kpoint", "kmesh": "kpoint",
        "parameter": "parameter"}
ON_STRUCTURE = ("structure_scalar", "structure_vector")
SYMBOLS = {"energy": "E", "frequency": "ω", "kpoint": "k"}
RERUN = "was computed before its k-points were kept: run it again to pick a k-point"


class PickError(ValueError):
    pass


def number(value):
    """A picked value as the menus write it: three significant digits."""
    text = f"{float(value):.3g}"
    return "0" if text == "-0" else text


def kpoint_text(k):
    return "(" + ", ".join(number(c) for c in k) + ")"


def parameter_text(target):
    """"t1 m[z] = 0.4" for {"entry", "param", "component", "value"}."""
    component = target.get("component")
    where = f"{target['entry']} {target['param']}" + (
        "" if component is None else f"[{'xyz'[component]}]")
    return f"{where} = {number(target['value'])}"


def describe(values):
    """The label of picked values: "E = 0.3 · k = (0.333, 0.333, 0)"."""
    parts = []
    for quantity in ("energy", "kpoint", "frequency"):
        if quantity in values:
            value = values[quantity]
            text = kpoint_text(value) if quantity == "kpoint" else number(value)
            parts.append(f"{SYMBOLS[quantity]} = {text}")
    for target in values.get("parameter", []):
        parts.append(parameter_text(target))
    sites = values.get("sites")
    if sites:
        parts.append(f"site at ({number(sites[0][0])}, {number(sites[0][1])})"
                     if len(sites) == 1 else f"{len(sites)} sites")
    return " · ".join(parts)


def spec_of(result):
    """What the axes of a result carry: {"x": axis, "y": axis, "fixed":
    {...}}, {"sites": True} for a result drawn on the atoms, {} for one
    with nothing to pick (a scalar, or a result saved before phase 7)."""
    kind = result.plot.get("kind")
    if kind in ON_STRUCTURE:
        return {"sites": True}
    if kind == "scalar":
        return {}
    return dict(result.plot.get("picks") or {})


def _path_index(result, x):
    """The index of the path point nearest to x on the k axis drawn (the
    bands' indices, or pyqula's fraction along the path for a spectral
    function)."""
    k = np.unique(np.round(np.asarray(result.arrays[result.plot["x"]], dtype=float).ravel(), 12))
    if len(k) == 0:
        return None
    return int(np.argmin(np.abs(k - float(x))))


def _along_path(result, x, notes):
    kpoints = result.arrays.get("kpoints")
    if kpoints is None:
        notes.append(f"{result.calculation} {RERUN}")
        return None
    kpoints = np.asarray(kpoints, dtype=float).reshape(-1, 3)
    if len(kpoints) == 0:                  # a finite system: no k
        return None
    i = _path_index(result, x)
    if i is None:
        return None
    return [float(c) for c in kpoints[min(i, len(kpoints) - 1)]]


def mesh_node(result, x, y):
    """The node of a map over the zone nearest to (x, y), in the mesh
    coordinates it is drawn in (its cell)."""
    kx = np.asarray(result.arrays[result.plot["x"]], dtype=float).ravel()
    ky = np.asarray(result.arrays[result.plot["y"]], dtype=float).ravel()
    if len(kx) == 0 or len(kx) != len(ky):
        return float(x), float(y)
    i = int(np.argmin(np.hypot(kx - x, ky - y)))
    return float(kx[i]), float(ky[i])


def reduced_k(kspace, kx, ky):
    """Reduced k [k1, k2, k3] of a point of pyqula's mesh, through the
    k2K matrix of the geometry (what the k-space tab uses: reduced = k2K
    @ mesh); None when there is none (a result without it, or 1D)."""
    if not kspace or kspace.get("k2K") is None:
        return None
    reduced = np.asarray(kspace["k2K"], dtype=float) @ np.array([kx, ky, 0.0])
    return [float(round(c, 12)) + 0.0 for c in reduced]


def pick(result, x=None, y=None, index=None, sites=None):
    """What a point of a result's plot stands for: {"values": {quantity:
    value}, "label", "point": [x, y], "notes": [why something could not be
    picked]}. x, y: data coordinates, the snapped ones of the drawn point
    nearest the cursor when the view found one (the readout's rule), else
    the cursor's; index: that drawn point's index (a site, for a result on
    the atoms, whose drawn points are the sites in order); sites: several
    site indices (a box or a lasso on the result view)."""
    spec = spec_of(result)
    values, notes = {}, []
    if spec.get("sites"):
        chosen = list(sites) if sites is not None else [] if index is None else [index]
        structure = result.structure
        if chosen and structure is not None:
            positions = np.asarray(structure["positions"], dtype=float)
            if any(not 0 <= int(i) < len(positions) for i in chosen):
                raise PickError(f"site indices go from 0 to {len(positions) - 1}")
            values["sites"] = [[float(c) for c in positions[int(i)]] for i in chosen]
        elif not chosen:
            notes.append("no atom here: click on one, or draw a box or a lasso around several")
    else:
        coordinates = {"x": x, "y": y}
        if spec.get("x") == "kmesh" and spec.get("y") == "kmesh" and x is not None \
                and y is not None:
            kx, ky = mesh_node(result, float(x), float(y))
            k = reduced_k(result.kspace, kx, ky)
            if k is not None:
                values["kpoint"] = k
            elif result.kspace is None:
                notes.append(f"{result.calculation} {RERUN}")
            coordinates = {}
        for axis, coordinate in coordinates.items():
            carrier = spec.get(axis)
            if carrier is None or coordinate is None:
                continue
            if carrier in ("energy", "frequency"):
                values[carrier] = float(coordinate)
            elif carrier == "kpath":
                k = _along_path(result, coordinate, notes)
                if k is not None:
                    values["kpoint"] = k
            elif carrier == "parameter":
                target = (result.plot.get("parameters") or {}).get(axis)
                if target is not None:
                    entry, param, component = target
                    values.setdefault("parameter", []).append(
                        {"entry": entry, "param": param, "component": component,
                         "value": float(coordinate)})
        for quantity, param in (spec.get("fixed") or {}).items():
            if isinstance(result.params.get(param), (int, float)):
                values.setdefault(quantity, float(result.params[param]))
    if not spec:
        notes.append(f"a {result.plot.get('kind')} result has nothing to pick")
    return {"values": values, "label": describe(values),
            "point": None if x is None or y is None else [float(x), float(y)], "notes": notes}
