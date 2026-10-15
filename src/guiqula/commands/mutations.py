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
                                   Construction, DocumentError, Embedding, Entry, Geometry,
                                   Hamiltonian, Junction, KPath, geometry_chain, source_of,
                                   variants_of, MeanField, Model, Region, System,
                                   kpath_params, kpath_users, region_users, terms_of)
from guiqula.registry import base as registry
from guiqula.registry import plugins
from guiqula.registry.params import ParamError, SystemParam, normalize_vertices

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
               kind="quantum", model_params=None, geometry=None):
    """Add a system; returns its id. geometry: the id of a geometry of the
    document it is built on (New Hamiltonian on this geometry); left out, a
    new geometry on a base lattice (lattice, lattice_params). kind: quantum
    (a Hamiltonian) or a classical kind (classical_spin, lattice_gas,
    ising: a model, set up with model_params)."""
    if kind not in SYSTEM_KINDS:
        raise CommandError(f"unknown system kind {kind!r}; kinds: {list(SYSTEM_KINDS)}")
    system_id = document.new_id("system")
    if geometry is None:
        geometry = _new_geometry(document, lattice, lattice_params).id
    else:
        _geometry(document, geometry)
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


def _original_system(document, system):
    """The system whose Hamiltonian or model a command changes: a variant's
    original (a variant has none of its own)."""
    try:
        return source_of(document, document.system(system))
    except DocumentError as error:
        raise CommandError(str(error)) from None


def _not_a_variant(document, system, role):
    """Refuse a system variant named as a calculation's target, a tip, a lead,
    the central region or a system of an embedding: a variant is no node of
    its own, only a further input of its original (decision 262), so the
    original is named instead, or the variant made a system of its own."""
    found = next((s for s in document.systems if s.id == system), None)
    if found is not None and found.variant_of is not None:
        raise CommandError(f"{role}: {system} is a variant of {found.variant_of}, which "
                           f"follows it on another geometry; name {found.variant_of}, or "
                           f"duplicate {system} to make it a system of its own")


def _system_variants(document, system):
    """The ids of the variants of a system (none for an embedding or a
    junction)."""
    return [s.id for s in document.systems if s.variant_of == system]


# ---- variants: one calculation on two inputs, one Hamiltonian on two geometries
@mutation
def add_variant(document, entry, target):
    """A second input of a calculation or a system (a link drawn onto an
    input that has one, in the node view): a variant, an ordinary entry that
    follows its original's parameters (a calculation, on the system,
    embedding or junction target) or its Hamiltonian or model (a system, on
    the geometry target, or a system's geometry), so that the same
    calculation runs with both. A system's variant gets a variant of each of
    its original's calculations too. Returns the new id."""
    try:
        family, _, _, _, obj = document.find(entry)
    except DocumentError as error:
        raise CommandError(str(error)) from None
    original = source_of(document, obj)
    if family == "calculation":
        return _calculation_variant(document, original, target)
    if family != "system":
        raise CommandError(f"{entry!r} is a {family}: only a calculation or a system takes a "
                           f"second input")
    geometry = _geometry(document, target).id
    taken = [original.geometry] + [document.system(v).geometry
                                   for v in variants_of(document, original.id)
                                   if any(s.id == v for s in document.systems)]
    if geometry in taken:
        raise CommandError(f"{original.id} is built on {geometry} already")
    variant = System(id=document.new_id("system"), kind=original.kind, geometry=geometry,
                     hamiltonian=None, model=None, variant_of=original.id,
                     name=f"{original.name or original.id} on {geometry}")
    document.systems.append(variant)
    for calc in [c for c in document.calculations
                 if c.system == original.id and c.variant_of is None]:
        _calculation_variant(document, calc, variant.id)
    return variant.id


