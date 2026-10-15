"""The Document: the whole editable state, as JSON-serializable data
(PLAN.md 3.1). Mutations happen only through guiqula.commands.

A document holds geometries, systems and calculations. A geometry
(``geometries``, ids geo1, geo2..., phase 9, part B) is a base lattice, or
another geometry it starts from (``parent``, a ribbon cut from a decorated
cell), ordered ops, and the regions, named site selections of it; a system
names one by id (``System.geometry``), and several systems may name the same
one, so that one geometry carries several Hamiltonians or a Hamiltonian and
a classical model. A system of kind ``quantum`` has a geometry and a
Hamiltonian (construction, an ordered term stack, and the mean-field block
that turns the terms into a self-consistent interacting Hamiltonian when it
is enabled). A system of one of the classical kinds (``classical_spin``,
``lattice_gas``, ``ising``, decision 13.5) has a geometry too and, in place
of the Hamiltonian, a ``model``: the classical model
built on the geometry (its kind names a registry entry of the "model"
family, whose parameters set it up: the filling, the initial
magnetization, the seed of the random initial configuration) and its
term stack. Entry ids are unique across the document, so a command can
name any entry by id alone; terms_of(system) is a system's term stack,
whatever its kind.

An embedding (``embeddings``, ids e1, e2...) names two quantum systems of
the document, the pristine crystal and the defect, each an ordinary system
edited as any other; it has no stack of its own, and a calculation may run
on it as it runs on a system (``Calculation.system`` names either). The two
must share their cell: pyqula's Embedding takes the pristine Hamiltonian and
only the intracell matrix of the defective one. The list is left out of the
JSON while it is empty, so a document without embeddings reads as before.

A junction (``junctions``, ids j1, j2..., phase 9, part D) is a two-terminal
transport device in pyqula's sense: two semi-infinite leads, the left and
the right one (one-dimensional quantum systems), and an optional central
region between them, a finite system contacted at two of its sites or a
one-dimensional one; a calculation may run on it as on a system or an
embedding. Left out of the JSON while empty, as the embeddings.

A k-path (``kpaths``, ids k1, k2...) is a path through the Brillouin zone
that calculations share (phase 9, part A): its vertices, each a label pyqula
knows or reduced coordinates, and no vertex at all for pyqula's default path
of the geometry it is walked on. A calculation that walks one names it by id
in its parameters; the planner resolves the id into the vertices, so the
key of a result hashes the path and never the id. The list is left out of
the JSON while it is empty. A document written before k-paths were objects
carried the vertices in each calculation (None for the default path);
reading it lifts them (lift_kpaths).

Parameters are stored as plain JSON (``params``); their meaning and
validation belong to the registry entry named by ``kind``. An entry whose
kind a plugin provides records that plugin (``plugin``), so a document
opened without it says which one is missing. An op, a term or a
calculation may have a ``name`` (a pick names what it adds after where it
came from: "at E = 0.3 from c1", the "Fermi level" term); the keys hash
kinds and parameters only, so a name never makes a result stale.
"""
import json
import math
import re
from typing import Any, Literal

from pydantic import (BaseModel, ConfigDict, Field, field_validator, model_serializer,
                      model_validator)

from guiqula.core import fields as field_tools

SCHEMA_VERSION = 2                 # 2: geometries of their own (version 1 is lifted)
# a JSON string, which is left as it is (the characters of a value never
# change: "[1,2]" in a note or in a Python node's code stays so), or a JSON
# list spread over lines whose items are numbers, strings without commas or
# brackets, true/false/null (group 1: its items)
_LEAF = r'-?[\d.eE+-]+|"(?:[^"\\,\[\]{}]|\\.)*"|true|false|null'
_LEAF_LIST = re.compile(rf'"(?:[^"\\]|\\.)*"|\[\s*((?:{_LEAF})(?:\s*,\s*(?:{_LEAF}))*)\s*\]')
SYSTEM_KINDS = ("quantum", "classical_spin", "lattice_gas", "ising")
CLASSICAL_KINDS = SYSTEM_KINDS[1:]

ID_PREFIX = {"geometry": "geo", "system": "s", "op": "op", "term": "t", "region": "r", "calculation": "c",
             "embedding": "e", "kpath": "k", "junction": "j"}


