"""The Document as a graph (PLAN.md phase 9, part C), without Qt and
without pyqula: the nodes, their sockets and the links between them, which
the node view (ui/nodes.py) draws, and the Command a link drawn by hand is.

The Document is a graph already, drawn by the outliner as a tree: a system
names its geometry, a geometry the one it starts from, a calculation its
target (a system or an embedding), the other systems it uses (a
SystemParam, the tip of a local probe) and the k-paths it walks (a
KPathParam), an embedding its pristine and its defect system; besides
those, a from_result Field reads the result of a calculation, and a sweep
moves parameters of entries; a junction names its two leads and its
central region (part D). A node is a geometry, a system, a k-path, an
embedding, a junction or a calculation. The sockets are read from the declarations
(spec.systems, the SystemParams, the KPathParams of a calculation's
registry entry), never listed by hand, so a plugin's calculation gets
them too. A link is solid when it is an id a socket holds, which a link
drawn by hand sets (connect); dashed for a from_result Field, from the
calculation whose result it reads to the system of the term; dotted for a
sweep, from the sweep to the calculation it runs and to the node of each
parameter it moves. The dashed and dotted links are shown and not edited
(decision 231).

An input that is never empty (the geometry of a system, the target and a
k-path of a calculation, the two systems of an embedding, the parent of a
geometry that has no lattice) is moved by a new link and never cut; an
optional one (the tip of a local probe) can be cut, meaning the entry's
default (decision 230). The nodes sit in columns by kind, left to right,
in Document order (layout); a node moved by hand keeps its place in the
Document's ui block, as view state, not as a Command (decision 229).
"""
from dataclasses import dataclass, field

from guiqula.core import fields
from guiqula.core.document import DocumentError, terms_of
from guiqula.registry import base as registry
from guiqula.registry.params import KPathParam, SystemParam

COLUMNS = ("geometry", "kpath", "system", "embedding", "junction", "calculation")
# the column of each kind, left to right: what a node takes is to its left (the k-paths
# under the geometries, which nothing links to each other)
COLUMN_OF = {"geometry": 0, "kpath": 1, "system": 1, "embedding": 2, "junction": 2,
             "calculation": 3}
OUTPUT = {"geometry": "geometry", "kpath": "kpath", "system": "system",
          "embedding": "embedding", "junction": "junction", "calculation": "result"}
TITLES = {"geometry": "Geometry", "kpath": "k-path", "embedding": "Embedding",
          "calculation": "Calculation"}


class GraphError(ValueError):
    """A link the declarations do not take."""


@dataclass
class Socket:
    name: str                   # "geometry", "parent", "target", a parameter's name...
    label: str
    accepts: tuple              # the kinds of output it takes ("geometry", "system", ...)
    required: bool = True       # never empty: moved by a link, never cut
    source: str | None = None   # the id of the node linked to it, if any
    kinds: tuple = ()           # for a system input: the system kinds it takes
    extra: list = field(default_factory=list)   # [(source, variant id)]: its further inputs
    multi: bool = False         # takes further inputs (a variant each)


@dataclass
class Node:
    id: str
    kind: str                   # geometry, system, kpath, embedding, calculation
    title: str                  # Hamiltonian, Model, Geometry, k-path, the calculation's label
    name: str = ""
    inputs: list = field(default_factory=list)
    output: str = ""            # what it gives a link: geometry, system, kpath, result...
    column: int = 0
    row: int = 0
    detail: str = ""            # what it is besides its name: a lattice, a path

@dataclass
class Link:
    source: str                 # node id
    target: str                 # node id
    socket: str                 # the target's input ("" for a dashed or dotted link)
    style: str = "solid"        # solid, dashed (a from_result Field), dotted (a sweep)
    variant: str | None = None  # the variant a further input of the socket is


def _label(family, kind):
    try:
        return registry.get(family, kind).label
    except registry.RegistryError:
        return kind


def _calc_spec(calc):
    try:
        return registry.get("calculation", calc.kind)
    except registry.RegistryError:
        return None


