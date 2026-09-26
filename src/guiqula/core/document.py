"""The Document: the whole editable state, as JSON-serializable data
(PLAN.md 3.1). Mutations happen only through guiqula.commands.

A document holds systems and calculations. A system of kind ``quantum`` has
a geometry stack (a base lattice and ordered ops), regions, and a
Hamiltonian (construction and an ordered term stack). The classical kinds
(``classical_spin``, ``lattice_gas``, ``ising``) are reserved in the schema;
they get their model stack in phase 4. Entry ids are unique across the
document, so a command can name any entry by id alone.

Parameters are stored as plain JSON (``params``); their meaning and
validation belong to the registry entry named by ``kind``.
"""
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1
# a JSON list spread over lines whose items are numbers, strings without
# commas or brackets, true/false/null
_LEAF_LIST = re.compile(r'\[\s*((?:-?[\d.eE+-]+|"[^",\[\]{}]*"|true|false|null)'
                        r'(?:\s*,\s*(?:-?[\d.eE+-]+|"[^",\[\]{}]*"|true|false|null))*)\s*\]')
SYSTEM_KINDS = ("quantum", "classical_spin", "lattice_gas", "ising")

ID_PREFIX = {"system": "s", "op": "op", "term": "t", "region": "r", "calculation": "c"}


class DocumentError(ValueError):
    """A document is inconsistent (dangling reference, duplicate id, ...)."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Base(_Model):
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


class Entry(_Model):
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


class Hamiltonian(_Model):
    construction: Construction = Field(default_factory=Construction)
    terms: list[Entry] = Field(default_factory=list)


class System(_Model):
    id: str
    name: str = ""
    kind: Literal["quantum", "classical_spin", "lattice_gas", "ising"] = "quantum"
    geometry: Geometry
    regions: list[Region] = Field(default_factory=list)
    hamiltonian: Hamiltonian | None = Field(default_factory=Hamiltonian)


class Calculation(_Model):
    id: str
    system: str
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


class Document(_Model):
    version: int = SCHEMA_VERSION
    systems: list[System] = Field(default_factory=list)
    calculations: list[Calculation] = Field(default_factory=list)
    ui: dict[str, Any] = Field(default_factory=dict)

    # ---- serialization
    def to_json(self, indent=2):
        """Indented JSON with short lists of scalars kept on one line, so
        that presets and projects diff well in git."""
        text = json.dumps(self.model_dump(mode="json"), indent=indent)
        return _LEAF_LIST.sub(lambda m: "[" + ", ".join(
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
            if system.hamiltonian is not None:
                for j, term in enumerate(system.hamiltonian.terms):
                    if term.id == entry_id:
                        return "term", system, system.hamiltonian.terms, j, term
        for i, calc in enumerate(self.calculations):
            if calc.id == entry_id:
                return "calculation", None, self.calculations, i, calc
        raise DocumentError(f"no entry {entry_id!r}")

    def all_ids(self):
        ids = []
        for system in self.systems:
            ids.append(system.id)
            ids += [op.id for op in system.geometry.ops]
            ids += [region.id for region in system.regions]
            if system.hamiltonian is not None:
                ids += [term.id for term in system.hamiltonian.terms]
        ids += [calc.id for calc in self.calculations]
        return ids

    def new_id(self, family):
        """Next free id for a family: s3, op2, t5, r1, c4 (deterministic)."""
        prefix = ID_PREFIX[family]
        pattern = re.compile(rf"^{prefix}(\d+)$")
        used = [int(m.group(1)) for m in map(pattern.match, self.all_ids()) if m]
        return f"{prefix}{max(used, default=0) + 1}"


def check(document):
    """Raise DocumentError on duplicate ids or dangling references."""
    ids = document.all_ids()
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise DocumentError(f"duplicate ids: {duplicates}")
    systems = {s.id: s for s in document.systems}
    for system in document.systems:
        if system.kind == "quantum" and system.hamiltonian is None:
            raise DocumentError(f"quantum system {system.id!r} has no hamiltonian")
        regions = {r.id for r in system.regions}
        if system.hamiltonian is not None:
            for term in system.hamiltonian.terms:
                if term.region is not None and term.region not in regions:
                    raise DocumentError(f"term {term.id!r} refers to region {term.region!r}, "
                                        f"which system {system.id!r} does not have")
        for op in system.geometry.ops:
            if op.region is not None:
                raise DocumentError(f"geometry op {op.id!r} cannot carry a region in phase 1")
    for calc in document.calculations:
        if calc.system not in systems:
            raise DocumentError(f"calculation {calc.id!r} refers to missing system {calc.system!r}")