class DocumentError(ValueError):
    """A document is inconsistent (dangling reference, duplicate id, ...)."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class _Kind(_Model):
    """Something whose kind names a registry entry. plugin: the plugin
    that provided the kind when it was added (phase-6 answer 37),
    "distribution==version", or "plugins/<file>.py" for the user's plugins
    folder; "" for guiqula's own, and then left out of the JSON, so that a
    document without plugins is written as before. The name of an entry
    or a calculation is left out when empty in the same way (phase 7)."""
    plugin: str = ""

    @model_serializer(mode="wrap")
    def _without_empty_plugin(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            for key in ("plugin", "name"):
                if key in data and not data[key]:
                    del data[key]
        return data


class Base(_Kind):
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


class Entry(_Kind):
    """A geometry op or a Hamiltonian term."""
    id: str
    kind: str
    name: str = ""                 # what it is for ("Fermi level"); "" is left out of the JSON
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)
    region: str | None = None      # terms only: restrict to this region


class Region(_Model):
    id: str
    name: str = ""
    select: dict[str, Any]


class Geometry(_Model):
    """A geometry of the document: a base lattice, or the geometry it starts
    from (parent, by id; exactly one of the two), its ops in order, and its
    regions. The systems that name it share it: an op or a region edited
    once is edited for all of them."""
    id: str
    name: str = ""
    base: Base | None = None
    parent: str | None = None
    ops: list[Entry] = Field(default_factory=list)
    regions: list[Region] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _without_empty_fields(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            for key in ("name", "parent", "base"):
                if key in data and not data[key]:
                    del data[key]
        return data


class Construction(_Model):
    has_spin: bool = True          # requested; the engine may upgrade (PLAN.md 3.1)
    nambu: bool = False            # requested; idem
    tij: list[float] = Field(default_factory=lambda: [1.0])
    is_sparse: bool = False

    @field_validator("tij")
    @classmethod
    def _finite_hoppings(cls, tij):
        """nan or inf would break every key of the system (JSON has neither)
        and be saved as a bare NaN."""
        for t in tij:
            if not math.isfinite(t):
                raise ValueError(f"the neighbour hoppings must be finite numbers, not {t}")
        return tij


class MeanField(_Kind):
    """Interactions solved at the mean-field level after the term stack
    (PLAN.md section 5); kind names a registry entry of the "meanfield"
    family, whose declaration checks params."""
    enabled: bool = False
    kind: str = "interactions"
    params: dict[str, Any] = Field(default_factory=dict)


class Hamiltonian(_Model):
    construction: Construction = Field(default_factory=Construction)
    terms: list[Entry] = Field(default_factory=list)
    meanfield: MeanField = Field(default_factory=MeanField)


class Model(_Kind):
    """A classical system's model (decision 13.5): kind names a registry
    entry of the "model" family (the same name as the system's kind),
    whose params set the model up; terms is its stack."""
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    terms: list[Entry] = Field(default_factory=list)


class System(_Model):
    id: str
    name: str = ""
    kind: Literal["quantum", "classical_spin", "lattice_gas", "ising"] = "quantum"
    geometry: str                  # the id of its geometry
    hamiltonian: Hamiltonian | None = Field(default_factory=Hamiltonian)
    model: Model | None = None
    variant_of: str | None = None  # a variant: the original's Hamiltonian or model, on
                                   # this geometry (left out of the JSON when None)

    @model_validator(mode="before")
    @classmethod
    def _classical_has_no_hamiltonian(cls, data):
        """A classical system, or a variant, written without a hamiltonian has
        none (the field's default is a Hamiltonian, for the quantum systems)."""
        if isinstance(data, dict) and (data.get("kind") in CLASSICAL_KINDS
                                       or data.get("variant_of")) \
                and "hamiltonian" not in data:
            data = dict(data, hamiltonian=None)
        return data

    @model_serializer(mode="wrap")
    def _without_empty_variant(self, handler):
        data = handler(self)
        if isinstance(data, dict) and not data.get("variant_of"):
            data.pop("variant_of", None)
        if isinstance(data, dict) and data.get("variant_of"):
            data.pop("hamiltonian", None)       # the original's
            data.pop("model", None)
        return data


class Embedding(_Model):
    """A defect in an otherwise infinite crystal: the pristine system and the
    defective one, by id (both quantum, with the same cell)."""
    id: str
    name: str = ""
    pristine: str
    defect: str

    @model_serializer(mode="wrap")
    def _without_empty_name(self, handler):
        data = handler(self)
        if isinstance(data, dict) and not data.get("name"):
            data.pop("name", None)
        return data


class Junction(_Model):
    """Two semi-infinite leads and an optional central region, by the ids of
    quantum systems of the document."""
    id: str
    name: str = ""
    left: str
    right: str
    central: str | None = None

    @model_serializer(mode="wrap")
    def _without_empty_fields(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            for key in ("name", "central"):
                if key in data and not data[key]:
                    del data[key]
        return data


class KPath(_Model):
    """A path through the Brillouin zone, shared by the calculations that
    name it: its vertices (labels or [k1, k2, k3] in reciprocal lattice
    units, checked by registry.params.normalize_vertices); none, pyqula's
    default path."""
    id: str
    name: str = ""
    vertices: list[Any] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _without_empty_name(self, handler):
        data = handler(self)
        if isinstance(data, dict) and not data.get("name"):
            data.pop("name", None)
        return data


class Calculation(_Kind):
    id: str
    system: str
    kind: str
    name: str = ""                 # where it came from ("at E = 0.3 from c1"); "" is left out
    params: dict[str, Any] = Field(default_factory=dict)
    variant_of: str | None = None  # a variant: the original's parameters, on its own system

    @model_serializer(mode="wrap")
    def _without_empty_fields(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            for key in ("plugin", "name", "variant_of"):
                if key in data and not data[key]:
                    del data[key]
            if data.get("variant_of"):
                data.pop("params", None)        # the original's
        return data


class Document(_Model):
    version: int = SCHEMA_VERSION
    notes: str = ""                # what the document is about (the presets gallery shows it)
    locks: list[str] = Field(default_factory=list)   # what a teacher locked (core/locks.py)
    geometries: list[Geometry] = Field(default_factory=list)
    systems: list[System] = Field(default_factory=list)
    embeddings: list[Embedding] = Field(default_factory=list)
    junctions: list[Junction] = Field(default_factory=list)
    calculations: list[Calculation] = Field(default_factory=list)
    kpaths: list[KPath] = Field(default_factory=list)
    ui: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _kpaths_lifted(self):
        """A document made or read with k-paths inside its calculations names
        k-paths of its own instead (lift_kpaths)."""
        lift_kpaths(self)
        return self

    @model_serializer(mode="wrap")
    def _without_empty_lists(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            for key in ("embeddings", "junctions", "kpaths"):
                if not data.get(key, True):
                    del data[key]
        return data

    # ---- serialization
    def to_json(self, indent=2):
        """Indented JSON with short lists of scalars kept on one line, so
        that presets and projects diff well in git. Only the layout between
        values changes: the worker keys the Document it reads from this
        text, which must be the Document the window keys."""
        text = json.dumps(self.model_dump(mode="json"), indent=indent)
        return _LEAF_LIST.sub(lambda m: m.group(0) if m.group(1) is None else "[" + ", ".join(
            part.strip() for part in m.group(1).split(",")) + "]", text)

    @classmethod
    def from_json(cls, text):
        return cls.from_data(json.loads(text))

    @classmethod
    def from_data(cls, data):
        if not isinstance(data, dict):
            raise DocumentError("a document is a JSON object")
        version = data.get("version", SCHEMA_VERSION)
        inline = any(isinstance(s, dict) and isinstance(s.get("geometry"), dict)
                     for s in data.get("systems") or [])
        if version == 1 or (inline and "version" not in data):     # written before part B
            data = lift_geometries(data)
            version = SCHEMA_VERSION
        if version != SCHEMA_VERSION:
            raise DocumentError(f"document schema version {version} is not supported "
                                f"(this guiqula reads version {SCHEMA_VERSION})")
        document = cls.model_validate(data)
        check(document)
        return document

    def copy_deep(self):
        return self.model_copy(deep=True)

    # ---- lookup
    def system(self, system_id):
        for system in self.systems:
            if system.id == system_id:
                return system
        raise DocumentError(f"no system {system_id!r}")

    def embedding(self, embedding_id):
        for embedding in self.embeddings:
            if embedding.id == embedding_id:
                return embedding
        raise DocumentError(f"no embedding {embedding_id!r}")

    def target_kind(self, target_id):
        """The kind of what a calculation may run on: a system's kind, or
        "embedding"."""
        for embedding in self.embeddings:
            if embedding.id == target_id:
                return "embedding"
        for junction in self.junctions:
            if junction.id == target_id:
                return "junction"
        return self.system(target_id).kind

    def junction(self, junction_id):
        for junction in self.junctions:
            if junction.id == junction_id:
                return junction
        raise DocumentError(f"no junction {junction_id!r}")

    def junctions_of(self, system_id):
        """The junctions that name a system (as a lead or the central region)."""
        return [j for j in self.junctions if system_id in (j.left, j.right, j.central)]

    def embeddings_of(self, system_id):
        """The embeddings that name a system (as pristine or defect)."""
        return [e for e in self.embeddings if system_id in (e.pristine, e.defect)]

    def calculation(self, calc_id):
        for calc in self.calculations:
            if calc.id == calc_id:
                return calc
        raise DocumentError(f"no calculation {calc_id!r}")

    def geometry(self, geometry_id):
        for geometry in self.geometries:
            if geometry.id == geometry_id:
                return geometry
        raise DocumentError(f"no geometry {geometry_id!r}")

    def geometry_of(self, system_id):
        """The geometry a system names (its object)."""
        return self.geometry(self.system(system_id).geometry)

    def systems_on(self, geometry_id):
        """The ids of the systems that name a geometry, in document order."""
        return [s.id for s in self.systems if s.geometry == geometry_id]

    def kpath(self, kpath_id):
        for kpath in self.kpaths:
            if kpath.id == kpath_id:
                return kpath
        raise DocumentError(f"no k-path {kpath_id!r}")

    def find(self, entry_id):
        """Locate any entry by id: returns (family, owner or None, containing
        list, index, object). family is one of "geometry", "op", "region"
        (whose owner is their geometry), "system", "term" (whose owner is its
        system), "embedding", "junction", "calculation", "kpath"."""
        for i, geometry in enumerate(self.geometries):
            if geometry.id == entry_id:
                return "geometry", None, self.geometries, i, geometry
            for j, op in enumerate(geometry.ops):
                if op.id == entry_id:
                    return "op", geometry, geometry.ops, j, op
            for j, region in enumerate(geometry.regions):
                if region.id == entry_id:
                    return "region", geometry, geometry.regions, j, region
        for i, system in enumerate(self.systems):
            if system.id == entry_id:
                return "system", None, self.systems, i, system
            terms = terms_of(system)
            for j, term in enumerate(terms):
                if term.id == entry_id:
                    return "term", system, terms, j, term
        for i, embedding in enumerate(self.embeddings):
            if embedding.id == entry_id:
                return "embedding", None, self.embeddings, i, embedding
        for i, junction in enumerate(self.junctions):
            if junction.id == entry_id:
                return "junction", None, self.junctions, i, junction
        for i, calc in enumerate(self.calculations):
            if calc.id == entry_id:
                return "calculation", None, self.calculations, i, calc
        for i, kpath in enumerate(self.kpaths):
            if kpath.id == entry_id:
                return "kpath", None, self.kpaths, i, kpath
        raise DocumentError(f"no entry {entry_id!r}")

    def plugins(self):
        """The plugins its entries record (sorted, without repeats)."""
        found = set()
        for geometry in self.geometries:
            if geometry.base is not None:
                found.add(geometry.base.plugin)
            found.update(op.plugin for op in geometry.ops)
        for system in self.systems:
            found.update(term.plugin for term in terms_of(system))
            if system.hamiltonian is not None:
                found.add(system.hamiltonian.meanfield.plugin)
            if system.model is not None:
                found.add(system.model.plugin)
        found.update(calc.plugin for calc in self.calculations)
        return sorted(found - {""})

    def all_ids(self):
        ids = []
        for geometry in self.geometries:
            ids.append(geometry.id)
            ids += [op.id for op in geometry.ops]
            ids += [region.id for region in geometry.regions]
        for system in self.systems:
            ids.append(system.id)
            ids += [term.id for term in terms_of(system)]
        ids += [embedding.id for embedding in self.embeddings]
        ids += [junction.id for junction in self.junctions]
        ids += [calc.id for calc in self.calculations]
        ids += [kpath.id for kpath in self.kpaths]
        return ids

    def new_id(self, family):
        """Next free id for a family: s3, op2, t5, r1, c4, k2 (deterministic)."""
        prefix = ID_PREFIX[family]
        pattern = re.compile(rf"^{prefix}(\d+)$")
        used = [int(m.group(1)) for m in map(pattern.match, self.all_ids()) if m]
        return f"{prefix}{max(used, default=0) + 1}"


def kpath_params(calc):
    """The names of a calculation's parameters that are k-paths (its
    registry entry's KPathParams); none for a kind the registry does not
    know (a missing plugin)."""
    from guiqula.registry import base as registry
    from guiqula.registry.params import KPathParam
    try:
        spec = registry.get("calculation", calc.kind)
    except registry.RegistryError:
        return []
    return [p.name for p in spec.params if isinstance(p, KPathParam)]


def kpath_users(document, kpath_id):
    """The ids of the calculations that walk a k-path."""
    return [c.id for c in document.calculations
            if any(c.params.get(name) == kpath_id for name in kpath_params(c))]


def lift_kpaths(document):
    """Turn the k-paths a document of before phase 9 carries inside its
    calculations into k-paths of the document: an inline path becomes a
    k-path of its own, named after its calculation, and the calculations of
    one system on pyqula's default path share one empty k-path. A document
    whose calculations already name k-paths is left as it is, so reading
    one twice gives the same document."""
    from guiqula.registry.params import ParamError, normalize_vertices
    shared = {}                    # system id: its empty k-path
    for calc in document.calculations:
        for name in kpath_params(calc):
            value = calc.params.get(name)
            if isinstance(value, str):
                continue
            if value is None:
                if calc.system not in shared:
                    shared[calc.system] = KPath(id=document.new_id("kpath"))
                    document.kpaths.append(shared[calc.system])
                calc.params = dict(calc.params, **{name: shared[calc.system].id})
                continue
            try:
                vertices = normalize_vertices(name, value)
            except ParamError:
                continue                # left for the planner to flag
            kpath = KPath(id=document.new_id("kpath"), name=calc.name or calc.id,
                          vertices=vertices)
            document.kpaths.append(kpath)
            calc.params = dict(calc.params, **{name: kpath.id})


def source_of(document, entry):
    """The original a variant follows (a system's Hamiltonian or model, a
    calculation's parameters), or the entry itself."""
    original = getattr(entry, "variant_of", None)
    if original is None:
        return entry
    family = "system" if isinstance(entry, System) else "calculation"
    return getattr(document, family)(original)


def variants_of(document, entry_id):
    """The ids of the variants of a system or a calculation, in order."""
    return [x.id for x in list(document.systems) + list(document.calculations)
            if x.variant_of == entry_id]


def terms_of(system):
    """A system's term stack: its Hamiltonian's, or its classical model's
    (the list itself, so a mutation can change it)."""
    if system.hamiltonian is not None:
        return system.hamiltonian.terms
    if system.model is not None:
        return system.model.terms
    return []


def region_users(system):
    """(owner, params) of everything in a system whose parameters can name
    regions (piecewise Fields): the terms, then the mean field."""
    users = [(term.id, term.params) for term in terms_of(system)]
    if system.hamiltonian is not None:
        users.append((f"{system.id}/meanfield", system.hamiltonian.meanfield.params))
    return users


def lift_geometries(data):
    """A document of schema version 1 (each system with its geometry and
    regions inline) as version 2: one geometry per system, geo1, geo2... in
    the order of the systems, holding its base, ops and regions with their
    ids, so nothing is shared until it is asked for. data: the JSON object;
    returns a new one."""
    import copy
    data = copy.deepcopy(data)
    geometries = []
    for system in data.get("systems", []):
        if not isinstance(system, dict) or not isinstance(system.get("geometry"), dict):
            continue
        inline = system["geometry"]
        geometry = {"id": f"geo{len(geometries) + 1}", **inline,
                    "regions": system.pop("regions", [])}
        geometries.append(geometry)
        system["geometry"] = geometry["id"]
    data["geometries"] = geometries + list(data.get("geometries", []))
    data["version"] = SCHEMA_VERSION
    return data


def geometry_chain(document, geometry_id):
    """The geometries a geometry is made from, the one with the base lattice
    first and geometry_id last; raises DocumentError on a cycle or a parent
    that is not there."""
    chain = []
    current = geometry_id
    while current is not None:
        if current in chain:
            raise DocumentError(f"geometry {geometry_id!r} starts from itself "
                                f"({' <- '.join(chain + [current])})")
        chain.append(current)
        current = document.geometry(current).parent
    return [document.geometry(g) for g in reversed(chain)]


def check(document):
    """Raise DocumentError on duplicate ids or dangling references."""
    ids = document.all_ids()
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise DocumentError(f"duplicate ids: {duplicates}")
    geometries = {g.id: g for g in document.geometries}
    for geometry in document.geometries:
        if (geometry.base is None) == (geometry.parent is None):
            raise DocumentError(f"geometry {geometry.id!r} starts from a lattice or from "
                                f"another geometry, one of the two")
        if geometry.parent is not None and geometry.parent not in geometries:
            raise DocumentError(f"geometry {geometry.id!r} starts from missing geometry "
                                f"{geometry.parent!r}")
        geometry_chain(document, geometry.id)
        for op in geometry.ops:
            if op.region is not None:
                raise DocumentError(f"geometry op {op.id!r} cannot carry a region")
    systems = {s.id: s for s in document.systems}
    for system in document.systems:
        if system.geometry not in geometries:
            raise DocumentError(f"system {system.id!r} names missing geometry "
                                f"{system.geometry!r}")
        if system.variant_of is not None:
            original = systems.get(system.variant_of)
            if original is None or original.variant_of is not None or original.kind != system.kind:
                raise DocumentError(f"system {system.id!r} is a variant of {system.variant_of!r}, "
                                    f"which is not an original system of its kind")
            if system.hamiltonian is not None or system.model is not None:
                raise DocumentError(f"system {system.id!r} is a variant: its Hamiltonian or "
                                    f"model is its original's")
            continue
        if system.kind == "quantum" and (system.hamiltonian is None or system.model is not None):
            raise DocumentError(f"quantum system {system.id!r} needs a hamiltonian and no model")
        if system.kind in CLASSICAL_KINDS and (system.model is None
                                               or system.hamiltonian is not None):
            raise DocumentError(f"{system.kind} system {system.id!r} needs a model and no "
                                f"hamiltonian")
        if system.model is not None and system.model.kind != system.kind:
            raise DocumentError(f"system {system.id!r} is {system.kind} but its model is "
                                f"{system.model.kind}")
        regions = {r.id for r in geometries[system.geometry].regions}
        for term in terms_of(system):
            if term.region is not None and term.region not in regions:
                raise DocumentError(f"term {term.id!r} refers to region {term.region!r}, "
                                    f"which the geometry of {system.id!r} does not have")
        for owner, params in region_users(system):
            missing = [r for r in field_tools.regions_of(list(params.values()))
                       if r not in regions]
            if missing:
                raise DocumentError(f"{owner} has a piecewise Field over region "
                                    f"{missing[0]!r}, which the geometry of {system.id!r} "
                                    f"does not have")
    for embedding in document.embeddings:
        for role in ("pristine", "defect"):
            target = getattr(embedding, role)
            if target not in systems:
                raise DocumentError(f"embedding {embedding.id!r} names missing system "
                                    f"{target!r} as its {role} one")
    for junction in document.junctions:
        for role in ("left", "right", "central"):
            target = getattr(junction, role)
            if target is not None and target not in systems:
                raise DocumentError(f"junction {junction.id!r} names missing system "
                                    f"{target!r} as its {role} one")
    embeddings = {e.id for e in document.embeddings} | {j.id for j in document.junctions}
    calcs = {c.id: c for c in document.calculations}
    for calc in document.calculations:
        if calc.system not in systems and calc.system not in embeddings:
            raise DocumentError(f"calculation {calc.id!r} refers to missing system {calc.system!r}")
        if calc.variant_of is not None:
            original = calcs.get(calc.variant_of)
            if original is None or original.variant_of is not None or original.kind != calc.kind:
                raise DocumentError(f"calculation {calc.id!r} is a variant of "
                                    f"{calc.variant_of!r}, which is not an original calculation "
                                    f"of its kind")
