"""The mutations of the Document (see guiqula.commands.dispatcher).

Each receives a private deep copy of the Document plus JSON arguments,
changes the copy, and returns a JSON result (the id of a new entry, or
None). Parameters are normalized through the registry, so the Document
always stores complete, checked parameter sets. An entry whose kind is
unknown to the registry (a missing plugin) is kept as it is and flagged by
the pipeline planner: it can be enabled or disabled, moved, duplicated or
removed, but not edited, since its parameters cannot be checked. Arguments
come as JSON from drivers too (the remote API, the console): a flag must be
true or false and a text a string, never read through bool() or str(), for
which "false" is true and null the text "None".
"""
from guiqula.commands.dispatcher import CommandError, mutation
from guiqula.core import fields as field_tools
from guiqula.core import locks as lock_tools
from guiqula.core import regions as region_tools
from guiqula.core.document import (CLASSICAL_KINDS, SYSTEM_KINDS, Base, Calculation,
                                   Construction, Entry, Geometry, Hamiltonian, MeanField, Model,
                                   Region, System, region_users, terms_of)
from guiqula.registry import base as registry
from guiqula.registry import plugins
from guiqula.registry.params import ParamError

FAMILY_OF = {"op": "geometry_op", "term": "term", "calculation": "calculation"}


def _normalize(family, kind, params):
    try:
        return registry.get(family, kind).normalize_params(params)
    except (registry.RegistryError, ParamError) as error:
        raise CommandError(str(error).strip("\"'")) from None


def _plugin(family, kind):
    """What the Document records of the plugin that provides an entry ("" for
    guiqula's own; registry/plugins.py, origin)."""
    try:
        return plugins.origin(registry.get(family, kind))
    except registry.RegistryError:
        return ""


def _rename_regions(params, mapping):
    return {name: field_tools.rename_regions(value, mapping) for name, value in params.items()}


def _flag(name, value):
    if not isinstance(value, bool):
        raise CommandError(f"{name}: expected true or false, got {value!r}")
    return value


def _text(name, value):
    if not isinstance(value, str):
        raise CommandError(f"{name}: expected a text, got {value!r}")
    return value


def _insert(items, item, index):
    if index is None:
        items.append(item)
    else:
        if not -len(items) - 1 <= index <= len(items):
            raise CommandError(f"index {index} out of range")
        items.insert(index, item)


# ---- systems
@mutation
def add_system(document, lattice="honeycomb_lattice", name="", lattice_params=None,
               kind="quantum", model_params=None):
    """Add a system built on a base lattice; returns its id. kind: quantum
    (a Hamiltonian) or a classical kind (classical_spin, lattice_gas,
    ising: a model, set up with model_params)."""
    if kind not in SYSTEM_KINDS:
        raise CommandError(f"unknown system kind {kind!r}; kinds: {list(SYSTEM_KINDS)}")
    params = _normalize("lattice", lattice, lattice_params)
    system_id = document.new_id("system")
    geometry = Geometry(base=Base(kind=lattice, params=params,
                                  plugin=_plugin("lattice", lattice)))
    if kind in CLASSICAL_KINDS:
        model = Model(kind=kind, params=_normalize("model", kind, model_params),
                      plugin=_plugin("model", kind))
        system = System(id=system_id, name=name or system_id, kind=kind, geometry=geometry,
                        hamiltonian=None, model=model)
    else:
        system = System(id=system_id, name=name or system_id, geometry=geometry,
                        hamiltonian=Hamiltonian())
    document.systems.append(system)
    return system_id


@mutation
def set_lattice(document, system, lattice, params=None):
    """Replace the base lattice of a system (ops and terms are kept)."""
    document.system(system).geometry.base = Base(kind=lattice,
                                                 params=_normalize("lattice", lattice, params),
                                                 plugin=_plugin("lattice", lattice))


@mutation
def set_construction(document, system, has_spin=None, nambu=None, tij=None, is_sparse=None):
    """Change how the Hamiltonian is built (the requested Hilbert space,
    neighbour hoppings, sparse storage)."""
    target = document.system(system)
    if target.hamiltonian is None:
        raise CommandError(f"system {system!r} has no Hamiltonian")
    data = target.hamiltonian.construction.model_dump()
    for key, value in dict(has_spin=has_spin, nambu=nambu, tij=tij, is_sparse=is_sparse).items():
        if value is not None:
            data[key] = value
    target.hamiltonian.construction = Construction.model_validate(data)