def nodes(document):
    """The nodes of a Document, each with its sockets, in columns by kind and
    in Document order within a column, the k-paths under the systems
    (decision 272)."""
    out = []

    def add(node):
        node.column = COLUMN_OF[node.kind]
        node.row = sum(1 for n in out if n.column == node.column and n.kind != "kpath")
        out.append(node)

    for geometry in document.geometries:
        inputs = []
        if geometry.parent is not None:
            inputs.append(Socket("parent", "starts from", ("geometry",), True, geometry.parent))
        detail = "" if geometry.base is None else _label("lattice", geometry.base.kind)
        ops = len(geometry.ops)
        detail += f" · {ops} op{'s' if ops != 1 else ''}" if ops else ""
        add(Node(geometry.id, "geometry", "Geometry", geometry.name, inputs, "geometry",
                 detail=detail.strip(" ·")))
    for kpath in document.kpaths:
        path = " ".join("Γ" if v == "G" else v if isinstance(v, str) else
                        "(" + ", ".join(f"{c:g}" for c in v[:2]) + ")" for v in kpath.vertices)
        add(Node(kpath.id, "kpath", "k-path", kpath.name, [], "kpath",
                 detail=path or "pyqula's default path"))
    variants = {}                              # original id: [(input, variant id)]
    for system in document.systems:
        if system.variant_of is not None:      # drawn as a further geometry of its original
            variants.setdefault(system.variant_of, []).append((system.geometry, system.id))
    hidden = {s.id: s.variant_of for s in document.systems if s.variant_of is not None}
    systems = {c.id: c.system for c in document.calculations}
    for calc in document.calculations:
        if calc.variant_of is None:
            continue
        if calc.system not in hidden:
            variants.setdefault(calc.variant_of, []).append((calc.system, calc.id))
        elif hidden[calc.system] != systems.get(calc.variant_of):
            # it follows its original on a variant of a system the original no longer
            # runs on (a file written before decision 264): drawn from that system, so
            # that it can be seen and cut
            variants.setdefault(calc.variant_of, []).append((hidden[calc.system], calc.id))
    for system in document.systems:
        if system.variant_of is not None:
            continue
        title = "Hamiltonian" if system.kind == "quantum" else "Model"
        add(Node(system.id, "system", title, system.name,
                 [Socket("geometry", "geometry", ("geometry",), True, system.geometry,
                         extra=variants.get(system.id, []), multi=True)],
                 "system"))
    for embedding in document.embeddings:
        add(Node(embedding.id, "embedding", "Embedding", embedding.name, [
            Socket("pristine", "pristine", ("system",), True, embedding.pristine, ("quantum",)),
            Socket("defect", "defect", ("system",), True, embedding.defect, ("quantum",))],
            "embedding"))
    for junction in document.junctions:
        add(Node(junction.id, "junction", "Junction", junction.name, [
            Socket("left", "left lead", ("system",), True, junction.left, ("quantum",)),
            Socket("right", "right lead", ("system",), True, junction.right, ("quantum",)),
            Socket("central", "central region", ("system",), False, junction.central,
                   ("quantum",))], "junction"))
    for calc in document.calculations:
        if calc.variant_of is not None:          # drawn as a further input of its original
            continue
        spec = _calc_spec(calc)
        target_kinds = tuple(spec.systems) if spec is not None else ()
        accepts = tuple(kind for kind, takes in (
            ("system", bool(set(target_kinds) - {"embedding", "junction"})),
            ("embedding", "embedding" in target_kinds),
            ("junction", "junction" in target_kinds)) if takes)
        inputs = [Socket("target", "runs on", accepts or ("system",), True, calc.system,
                         tuple(k for k in target_kinds if k not in ("embedding", "junction")),
                         extra=variants.get(calc.id, []), multi=True)]
        for param in (spec.params if spec is not None else ()):
            if isinstance(param, SystemParam):
                inputs.append(Socket(param.name, param.label, ("system",), not param.optional,
                                     calc.params.get(param.name), tuple(param.kinds)))
            elif isinstance(param, KPathParam):
                inputs.append(Socket(param.name, param.label, ("kpath",), True,
                                     calc.params.get(param.name)))
        add(Node(calc.id, "calculation", spec.label if spec is not None else calc.kind,
                 calc.name, inputs, "result"))
    below = {}                  # a k-path under the systems, so its link crosses none
    for node in out:
        if node.kind != "kpath":
            below[node.column] = max(below.get(node.column, 0), node.row + 1)
    for n, node in enumerate(n for n in out if n.kind == "kpath"):
        node.row = below.get(node.column, 0) + n
    return out


def links(document, graph=None):
    """Every link: solid from what an input holds, dashed from a calculation
    whose result a term's from_result Field reads to the term's system,
    dotted from a sweep to the calculation it runs and to what it moves."""
    graph = graph if graph is not None else nodes(document)
    ids = {n.id for n in graph}
    out = [Link(socket.source, node.id, socket.name) for node in graph
           for socket in node.inputs if socket.source in ids]
    out += [Link(source, node.id, socket.name, variant=variant) for node in graph
            for socket in node.inputs for source, variant in socket.extra if source in ids]
    for system in document.systems:
        params = [t.params for t in terms_of(system)]
        if system.hamiltonian is not None:
            params.append(system.hamiltonian.meanfield.params)
        for calc_id in sorted(set(fields.results_of(params))):
            if calc_id in ids:
                out.append(Link(calc_id, system.id, "", "dashed"))
    for calc in document.calculations:
        if calc.kind != "sweep":
            continue
        moved = [calc.params.get("calculation")] + [owner_node(document, calc.params.get(key))
                                                    for key in ("entry", "entry2")]
        for target in dict.fromkeys(m for m in moved if m in ids and m != calc.id):
            out.append(Link(calc.id, target, "", "dotted"))
    return out


