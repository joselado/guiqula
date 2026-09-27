"""Registry entries: one declaration per lattice, geometry op, term or
calculation (PLAN.md 3.2). Everything else (forms, validation, the engine
step, the exported script line, tooltips) is derived from it.

Most entries are a declarative ``Call``: the name of the pyqula call and
which parameters go where. The engine and the script exporter both read the
same Call, so the GUI cannot compute something different from the script it
exports. Entries that need more give ``apply`` and ``script`` functions
instead, and their engine test plus the script-reproduction test keep the
two in step.

No pyqula import happens here (the UI imports the registry, PLAN.md 13.15).
"""
from dataclasses import dataclass, field
from typing import Any, Callable

from guiqula.registry.params import Param, ParamError, SeedParam

FAMILIES = ("lattice", "geometry_op", "term", "meanfield", "model", "calculation")
CATALOGUE = {family: {} for family in FAMILIES}


class RegistryError(KeyError):
    pass


class _Marker:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


H = _Marker("h")   # the Hamiltonian being built
G = _Marker("g")   # the geometry being built


class Call:
    """``Call("h.add_zeeman", "m")`` or ``Call("disorder.anderson", H, w="w")``.

    target: ``h.<method>``, ``g.<method>`` or ``<pyqula module>.<function>``.
    Positional and keyword arguments name parameters of the entry; the
    markers H and G pass the object being built.
    """

    def __init__(self, target, *args, **kwargs):
        self.target = target
        self.args = args
        self.kwargs = kwargs
        head = target.split(".")[0]
        self.module = None if head in ("h", "g") else target.rsplit(".", 1)[0]

    def __repr__(self):
        return f"Call({self.target!r}, {self.args}, {self.kwargs})"


@dataclass
class EntrySpec:
    family: str
    kind: str
    label: str
    params: tuple = ()
    group: str = ""
    doc: str = ""
    formula: str = ""
    requires: tuple | Callable = ()  # "spin", "nambu": Hilbert space the entry needs, or a
                                     # callable of the parameters (a Python term's choice)
    systems: tuple = ("quantum",)
    call: Call | None = None
    apply: Callable | None = None    # custom: (target, ctx) -> result
    script: Callable | None = None   # custom: (ctx) -> list of source lines
    plot: dict | None = None         # calculations: plot kind and array mapping
    cost: Callable | None = None     # calculations: (params, size) -> seconds (registry/cost.py)
    modules: tuple = ()              # pyqula modules a custom script uses ("disorder")
    preamble: tuple = ()             # lines an exported script runs once, after its imports
    helpers: tuple = ()              # functions a custom script calls, whose source the
                                     # exported script defines (core.nearest.nearest_site)
    regions: bool = True             # terms: whether a region may restrict it (a factor may not)
    runs_code: bool = False          # a Python node: runs only in a trusted document (13.7)
    document_level: bool = False     # a sweep: apply(document, ctx, run) runs other calculations
    guide: tuple = ()                # sections of pyqula's user guide on it (in-app help, 13.13);
                                     # "guiqula: <heading>" names one of guiqula's own guide
    pyqula: tuple = ()               # the pyqula calls behind a custom entry, whose docstrings
                                     # the help shows (a Call's target is known already)
    plugin: str = ""                 # the distribution of the plugin that registered it
                                     # (registry/plugins.py); "" for guiqula's own
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.family not in FAMILIES:
            raise RegistryError(f"unknown family {self.family!r}")
        if (self.call is None) == (self.apply is None):
            raise RegistryError(f"{self.kind}: give either call or apply")
        if self.apply is not None and self.script is None:
            raise RegistryError(f"{self.kind}: a custom apply needs a custom script")
        names = [p.name for p in self.params]
        if len(set(names)) != len(names):
            raise RegistryError(f"{self.kind}: duplicate parameter names")

    def requires_of(self, params):
        """The Hilbert space the entry needs with these parameters."""
        return tuple(self.requires(params)) if callable(self.requires) else tuple(self.requires)

    @property
    def param_map(self):
        return {p.name: p for p in self.params}

    @property
    def seed_param(self):
        for p in self.params:
            if isinstance(p, SeedParam):
                return p
        return None

    def normalize_params(self, params):
        """Full parameter dict: defaults filled in, values checked.
        Raises ParamError."""
        params = dict(params or {})
        known = self.param_map
        unknown = sorted(set(params) - set(known))
        if unknown:
            raise ParamError(f"{self.kind} has no parameter(s) {unknown}; "
                             f"it has {list(known)}")
        return {name: p.normalize(params.get(name, p.default)) for name, p in known.items()}

    def describe(self):
        return {"family": self.family, "kind": self.kind, "label": self.label,
                "group": self.group, "doc": self.doc, "formula": self.formula,
                "guide": list(self.guide), "pyqula": list(self.pyqula),
                "requires": "per parameters" if callable(self.requires) else list(self.requires),
                "systems": list(self.systems), "runs_code": self.runs_code,
                "plugin": self.plugin, "params": [p.describe() for p in self.params]}


_plugin = None     # the plugin being loaded, whose name register() gives its entries


def _tagging(name):
    global _plugin
    _plugin = name


def register(spec):
    table = CATALOGUE[spec.family]
    if spec.kind in table:
        raise RegistryError(f"{spec.family} {spec.kind!r} registered twice")
    if _plugin is not None and not spec.plugin:
        spec.plugin = _plugin
    table[spec.kind] = spec
    return spec


def get(family, kind):
    _load_builtins()
    try:
        return CATALOGUE[family][kind]
    except KeyError:
        known = sorted(CATALOGUE.get(family, {}))
        raise RegistryError(f"unknown {family} {kind!r}; known: {known}") from None


def kinds(family):
    _load_builtins()
    return sorted(CATALOGUE[family])


def entries(family=None):
    _load_builtins()
    families = FAMILIES if family is None else (family,)
    return [spec for f in families for spec in CATALOGUE[f].values()]


_loaded = False


def _load_builtins():
    """guiqula's own entries, then the plugins' (registry/plugins.py)."""
    global _loaded
    if not _loaded:
        _loaded = True
        from guiqula.registry import (calculations, classical, geometry_ops,  # noqa: F401
                                      lattices, meanfield, python_nodes, sweeps, terms)
        from guiqula.registry import plugins
        plugins.load(CATALOGUE, _tagging)


ALL_SYSTEMS = ("quantum", "classical_spin", "lattice_gas", "ising")


def entry(family, kind, label, *params, **meta):
    """Declare and register an entry; returns the spec. Lattices and
    geometry ops apply to every kind of system unless they say otherwise; a
    lattice's help is the guide's section on making a geometry and a
    Hamiltonian unless it names another."""
    if family in ("lattice", "geometry_op"):
        meta.setdefault("systems", ALL_SYSTEMS)
    if family == "lattice":
        meta.setdefault("guide", ("Setting up a Hamiltonian",))
    return register(EntrySpec(family=family, kind=kind, label=label, params=tuple(params), **meta))


__all__ = ["Call", "EntrySpec", "G", "H", "Param", "ParamError", "RegistryError",
           "entry", "entries", "get", "kinds", "register"]