@mutation
def set_meanfield(document, system, enabled=None, params=None, kind=None):
    """Enable or disable the mean-field block of a system, change its
    parameters (merged into the stored ones, one undo step) or its kind."""
    target = document.system(system)
    if target.hamiltonian is None:
        raise CommandError(f"system {system!r} has no Hamiltonian")
    block = target.hamiltonian.meanfield
    kind = block.kind if kind is None else kind
    merged = dict(block.params if kind == block.kind else {}, **(params or {}))
    target.hamiltonian.meanfield = MeanField(
        enabled=block.enabled if enabled is None else _flag("enabled", enabled), kind=kind,
        params=_normalize("meanfield", kind, merged), plugin=_plugin("meanfield", kind))


@mutation
def set_model(document, system, params):
    """Change the set-up parameters of a classical system's model (merged
    into the stored ones, one undo step)."""
    target = document.system(system)
    if target.model is None:
        raise CommandError(f"system {system!r} is {target.kind}: it has no classical model")
    model = target.model
    model.params = _normalize("model", model.kind, dict(model.params, **(params or {})))


@mutation
def set_notes(document, notes):
    """What the document is about: a title line, then a description."""
    document.notes = _text("notes", notes)


@mutation
def rename(document, entry, name):
    """Name a system, region, op, term or calculation ("" takes an entry's
    name away)."""
    family, _, _, _, obj = document.find(entry)
    if family not in ("system", "region", "op", "term", "calculation"):
        raise CommandError(f"{entry!r} is a {family}, which has no name")
    obj.name = _text("name", name)


# ---- stacks
@mutation
def add_geometry_op(document, system, kind, params=None, index=None, enabled=True):
    """Add a geometry op (at the end, or at index); returns its id."""
    target = document.system(system)
    op = Entry(id=document.new_id("op"), kind=kind, enabled=_flag("enabled", enabled),
               params=_normalize("geometry_op", kind, params),
               plugin=_plugin("geometry_op", kind))
    _insert(target.geometry.ops, op, index)
    return op.id


@mutation
def add_term(document, system, kind, params=None, region=None, index=None, enabled=True,
             name=""):
    """Add a term to a system's Hamiltonian, or to its classical model (at
    the end, or at index), with an optional name; returns its id."""
    target = document.system(system)
    params = _normalize("term", kind, params)
    spec = registry.get("term", kind)
    if target.kind not in spec.systems:
        raise CommandError(f"{spec.label} does not apply to a {target.kind} system; it is a "
                           f"term of {', '.join(spec.systems)} systems")
    term = Entry(id=document.new_id("term"), kind=kind, enabled=_flag("enabled", enabled),
                 params=params, region=region, plugin=plugins.origin(spec),
                 name=_text("name", name))
    _insert(terms_of(target), term, index)
    return term.id


@mutation
def add_region(document, system, select, name=""):
    """Add a named region (a site selection); returns its id."""
    try:
        select = region_tools.normalize(select)
    except region_tools.RegionError as error:
        raise CommandError(str(error)) from None
    region = Region(id=document.new_id("region"), name=name, select=select)
    region.name = name or region.id
    document.system(system).regions.append(region)
    return region.id


@mutation
def set_region(document, entry, region):
    """Restrict a term to a region (or lift the restriction with None)."""
    family, _, _, _, term = document.find(entry)
    if family != "term":
        raise CommandError(f"only terms take a region, {entry!r} is a {family}")
    term.region = region


@mutation
def set_selection(document, entry, select):
    """Replace the site selection of a region."""
    family, _, _, _, region = document.find(entry)
    if family != "region":
        raise CommandError(f"{entry!r} is a {family}, not a region")
    try:
        region.select = region_tools.normalize(select)
    except region_tools.RegionError as error:
        raise CommandError(str(error)) from None


@mutation
def add_calculation(document, system, kind, params=None, name=""):
    """Add a calculation on a system, with an optional name; returns its id."""
    target = document.system(system)
    params = _normalize("calculation", kind, params)
    spec = registry.get("calculation", kind)
    if target.kind not in spec.systems:
        raise CommandError(f"{spec.label} does not apply to a {target.kind} system; it is a "
                           f"calculation of {', '.join(spec.systems)} systems")
    calc = Calculation(id=document.new_id("calculation"), system=system, kind=kind,
                       params=params, plugin=_plugin("calculation", kind),
                       name=_text("name", name))
    document.calculations.append(calc)
    return calc.id