def owner_node(document, target):
    """The node an entry or a pseudo id belongs to: a term's system, an op's
    or a region's geometry, a system, a calculation; None if none."""
    if not target:
        return None
    if "/" in target:
        return target.split("/", 1)[0]
    try:
        family, owner, _, _, obj = document.find(target)
    except DocumentError:
        return None
    if family in ("system", "geometry", "calculation", "embedding", "junction", "kpath"):
        return obj.id
    return owner.id if owner is not None else None


def node_kind(document, node_id):
    """geometry, system, kpath, embedding or calculation; None otherwise."""
    try:
        family = document.find(node_id)[0]
    except DocumentError:
        return None
    return family if family in COLUMNS else None


def connect(document, source, target, socket, replace=False):
    """The Command (name, args) that links the output of node source to the
    input socket of node target; GraphError, saying why, when the
    declaration does not take it. On an input that takes further inputs (a
    calculation's target, a system's geometry) and has one, the link adds
    one, a variant (add_variant), unless replace, which moves it."""
    graph = {n.id: n for n in nodes(document)}
    if target not in graph:
        raise GraphError(f"{target!r} is not a node with inputs")
    if source not in graph:
        raise GraphError(f"{source!r} is not a node")
    node, out = graph[target], graph[source]
    entry = next((s for s in node.inputs if s.name == socket), None)
    if entry is None:
        names = [s.name for s in node.inputs] or ["none"]
        raise GraphError(f"{target} has no input {socket!r}; its inputs: {', '.join(names)}")
    if out.output not in entry.accepts:
        raise GraphError(f"the {entry.label} of {target} takes a {' or '.join(entry.accepts)}, "
                         f"not a {out.output}")
    if source == target:
        raise GraphError(f"{target} cannot take itself")
    if out.kind == "system" and entry.kinds:
        kind = document.system(source).kind
        if kind not in entry.kinds:
            raise GraphError(f"the {entry.label} of {target} takes a "
                             f"{' or '.join(entry.kinds).replace('_', ' ')} system, and "
                             f"{source} is {kind.replace('_', ' ')}")
    if entry.multi and entry.source is not None:
        if source == entry.source or source in [s for s, _ in entry.extra]:
            # a replace too: the original and its variant would share one input
            raise GraphError(f"{source} is an input of {target} already")
        if node.kind == "calculation":
            named = next((s for s in node.inputs if s.name != "target"
                          and "system" in s.accepts and s.source == source), None)
            if named is not None:   # a variant follows the original's parameters
                raise GraphError(f"{target} names {source} as its {named.label}, so it "
                                 f"cannot run on it too; link another one")
        if not replace:
            return "add_variant", {"entry": target, "target": source}
    if node.kind == "calculation" and socket != "target" and out.kind == "system":
        calc = document.calculation(target)
        own = [calc.system] + [c.system for c in document.calculations
                               if c.variant_of == target]
        if source in own:
            raise GraphError(f"the {entry.label} of {target} is {source}, the system it runs "
                             f"on; link another one")
    if node.kind == "system":
        return "set_geometry", {"system": target, "geometry": source}
    if node.kind == "geometry":
        return "set_parent", {"geometry": target, "parent": source}
    if node.kind == "embedding":
        return "set_embedding", {"embedding": target, socket: source}
    if node.kind == "junction":
        return "set_junction", {"junction": target, socket: source}
    if socket == "target":
        return "set_calculation_system", {"calculation": target, "system": source}
    return "set_param", {"entry": target, "name": socket, "value": source}


def cut(document, target, socket, source=None):
    """The Command that empties an optional input (meaning the entry's
    default), or takes away a further input of source (removing its
    variant); GraphError for an input that is never empty."""
    graph = {n.id: n for n in nodes(document)}
    node = graph.get(target)
    entry = next((s for s in node.inputs if s.name == socket), None) if node else None
    if entry is None:
        raise GraphError(f"{target} has no input {socket!r}")
    variant = next((v for s, v in entry.extra if s == source), None)
    if variant is not None:
        return "remove", {"entry": variant}
    if entry.required:
        raise GraphError(f"the {entry.label} of {target} is never empty: link another one "
                         f"to it instead")
    if node.kind == "junction":
        return "set_junction", {"junction": target, "clear_central": True}
    return "set_param", {"entry": target, "name": socket, "value": None}


def layout(graph, places=None, width=180, height=110, gap=50):
    """{node id: [x, y]}: the column of its kind and its row in it, the
    columns without a node left out, unless places (the ui block's) keeps
    one moved by hand."""
    places = places or {}
    used = sorted({node.column for node in graph})
    out = {}
    for node in graph:
        place = places.get(node.id)
        if isinstance(place, (list, tuple)) and len(place) == 2 and \
                all(isinstance(v, (int, float)) for v in place):
            out[node.id] = [float(place[0]), float(place[1])]
        else:
            out[node.id] = [float(used.index(node.column) * (width + gap)),
                            float(node.row * height)]
    return out