def _calculation_variant(document, original, target):
    try:
        target_kind = document.target_kind(target)
    except DocumentError as error:
        raise CommandError(str(error)) from None
    try:
        spec = registry.get("calculation", original.kind)
    except registry.RegistryError as error:
        raise CommandError(str(error).strip("\"'")) from None
    if target_kind not in spec.systems:
        raise CommandError(f"{spec.label} does not apply to {target}")
    found = next((s for s in document.systems if s.id == target), None)
    if found is not None and found.variant_of is not None \
            and found.variant_of != original.system:   # only the one that follows its system
        _not_a_variant(document, target, "target")
    taken = [original.system] + [c.system for c in document.calculations
                                 if c.variant_of == original.id]
    if target in taken:
        raise CommandError(f"{original.id} runs on {target} already")
    for param in spec.params:   # the variant follows these, so it would name itself
        if isinstance(param, SystemParam) and original.params.get(param.name) == target:
            raise CommandError(f"{original.id} names {target} as its {param.label}: a variant "
                               f"on it would name the system it runs on")
    variant = Calculation(id=document.new_id("calculation"), system=target, kind=original.kind,
                          plugin=original.plugin, variant_of=original.id)
    document.calculations.append(variant)
    return variant.id


def _new_geometry(document, lattice, params=None, name=""):
    geometry = Geometry(id=document.new_id("geometry"), name=_text("name", name),
                        base=Base(kind=lattice, params=_normalize("lattice", lattice, params),
                                  plugin=_plugin("lattice", lattice)))
    document.geometries.append(geometry)
    return geometry


def _geometry(document, target):
    """The geometry a command acts on: a geometry's id, or a system's (its
    geometry), so that system="s1" names the geometry of s1."""
    try:
        if any(g.id == target for g in document.geometries):
            return document.geometry(target)
        return document.geometry_of(target)
    except DocumentError:
        raise CommandError(f"no system or geometry {target!r}") from None


def _base(document, target):
    """The base lattice a geometry (of a system) starts from, through its
    parents."""
    try:
        return geometry_chain(document, _geometry(document, target).id)[0].base
    except DocumentError as error:
        raise CommandError(str(error)) from None


@mutation
def set_lattice(document, system, lattice, params=None):
    """Replace the base lattice of a geometry, given by its id or a system's
    (ops, regions and terms are kept); a geometry that started from another
    one starts from the lattice then."""
    geometry = _geometry(document, system)
    geometry.base = Base(kind=lattice, params=_normalize("lattice", lattice, params),
                         plugin=_plugin("lattice", lattice))
    geometry.parent = None


# ---- geometries (phase 9, part B)
@mutation
def add_geometry(document, lattice="honeycomb_lattice", params=None, parent=None, name=""):
    """Add a geometry, on a base lattice or starting from another geometry
    (parent: its id, a ribbon or an island cut from a decorated cell, which
    follows every edit of it); returns its id."""
    if parent is None:
        return _new_geometry(document, lattice, params, name).id
    _geometry(document, parent)
    geometry = Geometry(id=document.new_id("geometry"), name=_text("name", name),
                        parent=parent)
    document.geometries.append(geometry)
    return geometry.id


@mutation
def set_geometry(document, system, geometry):
    """Build a system on another geometry of the document (its terms' regions
    must be regions of that geometry); refused onto the geometry of its
    original or of one of its variants (decision 265)."""
    target = document.system(system)
    geometry = _geometry(document, geometry).id
    root = source_of(document, target)
    family = [root.id] + _system_variants(document, root.id)
    if any(document.system(s).geometry == geometry for s in family if s != target.id):
        raise CommandError(f"{root.id} is built on {geometry} already")  # one input each
    target.geometry = geometry


@mutation
def set_parent(document, geometry, parent):
    """Make a geometry start from another one (its base lattice goes); a
    cycle is refused."""
    target = _geometry(document, geometry)
    target.parent = _geometry(document, parent).id
    target.base = None


@mutation
def set_construction(document, system, has_spin=None, nambu=None, tij=None, is_sparse=None):
    """Change how the Hamiltonian is built (the requested Hilbert space,
    neighbour hoppings, sparse storage)."""
    target = _original_system(document, system)
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
    target = _original_system(document, system)
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
    target = _original_system(document, system)
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
    """Name a system, region, op, term, embedding, calculation or k-path (""
    takes an entry's name away)."""
    family, _, _, _, obj = document.find(entry)
    if family not in ("geometry", "system", "region", "op", "term", "embedding", "junction",
                      "calculation", "kpath"):
        raise CommandError(f"{entry!r} is a {family}, which has no name")
    obj.name = _text("name", name)


