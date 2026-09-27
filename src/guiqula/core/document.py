"""The Document: the whole editable state, as JSON-serializable data
(PLAN.md 3.1). Mutations happen only through guiqula.commands.

A document holds systems and calculations. A system of kind ``quantum`` has
a geometry stack (a base lattice and ordered ops), regions, and a
Hamiltonian (construction, an ordered term stack, and the mean-field block
that turns the terms into a self-consistent interacting Hamiltonian when it
is enabled). A system of one of the classical kinds (``classical_spin``,
``lattice_gas``, ``ising``, decision 13.5) has the same geometry stack and
regions and, in place of the Hamiltonian, a ``model``: the classical model
built on the geometry (its kind names a registry entry of the "model"
family, whose parameters set it up: the filling, the initial
magnetization, the seed of the random initial configuration) and its
term stack. Entry ids are unique across the document, so a command can
name any entry by id alone; terms_of(system) is a system's term stack,
whatever its kind.

Parameters are stored as plain JSON (``params``); their meaning and
validation belong to the registry entry named by ``kind``. An entry whose
kind a plugin provides records that plugin (``plugin``), so a document
opened without it says which one is missing.
"""
import json
import math
import re
from typing import Any, Literal

from pydantic import (BaseModel, ConfigDict, Field, field_validator, model_serializer,
                      model_validator)

from guiqula.core import fields as field_tools

SCHEMA_VERSION = 1
# a JSON string, which is left as it is (the characters of a value never
# change: "[1,2]" in a note or in a Python node's code stays so), or a JSON
# list spread over lines whose items are numbers, strings without commas or
# brackets, true/false/null (group 1: its items)
_LEAF = r'-?[\d.eE+-]+|"(?:[^"\\,\[\]{}]|\\.)*"|true|false|null'
_LEAF_LIST = re.compile(rf'"(?:[^"\\]|\\.)*"|\[\s*((?:{_LEAF})(?:\s*,\s*(?:{_LEAF}))*)\s*\]')
SYSTEM_KINDS = ("quantum", "classical_spin", "lattice_gas", "ising")
CLASSICAL_KINDS = SYSTEM_KINDS[1:]

ID_PREFIX = {"system": "s", "op": "op", "term": "t", "region": "r", "calculation": "c"}


