"""What a pick can do (PLAN.md phase 7): the targets of the values a point
of a plot stands for (core/picks.py), computed from what the parameters
of the calculations declare they take (``quantity``), never listed by
pairs, so that a new source or target is one declaration on an existing
entry. In order:

- every calculation of the system with a parameter taking a picked
  quantity, moved to it ("c3 Local density of states: energy = 0.3"; its
  other parameters kept), unless it holds that value already;
- every calculation kind applicable to the system with such a parameter,
  added with the picked values and its defaults otherwise, named after
  where it came from ("at E = 0.3 from c1"); a parameter that may be left
  empty (the LDOS's k-point, empty: over the k-mesh) gives two, without it
  and with it, and an existing calculation that leaves it empty keeps it
  so;
- the swept parameters of a sweep, set: the Document at that point of the
  phase diagram, and the sweep's calculation run there;
- a picked k-point as a new vertex of the k-path of every calculation that
  has one;
- picked sites selected on the canvas, or made a region;
- a picked energy as the Fermi level: an onsite term named "Fermi level"
  whose mu shifts the spectrum so that the energy sits at zero, which every
  calculation counting the states below zero energy then sees. Offered on
  a Hamiltonian without pairing only: in Nambu, add_onsite enters with
  opposite signs on the electron and hole blocks, a chemical potential
  that changes the pairing problem rather than shifting the spectrum,
  whose zero is the Fermi level already.

A target is a dict with ``target`` (set, add, parameter, kpath,
select_sites, region, fermi_level), what doing it needs, and ``label``,
the text of the menu. pyqula-free, like pipeline.py.
"""
from guiqula.core import picks as pick_tools
from guiqula.core.document import Document, terms_of
from guiqula.core import fields
from guiqula.registry import base as registry
from guiqula.registry.params import KPathParam

FERMI_LEVEL = "Fermi level"     # the name of the onsite term the Fermi-level target keeps


def _fits(spec, dimensionality):
    """Whether a calculation applies to a system of this dimensionality
    (an entry's extra "dimensions"; unknown: yes)."""
    dimensions = spec.extra.get("dimensions")
    return dimensions is None or dimensionality is None or dimensionality in dimensions


def _taken(spec, values):
    """{parameter: picked value} of the parameters of a calculation that
    take a picked quantity."""
    return {p.name: values[p.quantity] for p in spec.params
            if p.quantity is not None and p.quantity in values}


def _optional(spec, name):
    """Whether a parameter may be left empty, which is a mode of its own
    (an LDOS without a k-point is over the k-mesh)."""
    return getattr(spec.param_map[name], "optional", False)


def _variants(spec, values):
    """The parameters a new calculation takes from picked values: those
    without the optional ones first (the LDOS at the energy, over the
    k-mesh), then with them (the LDOS at the energy and the k-point)."""
    taken = _taken(spec, values)
    required = {name: v for name, v in taken.items() if not _optional(spec, name)}
    out = [required] if required else []
    if taken != required:
        out.append(taken)
    return out


def _value_text(value):
    return pick_tools.kpoint_text(value) if isinstance(value, list) else pick_tools.number(value)


def _assignments(params):
    return ", ".join(f"{name} = {_value_text(value)}" for name, value in params.items())


def _where(values):
    """Where a new calculation is: "at E = 0.3 · k = (...)", "on 3 sites"."""
    at = pick_tools.describe({q: v for q, v in values.items() if q != "sites"})
    sites = values.get("sites") or []
    on = "" if not sites else f"on the site at ({pick_tools.number(sites[0][0])}, " \
        f"{pick_tools.number(sites[0][1])})" if len(sites) == 1 else f"on {len(sites)} sites"
    return " ".join(part for part in (f"at {at}" if at else "", on) if part)


def fermi_term(system):
    """The Fermi-level term of a system (an onsite term of that name), or None."""
    for term in terms_of(system):
        if term.kind == "onsite" and term.name == FERMI_LEVEL:
            return term
    return None


def _shift_then(snapshot, system_id):
    """The mu of the Fermi-level term when the picked result was computed
    (0 without one): the energy picked on it is measured on the spectrum
    that term had already shifted."""
    if snapshot is None:
        return 0.0
    try:
        term = fermi_term(snapshot.system(system_id))
    except Exception:
        return 0.0
    if term is None or not term.enabled or not fields.is_constant(term.params.get("mu")):
        return 0.0
    return float(term.params["mu"])