# ---- embeddings
def _quantum(document, system, role):
    try:
        target = document.system(_text(role, system))
    except DocumentError as error:
        raise CommandError(str(error)) from None
    if target.kind != "quantum":
        raise CommandError(f"{role}: {system} is a {target.kind.replace('_', ' ')} system, and "
                           f"it has to be a quantum one")
    _not_a_variant(document, target.id, role)
    return target


@mutation
def add_embedding(document, pristine, defect=None, name=""):
    """Add an embedding of a defect in the infinite pristine system; returns
    its id. defect: the defective system; None makes it, a copy of the
    pristine one on the same geometry (decision 224: the two cells are one),
    to which the defect's terms are added."""
    _quantum(document, pristine, "pristine")
    if defect is None:
        defect = _copy_system(document, pristine, linked=True)
        copy = document.system(defect)
        copy.name = f"{document.system(pristine).name or pristine} (defect)"
    _quantum(document, defect, "defect")
    if defect == pristine:
        raise CommandError("the defect is a system of its own, not the pristine one")
    embedding = Embedding(id=document.new_id("embedding"), name=_text("name", name),
                          pristine=pristine, defect=defect)
    embedding.name = embedding.name or embedding.id
    document.embeddings.append(embedding)
    return embedding.id


@mutation
def set_embedding(document, embedding, pristine=None, defect=None):
    """Name another pristine or defective system in an embedding."""
    try:
        target = document.embedding(embedding)
    except DocumentError as error:
        raise CommandError(str(error)) from None
    pristine = target.pristine if pristine is None else _quantum(document, pristine,
                                                                 "pristine").id
    defect = target.defect if defect is None else _quantum(document, defect, "defect").id
    if pristine == defect:
        raise CommandError("the defect is a system of its own, not the pristine one")
    target.pristine, target.defect = pristine, defect


# ---- junctions (phase 9, part D)
@mutation
def add_junction(document, left, right=None, central=None, name=""):
    """Add a junction of two semi-infinite leads, with an optional central
    region between them; returns its id. right: the right lead; None makes
    it, a copy of the left one on the same geometry, to which what makes it
    different is added (a pairing, an exchange field)."""
    _quantum(document, left, "left")
    if right is None:
        right = _copy_system(document, left, linked=True)
        document.system(right).name = f"{document.system(left).name or left} (right lead)"
    _quantum(document, right, "right")
    if central is not None:
        _quantum(document, central, "central")
    if len({left, right, central} - {None}) < (3 if central else 2):
        raise CommandError("the two leads and the central region are three systems")
    junction = Junction(id=document.new_id("junction"), name=_text("name", name), left=left,
                        right=right, central=central)
    junction.name = junction.name or junction.id
    document.junctions.append(junction)
    return junction.id


@mutation
def set_junction(document, junction, left=None, right=None, central=None, clear_central=False):
    """Name another system as a lead or the central region of a junction;
    clear_central takes the central region away."""
    try:
        target = document.junction(junction)
    except DocumentError as error:
        raise CommandError(str(error)) from None
    left = target.left if left is None else _quantum(document, left, "left").id
    right = target.right if right is None else _quantum(document, right, "right").id
    central = None if _flag("clear_central", clear_central) else \
        target.central if central is None else _quantum(document, central, "central").id
    if len({left, right, central} - {None}) < (3 if central else 2):
        raise CommandError("the two leads and the central region are three systems")
    target.left, target.right, target.central = left, right, central


# ---- stacks
@mutation
def add_geometry_op(document, system, kind, params=None, index=None, enabled=True):
    """Add a geometry op to a geometry, given by its id or a system's (at the
    end, or at index); returns its id."""
    target = _geometry(document, system)
    op = Entry(id=document.new_id("op"), kind=kind, enabled=_flag("enabled", enabled),
               params=_normalize("geometry_op", kind, params),
               plugin=_plugin("geometry_op", kind))
    _insert(target.ops, op, index)
    return op.id