class DocumentError(ValueError):
    """A document is inconsistent (dangling reference, duplicate id, ...)."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class _Kind(_Model):
    """Something whose kind names a registry entry. plugin: the plugin
    that provided the kind when it was added (phase-6 answer 37),
    "distribution==version", or "plugins/<file>.py" for the user's plugins
    folder; "" for guiqula's own, and then left out of the JSON, so that a
    document without plugins is written as before."""
    plugin: str = ""

    @model_serializer(mode="wrap")
    def _without_empty_plugin(self, handler):
        data = handler(self)
        if isinstance(data, dict) and not data.get("plugin"):
            data.pop("plugin", None)
        return data


class Base(_Kind):
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


class Entry(_Kind):
    """A geometry op or a Hamiltonian term."""
    id: str
    kind: str
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)
    region: str | None = None      # terms only: restrict to this region


class Geometry(_Model):
    base: Base
    ops: list[Entry] = Field(default_factory=list)


class Region(_Model):
    id: str
    name: str = ""
    select: dict[str, Any]


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
    geometry: Geometry
    regions: list[Region] = Field(default_factory=list)
    hamiltonian: Hamiltonian | None = Field(default_factory=Hamiltonian)
    model: Model | None = None

    @model_validator(mode="before")
    @classmethod
    def _classical_has_no_hamiltonian(cls, data):
        """A classical system written without a hamiltonian has none (the
        field's default is a Hamiltonian, for the quantum systems)."""
        if isinstance(data, dict) and data.get("kind") in CLASSICAL_KINDS \
                and "hamiltonian" not in data:
            data = dict(data, hamiltonian=None)
        return data


class Calculation(_Kind):
    id: str
    system: str
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


class Document(_Model):
    version: int = SCHEMA_VERSION
    notes: str = ""                # what the document is about (the presets gallery shows it)
    locks: list[str] = Field(default_factory=list)   # what a teacher locked (core/locks.py)
    systems: list[System] = Field(default_factory=list)
    calculations: list[Calculation] = Field(default_factory=list)
    ui: dict[str, Any] = Field(default_factory=dict)

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

    def calculation(self, calc_id):
        for calc in self.calculations:
            if calc.id == calc_id:
                return calc
        raise DocumentError(f"no calculation {calc_id!r}")

    def find(self, entry_id):
        """Locate any entry by id: returns (family, owner system or None,
        containing list, index, object). family is one of "system", "op",
        "term", "region", "calculation"."""
        for i, system in enumerate(self.systems):
            if system.id == entry_id:
                return "system", None, self.systems, i, system
            for j, op in enumerate(system.geometry.ops):
                if op.id == entry_id:
                    return "op", system, system.geometry.ops, j, op
            for j, region in enumerate(system.regions):
                if region.id == entry_id:
                    return "region", system, system.regions, j, region
            terms = terms_of(system)
            for j, term in enumerate(terms):
                if term.id == entry_id:
                    return "term", system, terms, j, term
        for i, calc in enumerate(self.calculations):
            if calc.id == entry_id:
                return "calculation", None, self.calculations, i, calc
        raise DocumentError(f"no entry {entry_id!r}")

    def plugins(self):
        """The plugins its entries record (sorted, without repeats)."""
        found = set()
        for system in self.systems:
            found.add(system.geometry.base.plugin)
            found.update(op.plugin for op in system.geometry.ops)
            found.update(term.plugin for term in terms_of(system))
            if system.hamiltonian is not None:
                found.add(system.hamiltonian.meanfield.plugin)
            if system.model is not None:
                found.add(system.model.plugin)
        found.update(calc.plugin for calc in self.calculations)
        return sorted(found - {""})

    def all_ids(self):
        ids = []
        for system in self.systems:
            ids.append(system.id)
            ids += [op.id for op in system.geometry.ops]
            ids += [region.id for region in system.regions]
            ids += [term.id for term in terms_of(system)]
        ids += [calc.id for calc in self.calculations]
        return ids

    def new_id(self, family):
        """Next free id for a family: s3, op2, t5, r1, c4 (deterministic)."""
        prefix = ID_PREFIX[family]
        pattern = re.compile(rf"^{prefix}(\d+)$")
        used = [int(m.group(1)) for m in map(pattern.match, self.all_ids()) if m]
        return f"{prefix}{max(used, default=0) + 1}"


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


def check(document):
    """Raise DocumentError on duplicate ids or dangling references."""
    ids = document.all_ids()
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise DocumentError(f"duplicate ids: {duplicates}")
    systems = {s.id: s for s in document.systems}
    for system in document.systems:
        if system.kind == "quantum" and (system.hamiltonian is None or system.model is not None):
            raise DocumentError(f"quantum system {system.id!r} needs a hamiltonian and no model")
        if system.kind in CLASSICAL_KINDS and (system.model is None
                                               or system.hamiltonian is not None):
            raise DocumentError(f"{system.kind} system {system.id!r} needs a model and no "
                                f"hamiltonian")
        if system.model is not None and system.model.kind != system.kind:
            raise DocumentError(f"system {system.id!r} is {system.kind} but its model is "
                                f"{system.model.kind}")
        regions = {r.id for r in system.regions}
        for term in terms_of(system):
            if term.region is not None and term.region not in regions:
                raise DocumentError(f"term {term.id!r} refers to region {term.region!r}, "
                                    f"which system {system.id!r} does not have")
        for owner, params in region_users(system):
            missing = [r for r in field_tools.regions_of(list(params.values()))
                       if r not in regions]
            if missing:
                raise DocumentError(f"{owner} has a piecewise Field over region "
                                    f"{missing[0]!r}, which system {system.id!r} does not have")
        for op in system.geometry.ops:
            if op.region is not None:
                raise DocumentError(f"geometry op {op.id!r} cannot carry a region in phase 1")
    for calc in document.calculations:
        if calc.system not in systems:
            raise DocumentError(f"calculation {calc.id!r} refers to missing system {calc.system!r}")