def snapshot_of(result):
    """The Document a result was computed from, or None."""
    try:
        return Document.from_json(result.document) if result.document else None
    except Exception:
        return None


def targets(document, system_id, values, source=None, mode=None, dimensionality=None,
            snapshot=None):
    """The targets of picked values on a system. source: the calculation
    picked on (it is not moved to a value it holds already, and a sweep
    runs its calculation at the point picked); mode: the system's planned
    Hilbert space (nambu: no Fermi-level target); dimensionality: of its
    geometry, when known (a calculation of two-dimensional systems only is
    not offered on others); snapshot: the Document the picked result was
    computed from (the Fermi level it had)."""
    system = document.system(system_id)
    out = []
    for calc in document.calculations:
        if calc.system != system_id:
            continue
        try:
            spec = registry.get("calculation", calc.kind)
        except registry.RegistryError:
            continue
        if not _fits(spec, dimensionality):
            continue
        # an optional parameter left empty keeps its mode (an LDOS over the mesh stays so)
        changed = {name: value for name, value in _taken(spec, values).items()
                   if calc.params.get(name) != value
                   and not (_optional(spec, name) and calc.params.get(name) is None)}
        if changed:
            out.append({"target": "set", "calculation": calc.id, "params": changed,
                        "label": f"{calc.id} {spec.label}: {_assignments(changed)}"})
    for spec in registry.entries("calculation"):
        if system.kind not in spec.systems or not _fits(spec, dimensionality):
            continue
        for params in _variants(spec, values):
            taken = {p.quantity for p in spec.params if p.name in params}
            where = _where({q: v for q, v in values.items() if q in taken})
            out.append({"target": "add", "system": system_id, "kind": spec.kind,
                        "params": params, "name": where + (f" from {source}" if source else ""),
                        "label": f"new {spec.label} {where}"})
    if values.get("parameter"):
        run = None
        if source is not None:
            calc = next((c for c in document.calculations if c.id == source), None)
            if calc is not None and calc.kind == "sweep" and calc.params.get("calculation"):
                run = calc.params["calculation"]
        label = "set " + ", ".join(pick_tools.parameter_text(t) for t in values["parameter"])
        out.append({"target": "parameter", "set": [dict(t) for t in values["parameter"]],
                    "run": run, "label": label + (f" (and run {run})" if run else "")})
    if "kpoint" in values:
        k = [float(c) for c in values["kpoint"]]
        for calc in document.calculations:
            if calc.system != system_id:
                continue
            try:
                spec = registry.get("calculation", calc.kind)
            except registry.RegistryError:
                continue
            for param in spec.params:
                if not isinstance(param, KPathParam):
                    continue
                current = calc.params.get(param.name)
                text = pick_tools.kpoint_text(k)
                if current is None:
                    kpath, label = ["G", k], f"k-path of {calc.id} from Γ to k = {text}"
                else:
                    kpath, label = list(current) + [k], f"add k = {text} to the k-path of {calc.id}"
                out.append({"target": "kpath", "calculation": calc.id, "param": param.name,
                            "kpath": kpath, "label": label})
    if values.get("sites"):
        sites = [list(p) for p in values["sites"]]
        many = f"the {len(sites)} sites" if len(sites) > 1 else "the site"
        out.append({"target": "select_sites", "system": system_id, "positions": sites,
                    "label": f"select {many} on the Structure tab"})
        out.append({"target": "region", "system": system_id, "positions": sites,
                    "label": f"a region of {many}"})
    if "energy" in values and system.kind == "quantum" and mode != "nambu":
        energy = float(values["energy"])
        term = fermi_term(system)
        mu = _shift_then(snapshot, system_id) - energy
        out.append({"target": "fermi_level", "system": system_id,
                    "term": term.id if term is not None else None, "mu": mu,
                    "label": f"Fermi level to E = {pick_tools.number(energy)} "
                             f"({'update' if term is not None else 'add'} the onsite term "
                             f"{FERMI_LEVEL!r}, mu = {pick_tools.number(mu)})"})
    return out