@mutation
def add_term(document, system, kind, params=None, region=None, index=None, enabled=True,
             name=""):
    """Add a term to a system's Hamiltonian, or to its classical model (at
    the end, or at index), with an optional name; returns its id."""
    target = _original_system(document, system)
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
    """Add a named region (a site selection) to a geometry, given by its id
    or a system's; returns its id."""
    try:
        select = region_tools.normalize(select)
    except region_tools.RegionError as error:
        raise CommandError(str(error)) from None
    region = Region(id=document.new_id("region"), name=name, select=select)
    region.name = name or region.id
    _geometry(document, system).regions.append(region)
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
    """Add a calculation on a system or an embedding, with an optional name;
    returns its id. A k-path it walks and is not given is the one of the
    last calculation of the document on the same system that walks one,
    else a new k-path, pyqula's default path (phase 9, decision 217); one
    given as its vertices rather than an id becomes a k-path of its own,
    named after the calculation (decision 235)."""
    try:
        target_kind = document.target_kind(system)
    except DocumentError as error:
        raise CommandError(str(error)) from None
    _not_a_variant(document, system, "system")
    calc = Calculation(id=document.new_id("calculation"), system=system, kind=kind,
                       params={}, plugin=_plugin("calculation", kind), name=_text("name", name))
    names = kpath_params(calc)
    inline = {n: v for n, v in (params or {}).items() if n in names and isinstance(v, list)}
    params = _normalize("calculation", kind, {n: v for n, v in (params or {}).items()
                                              if n not in inline})
    spec = registry.get("calculation", kind)
    if target_kind not in spec.systems:
        what = "an embedding" if target_kind == "embedding" else f"a {target_kind} system"
        raise CommandError(f"{spec.label} does not apply to {what}; it is a calculation of "
                           f"{', '.join(spec.systems)} systems")
    for n, vertices in inline.items():         # its own k-path, named after it
        kpath = KPath(id=document.new_id("kpath"), name=calc.name or calc.id,
                      vertices=_vertices(vertices))
        document.kpaths.append(kpath)
        params[n] = kpath.id
    calc.params = params
    _check_systems_named(document, calc)
    if any(params.get(n) is None for n in names):
        last = _last_kpath(document, system)
        if last is None:
            last = KPath(id=document.new_id("kpath"))
            document.kpaths.append(last)
            last = last.id
        calc.params = dict(params, **{n: last for n in names if params.get(n) is None})
    _check_kpaths(document, calc)
    document.calculations.append(calc)
    _follow(document, calc)
    return calc.id


def _follow(document, calc):
    """Give an original calculation a variant on each variant of its system
    that it has none on: a calculation of a system runs on every variant of
    it."""
    taken = {c.system for c in document.calculations if c.variant_of == calc.id}
    for variant in _system_variants(document, calc.system):
        if variant not in taken:
            _calculation_variant(document, calc, variant)


@mutation
def set_calculation_system(document, calculation, system):
    """Run a calculation on another system or embedding (a link drawn in the
    node view); refused when its entry does not apply to that kind, for a
    variant, or onto an input one of its variants has. Its variants on the
    variants of the old system go, and it gets one on each variant of the
    new one (decision 264)."""
    try:
        calc = document.calculation(calculation)
        target_kind = document.target_kind(system)
    except DocumentError as error:
        raise CommandError(str(error)) from None
    try:
        spec = registry.get("calculation", calc.kind)
    except registry.RegistryError as error:
        raise CommandError(str(error).strip("\"'")) from None
    if target_kind not in spec.systems:
        what = "an embedding" if target_kind == "embedding" else f"a {target_kind} system"
        raise CommandError(f"{spec.label} does not apply to {what}; it is a calculation of "
                           f"{', '.join(spec.systems)} systems")
    if calc.variant_of is not None:
        raise CommandError(f"{calculation} is a variant of {calc.variant_of}: link its new "
                           f"input to {calc.variant_of}, or remove {calculation}")
    _not_a_variant(document, system, "system")
    old = calc.system
    following = {c.id for c in document.calculations if c.variant_of == calc.id
                 and c.system in _system_variants(document, old)}
    taken = [c.system for c in document.calculations
             if c.variant_of == calc.id and c.id not in following]
    if system in taken:
        raise CommandError(f"{calculation} runs on {system} already")
    for param in spec.params:   # it would probe the system it runs on (decision 268)
        if isinstance(param, SystemParam) and calc.params.get(param.name) == system:
            raise CommandError(f"{calculation} names {system} as its {param.label}: it "
                               f"cannot run on it too")
    calc.system = system
    # the variants that followed it on the variants of its old system go, and it
    # follows the variants of its new one (decision 264)
    document.calculations[:] = [c for c in document.calculations if c.id not in following]
    _follow(document, calc)