@mutation
def remove(document, entry):
    """Remove a system, op, term, region or calculation. A region still
    used by a term, or a system used by a calculation, cannot be removed."""
    family, owner, items, index, obj = document.find(entry)
    if family == "region":
        users = [t.id for t in terms_of(owner) if t.region == entry]
        users += [user for user, params in region_users(owner)
                  if entry in field_tools.regions_of(list(params.values())) and user not in users]
        if users:
            raise CommandError(f"region {entry!r} is used by {users}")
    if family == "system":
        users = [c.id for c in document.calculations if c.system == entry]
        if users:
            raise CommandError(f"system {entry!r} is used by calculations {users}")
    del items[index]


@mutation
def duplicate(document, entry):
    """Copy an op, term, region or calculation (placed right after the
    original), or a whole system with fresh ids for everything in it (its
    terms keep pointing at the copies of its regions); returns the new id."""
    family, _, items, index, obj = document.find(entry)
    copy = obj.model_copy(deep=True)
    items.insert(index + 1, copy)          # new ids are allocated with the copy in place
    if family != "system":
        copy.id = document.new_id(family)
        if family == "region":
            copy.name = f"{obj.name} (copy)"
        return copy.id
    copy.id = document.new_id("system")
    copy.name = f"{obj.name or obj.id} (copy)"
    for op in copy.geometry.ops:
        op.id = document.new_id("op")
    regions = {}
    for region in copy.regions:
        regions[region.id] = region.id = document.new_id("region")
    for term in terms_of(copy):
        term.id = document.new_id("term")
        if term.region is not None:
            term.region = regions[term.region]
        term.params = _rename_regions(term.params, regions)
    if copy.hamiltonian is not None:
        block = copy.hamiltonian.meanfield
        block.params = _rename_regions(block.params, regions)
    return copy.id


@mutation
def move(document, entry, index):
    """Move an op, term, region or calculation to a new position in its list."""
    family, _, items, old, obj = document.find(entry)
    if family == "system":
        raise CommandError("systems are not ordered")
    if not 0 <= index < len(items):
        raise CommandError(f"index {index} out of range 0..{len(items) - 1}")
    items.insert(index, items.pop(old))


@mutation
def set_enabled(document, entry, enabled):
    family, _, _, _, obj = document.find(entry)
    if family not in ("op", "term"):
        raise CommandError(f"only ops and terms can be disabled, {entry!r} is a {family}")
    obj.enabled = _flag("enabled", enabled)


@mutation
def set_param(document, entry, name, value):
    """Set one parameter of an op, term or calculation (or of a system's base
    lattice, when entry is a system id)."""
    family, _, _, _, obj = document.find(entry)
    if family == "system":
        base = obj.geometry.base
        base.params = _normalize("lattice", base.kind, dict(base.params, **{name: value}))
        return
    if family not in FAMILY_OF:
        raise CommandError(f"{entry!r} is a {family}, which has no parameters")
    obj.params = _normalize(FAMILY_OF[family], obj.kind, dict(obj.params, **{name: value}))


@mutation
def set_params(document, entry, params):
    """Set several parameters at once (one undo step)."""
    family, _, _, _, obj = document.find(entry)
    if family not in FAMILY_OF:
        raise CommandError(f"{entry!r} is a {family}, which has no parameters")
    obj.params = _normalize(FAMILY_OF[family], obj.kind, dict(obj.params, **params))


# ---- locks (teaching presets, core/locks.py)
@mutation
def lock(document, target):
    """Lock an entry ("t1"), a parameter ("t1.m"; "s1.n" for a lattice's) or
    a system's geometry ("s1/geometry"): commands that would change it are
    refused until it is unlocked."""
    try:
        lock_tools.check_target(document, target)
    except lock_tools.LockError as error:
        raise CommandError(str(error)) from None
    if target not in document.locks:
        document.locks.append(target)


@mutation
def unlock(document, target=None):
    """Unlock one target, or everything (target None)."""
    if target is None:
        document.locks.clear()
    elif target in document.locks:
        document.locks.remove(target)
    else:
        raise CommandError(f"{target!r} is not locked; locked: {document.locks}")