def _last_kpath(document, system):
    """The k-path of the last calculation on a system that walks one."""
    for calc in reversed(document.calculations):
        if calc.system == system:
            for name in kpath_params(calc):
                if isinstance(calc.params.get(name), str):
                    return calc.params[name]
    return None


def _check_kpaths(document, calc):
    """Refuse a calculation that names a k-path the document does not have."""
    for name in kpath_params(calc):
        value = calc.params.get(name)
        if value is not None and value not in {k.id for k in document.kpaths}:
            raise CommandError(f"{name}: there is no k-path {value!r}; the k-paths are "
                               f"{[k.id for k in document.kpaths]}")


# ---- k-paths (phase 9, part A)
def _vertices(vertices):
    try:
        return normalize_vertices("vertices", vertices)
    except ParamError as error:
        raise CommandError(str(error)) from None


def _kpath(document, kpath):
    try:
        return document.kpath(kpath)
    except DocumentError as error:
        raise CommandError(str(error)) from None


@mutation
def add_kpath(document, vertices=None, name=""):
    """Add a k-path (no vertices: pyqula's default path); returns its id."""
    kpath = KPath(id=document.new_id("kpath"), name=_text("name", name),
                  vertices=_vertices(vertices))
    document.kpaths.append(kpath)
    return kpath.id


@mutation
def set_kpath(document, kpath, vertices):
    """Set the vertices of a k-path (none: pyqula's default path), for every
    calculation that walks it."""
    _kpath(document, kpath).vertices = _vertices(vertices)


@mutation
def single_user_kpath(document, calculation, param="kpath", copy=True):
    """Give a calculation a k-path of its own, a copy of the one it walks
    (copy true, Make single-user) or pyqula's default path (copy false, New
    k-path), named after it, so that an edit of the path changes this
    calculation alone; returns the new k-path's id."""
    try:
        calc = source_of(document, document.calculation(calculation))  # a variant's: its original's
    except DocumentError as error:
        raise CommandError(str(error)) from None
    if param not in kpath_params(calc):
        raise CommandError(f"{calculation} walks no k-path {param!r}")
    vertices = []
    if _flag("copy", copy) and calc.params.get(param) is not None:
        vertices = list(_kpath(document, calc.params[param]).vertices)
    copy = KPath(id=document.new_id("kpath"), name=calc.name or calc.id, vertices=vertices)
    document.kpaths.append(copy)
    calc.params = dict(calc.params, **{param: copy.id})
    return copy.id


@mutation
def remove(document, entry):
    """Remove a geometry, system, op, term, region, embedding, calculation or
    k-path. A geometry a system names or another starts from, a region still
    used by a term, a system a calculation runs on or names (the
    tip of a local probe) or an embedding names, an embedding a calculation
    runs on, or a k-path a calculation walks, cannot be removed."""
    family, owner, items, index, obj = document.find(entry)
    if family == "region":
        users = []
        for system in (document.system(s) for s in document.systems_on(owner.id)):
            users += [t.id for t in terms_of(system) if t.region == entry]
            users += [user for user, params in region_users(system)
                      if entry in field_tools.regions_of(list(params.values()))
                      and user not in users]
        if users:
            raise CommandError(f"region {entry!r} is used by {users}")
    if family == "geometry":
        users = document.systems_on(entry)
        if users:
            raise CommandError(f"geometry {entry!r} is the geometry of systems {users}")
        children = [g.id for g in document.geometries if g.parent == entry]
        if children:
            raise CommandError(f"geometry {entry!r} is where geometries {children} start")
    if family in ("system", "calculation"):
        variants = [v for v in variants_of(document, entry)
                    if family == "calculation" or any(s.id == v for s in document.systems)]
        if variants:
            raise CommandError(f"{family} {entry!r} has variants {variants}: remove them first")
    if family == "system" and obj.variant_of is not None:   # its calculation variants go too
        document.calculations[:] = [c for c in document.calculations
                                    if not (c.system == entry and c.variant_of is not None)]
    if family == "system":
        users = [c.id for c in document.calculations
                 if c.system == entry or entry in _systems_named(c)]
        if users:
            raise CommandError(f"system {entry!r} is used by calculations {users}")
        named = [e.id for e in document.embeddings_of(entry)]
        if named:
            raise CommandError(f"system {entry!r} is part of embeddings {named}")
        named = [j.id for j in document.junctions_of(entry)]
        if named:
            raise CommandError(f"system {entry!r} is part of junctions {named}")
    if family in ("embedding", "junction"):
        users = [c.id for c in document.calculations if c.system == entry]
        if users:
            raise CommandError(f"{family} {entry!r} is used by calculations {users}")
    if family == "kpath":
        users = kpath_users(document, entry)
        if users:
            raise CommandError(f"k-path {entry!r} is walked by calculations {users}")
    del items[index]


@mutation
def remove_entries(document, entries):
    """Remove several entries as one step (Del on nodes selected together),
    each after whatever among them uses it: a system after its
    calculations, a geometry after its systems. Refused whole, saying why,
    when something left out of entries still uses one of them."""
    if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries) \
            or not entries:
        raise CommandError("entries is a list of entry ids")
    left, removed = list(dict.fromkeys(entries)), []
    while left:
        refused = []
        for entry in left:
            try:
                remove(document.copy_deep(), entry)    # a refusal changes nothing
            except (CommandError, DocumentError) as error:
                refused.append((entry, error))
                continue
            remove(document, entry)
            removed.append(entry)
        if len(refused) == len(left):    # say what holds from outside, not the chain
            outside = [str(error) for entry, error in refused
                       if not any(f"'{other}'" in str(error) for other in left if other != entry)]
            raise CommandError((outside or [str(refused[0][1])])[0])
        left = [entry for entry, _ in refused]
    return removed

def _systems_named(calc):
    """Ids of the other systems a calculation names (SystemParam)."""
    try:
        spec = registry.get("calculation", calc.kind)
    except registry.RegistryError:
        return set()
    return {calc.params.get(p.name) for p in spec.params if isinstance(p, SystemParam)} - {None}


def _check_systems_named(document, calc):
    """Refuse a SystemParam (the tip of a local probe) naming a system
    variant."""
    try:
        spec = registry.get("calculation", calc.kind)
    except registry.RegistryError:
        return
    for param in spec.params:
        if isinstance(param, SystemParam) and calc.params.get(param.name) is not None:
            _not_a_variant(document, calc.params[param.name], param.name)


@mutation
def duplicate(document, entry):
    """Copy a geometry, op, term, region, embedding, calculation (which walks
    the same k-path as the original) or k-path (placed right after the
    original), or a whole system with a copy of its geometry and fresh ids
    for everything in them (its terms point at the copies of the regions);
    returns the new id."""
    family, _, items, index, obj = document.find(entry)
    if family == "system":
        return _copy_system(document, entry)
    if family == "geometry":
        return _copy_geometry(document, entry)[0]
    if family == "calculation" and obj.variant_of is not None:
        # the copy of a variant is a calculation of its own, with its original's
        # parameters on the variant's input (decision 263)
        source = source_of(document, obj)
        if obj.system in _system_variants(document, source.system):
            raise CommandError(f"{entry} follows {obj.variant_of} on {obj.system}, a variant "
                               f"of its system; duplicate {obj.variant_of} instead")
        copy = source.model_copy(deep=True)
        copy.system, copy.variant_of = obj.system, None
    else:
        copy = obj.model_copy(deep=True)
    items.insert(index + 1, copy)          # new ids are allocated with the copy in place
    copy.id = document.new_id(family)
    if family == "region":
        copy.name = f"{obj.name} (copy)"
    if family in ("embedding", "junction", "kpath"):
        copy.name = f"{obj.name or obj.id} (copy)"
    if family == "calculation":
        _follow(document, copy)            # on the variants of its system too
    return copy.id


@mutation
def duplicate_linked(document, system):
    """Copy a system that shares its geometry with the original (Blender's
    Alt+D): a new Hamiltonian or model on the same sites, whose terms keep
    naming the same regions; returns its id."""
    return _copy_system(document, system, linked=True)


def _copy_geometry(document, geometry_id):
    """A copy of a geometry right after it, with fresh op and region ids;
    returns (its id, {old region id: new id})."""
    _, _, items, index, obj = document.find(geometry_id)
    copy = obj.model_copy(deep=True)
    items.insert(index + 1, copy)
    copy.id = document.new_id("geometry")
    if obj.name:
        copy.name = f"{obj.name} (copy)"
    for op in copy.ops:
        op.id = document.new_id("op")
    regions = {}
    for region in copy.regions:
        regions[region.id] = region.id = document.new_id("region")
    return copy.id, regions


def _copy_system(document, system_id, linked=False):
    """A copy of a system right after it, with fresh ids; with a copy of its
    geometry, or naming the same one (linked); returns its id."""
    _, _, items, index, obj = document.find(system_id)
    copy = obj.model_copy(deep=True)
    if obj.variant_of is not None:         # a system of its own, with its original's
        source = source_of(document, obj)  # Hamiltonian or model (decision 263)
        copy.hamiltonian = None if source.hamiltonian is None else \
            source.hamiltonian.model_copy(deep=True)
        copy.model = None if source.model is None else source.model.model_copy(deep=True)
        copy.variant_of = None
    items.insert(index + 1, copy)
    copy.id = document.new_id("system")
    copy.name = f"{obj.name or obj.id} (copy)"
    regions = {}
    if not linked:
        copy.geometry, regions = _copy_geometry(document, obj.geometry)
    for term in terms_of(copy):
        term.id = document.new_id("term")
        if term.region is not None:
            term.region = regions.get(term.region, term.region)
        term.params = _rename_regions(term.params, regions)
    if copy.hamiltonian is not None:
        block = copy.hamiltonian.meanfield
        block.params = _rename_regions(block.params, regions)
    return copy.id


@mutation
def move(document, entry, index):
    """Move an op, term, region or calculation to a new position in its list."""
    family, _, items, old, obj = document.find(entry)
    if family in ("geometry", "system", "embedding", "junction", "kpath"):
        raise CommandError(f"{family}s are not ordered")
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
    """Set one parameter of an op, term or calculation (or of the base
    lattice of a geometry, when entry is a geometry's id or a system's)."""
    family, _, _, _, obj = document.find(entry)
    if family in ("system", "geometry"):
        base = _base(document, entry)
        base.params = _normalize("lattice", base.kind, dict(base.params, **{name: value}))
        return
    if family not in FAMILY_OF:
        raise CommandError(f"{entry!r} is a {family}, which has no parameters")
    if family == "calculation":
        obj = source_of(document, obj)        # a variant's are its original's
    obj.params = _normalize(FAMILY_OF[family], obj.kind, dict(obj.params, **{name: value}))
    if family == "calculation":
        _check_kpaths(document, obj)
        _check_systems_named(document, obj)


@mutation
def set_params(document, entry, params):
    """Set several parameters at once (one undo step)."""
    family, _, _, _, obj = document.find(entry)
    if family not in FAMILY_OF:
        raise CommandError(f"{entry!r} is a {family}, which has no parameters")
    if family == "calculation":
        obj = source_of(document, obj)
    obj.params = _normalize(FAMILY_OF[family], obj.kind, dict(obj.params, **params))
    if family == "calculation":
        _check_kpaths(document, obj)
        _check_systems_named(document, obj)


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
