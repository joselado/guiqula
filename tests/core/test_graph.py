"""The Document as a graph (PLAN.md phase 9, part C): the nodes and their
sockets read from the declarations, the solid, dashed and dotted links, the
Command a link drawn by hand is, and what is refused."""
import pytest

from guiqula.commands.dispatcher import CommandError, Dispatcher
from guiqula.core.document import Document
from guiqula.registry import graph


def document():
    """A Hamiltonian and a tip on one geometry each, the bands of the first
    on a k-path, a local probe with the tip, an embedding of a defect, a
    classical model whose texture the first reads, and a sweep."""
    d = Dispatcher(Document())
    s1 = d.do("add_system", lattice="chain")
    tip = d.do("add_system", lattice="chain", name="tip")
    bands = d.do("add_calculation", system=s1, kind="bands")
    probe = d.do("add_calculation", system=s1, kind="local_probe", params={"probe": tip})
    e = d.do("add_embedding", pristine=s1)
    spins = d.do("add_system", lattice="chain", kind="classical_spin")
    texture = d.do("add_calculation", system=spins, kind="minimize_spins")
    d.do("add_term", system=s1, kind="zeeman", params={"m": [0.0, 0.0, {
        "kind": "from_result", "calculation": texture, "array": "m", "component": 2}]})
    t1 = d.document.system(s1).hamiltonian.terms[-1].id
    gap = d.do("add_calculation", system=s1, kind="gap")
    sweep = d.do("add_calculation", system=s1, kind="sweep", params={
        "calculation": gap, "entry": t1, "param": "m", "component": 0})
    return d, dict(s1=s1, tip=tip, bands=bands, probe=probe, e=e, spins=spins,
                   texture=texture, gap=gap, sweep=sweep)


def test_the_nodes_and_their_sockets_come_from_the_declarations():
    d, ids = document()
    nodes = {n.id: n for n in graph.nodes(d.document)}
    assert [n.kind for n in graph.nodes(d.document)][:2] == ["geometry", "geometry"]
    assert nodes[ids["s1"]].title == "Hamiltonian" and nodes[ids["spins"]].title == "Model"
    probe = {s.name: s for s in nodes[ids["probe"]].inputs}
    assert probe["target"].accepts == ("system",) and probe["target"].required
    assert probe["probe"].accepts == ("system",) and not probe["probe"].required  # optional
    bands = {s.name: s for s in nodes[ids["bands"]].inputs}
    assert bands["kpath"].accepts == ("kpath",) and bands["kpath"].source.startswith("k")
    embedding = {s.name: s.source for s in nodes[ids["e"]].inputs}
    assert embedding == {"pristine": ids["s1"], "defect": d.document.embedding(ids["e"]).defect}
    columns = {n.kind: n.column for n in nodes.values()}
    assert columns["geometry"] < columns["system"] < columns["calculation"]


def test_the_links():
    d, ids = document()
    links = graph.links(d.document)
    solid = {(l.source, l.target, l.socket) for l in links if l.style == "solid"}
    geometry = d.document.system(ids["s1"]).geometry
    assert (geometry, ids["s1"], "geometry") in solid
    assert (ids["tip"], ids["probe"], "probe") in solid
    assert (ids["s1"], ids["e"], "pristine") in solid
    dotted = {(l.source, l.target) for l in links if l.style == "dotted"}
    assert dotted == {(ids["sweep"], ids["gap"]), (ids["sweep"], ids["s1"])}  # runs, moves
    dashed = {(l.source, l.target) for l in links if l.style == "dashed"}
    assert dashed == {(ids["texture"], ids["s1"])}          # the texture the Zeeman term reads


def test_a_link_drawn_is_one_command():
    d, ids = document()
    k2 = d.do("add_kpath", vertices=["G", "X"])
    name, args = graph.connect(d.document, k2, ids["bands"], "kpath")
    assert (name, args) == ("set_param", {"entry": ids["bands"], "name": "kpath", "value": k2})
    d.do(name, **args)
    assert d.document.calculation(ids["bands"]).params["kpath"] == k2
    other = d.do("add_system", lattice="square_lattice")
    apply(d, graph.connect(d.document, d.document.system(other).geometry, ids["tip"],
                           "geometry", replace=True))           # Ctrl: moved
    assert d.document.system(ids["tip"]).geometry == d.document.system(other).geometry
    apply(d, graph.connect(d.document, other, ids["bands"], "target", replace=True))
    assert d.document.calculation(ids["bands"]).system == other


def test_a_second_input_is_a_variant():
    """A link dropped onto a calculation's target, or a system's geometry,
    that has one adds an input: a variant, drawn into the same socket."""
    d, ids = document()
    other = d.do("add_system", lattice="chain")
    name, args = graph.connect(d.document, other, ids["bands"], "target")
    assert (name, args) == ("add_variant", {"entry": ids["bands"], "target": other})
    variant = apply(d, (name, args))
    nodes = {n.id: n for n in graph.nodes(d.document)}
    assert variant not in nodes                                    # no node of its own
    socket = next(s for s in nodes[ids["bands"]].inputs if s.name == "target")
    assert socket.extra == [(other, variant)]
    assert (other, ids["bands"], "target") in {(l.source, l.target, l.socket)
                                               for l in graph.links(d.document)}
    with pytest.raises(graph.GraphError, match="already"):
        graph.connect(d.document, other, ids["bands"], "target")
    assert graph.cut(d.document, ids["bands"], "target", other) == ("remove",
                                                                     {"entry": variant})
    geometry = d.do("add_geometry", lattice="chain")
    hamiltonian = apply(d, graph.connect(d.document, geometry, ids["s1"], "geometry"))
    nodes = {n.id: n for n in graph.nodes(d.document)}
    assert hamiltonian not in nodes
    assert next(s for s in nodes[ids["s1"]].inputs).extra == [(geometry, hamiltonian)]
    apply(d, graph.cut(d.document, ids["probe"], "probe"))           # optional: the default
    assert d.document.calculation(ids["probe"]).params["probe"] is None


def apply(d, command):
    name, args = command
    return d.do(name, **args)


@pytest.mark.parametrize("source, target, socket, message", [
    ("bands", "s1", "geometry", "takes a geometry"),
    ("spins", "probe", "probe", "quantum"),
    ("s1", "bands", "kpath", "takes a kpath"),
    ("s1", "s1", "nope", "no input"),
])
def test_a_link_the_declarations_do_not_take_is_refused(source, target, socket, message):
    d, ids = document()
    with pytest.raises(graph.GraphError, match=message):
        graph.connect(d.document, ids[source], ids[target], socket)


def test_an_input_never_empty_is_not_cut():
    d, ids = document()
    with pytest.raises(graph.GraphError, match="never empty"):
        graph.cut(d.document, ids["bands"], "kpath")


def test_the_layout_keeps_a_place_moved_by_hand():
    d, ids = document()
    nodes = graph.nodes(d.document)
    places = graph.layout(nodes, {ids["s1"]: [500, 40]})
    assert places[ids["s1"]] == [500.0, 40.0]
    first = next(n for n in nodes if n.kind == "geometry")
    assert places[first.id] == [0.0, 0.0]


# ---- variants in the node view: every calculation is drawn, every input is a node
def audit(document):
    """What the node view cannot show: a calculation that is neither a node
    nor a further input of one, a socket naming no node, a link drawn twice."""
    nodes = graph.nodes(document)
    ids = {n.id for n in nodes}
    drawn = ids | {v for n in nodes for s in n.inputs for _, v in s.extra}
    follows = {s.id: s.variant_of for s in document.systems if s.variant_of is not None}
    drawn |= {c.id for c in document.calculations if c.variant_of is not None   # with the
              and follows.get(c.system) == document.calculation(c.variant_of).system}  # system
    problems = [f"{c.id} drawn nowhere" for c in document.calculations if c.id not in drawn]
    problems += [f"{n.id}.{s.name} -> {s.source}" for n in nodes for s in n.inputs
                 if s.source is not None and s.source not in ids]
    solid = [(l.source, l.target, l.socket) for l in graph.links(document, nodes)
             if l.style == "solid"]
    problems += [f"twice {link}" for link in set(solid) if solid.count(link) > 1]
    return problems


def variant_on_a_geometry():
    """s1 on two geometries (its variant s3 on geo3), c1 on s1 and so on s3
    too (its variant c2), and s2 beside them."""
    d = Dispatcher(Document())
    s1, s2 = d.do("add_system", lattice="chain"), d.do("add_system", lattice="chain")
    geometry = d.do("add_geometry", lattice="chain")
    c1 = d.do("add_calculation", system=s1, kind="bands")
    s3 = apply(d, graph.connect(d.document, geometry, s1, "geometry"))
    c2 = next(c.id for c in d.document.calculations if c.variant_of == c1)
    return d, s1, s2, s3, geometry, c1, c2


def test_a_moved_calculation_follows_the_variants_of_its_new_system():
    d, s1, s2, s3, geometry, c1, c2 = variant_on_a_geometry()
    apply(d, graph.connect(d.document, s2, c1, "target", replace=True))
    calcs = [(c.id, c.system, c.variant_of) for c in d.document.calculations]
    assert calcs == [(c1, s2, None)]                # its variant on s3 followed s1, so it went
    assert audit(d.document) == []
    d.undo()
    c3 = d.do("add_calculation", system=s2, kind="dos")
    apply(d, graph.connect(d.document, s1, c3, "target", replace=True))
    follow = [c for c in d.document.calculations if c.variant_of == c3]
    assert [c.system for c in follow] == [s3]       # it runs on every variant of s1
    assert audit(d.document) == []
    d.do("remove", entry=follow[0].id)
    d.do("remove", entry=c3)
    with pytest.raises(CommandError, match="variant of"):
        d.do("set_calculation_system", calculation=c2, system=s2)


def test_a_variant_left_behind_by_an_older_file_is_drawn_from_its_system():
    d, s1, s2, s3, geometry, c1, c2 = variant_on_a_geometry()
    document = d.document.model_copy(deep=True)
    document.calculation(c1).system = s2            # as set_calculation_system left it
    target = next(s for n in graph.nodes(document) if n.id == c1 for s in n.inputs
                  if s.name == "target")
    assert target.extra == [(s1, c2)]
    assert audit(document) == []
    assert graph.cut(document, c1, "target", s1) == ("remove", {"entry": c2})


def test_a_replace_onto_the_input_of_a_variant_is_refused():
    d = Dispatcher(Document())
    s1, s2 = d.do("add_system", lattice="chain"), d.do("add_system", lattice="chain")
    c1 = d.do("add_calculation", system=s1, kind="bands")
    apply(d, graph.connect(d.document, s2, c1, "target"))
    with pytest.raises(graph.GraphError, match="already"):
        graph.connect(d.document, s2, c1, "target", replace=True)
    with pytest.raises(CommandError, match="runs on s2 already"):
        d.do("set_calculation_system", calculation=c1, system=s2)
    geometry = d.do("add_geometry", lattice="chain")
    s3 = apply(d, graph.connect(d.document, geometry, s1, "geometry"))
    with pytest.raises(graph.GraphError, match="already"):
        graph.connect(d.document, geometry, s1, "geometry", replace=True)
    with pytest.raises(CommandError, match="built on geo3 already"):
        d.do("set_geometry", system=s1, geometry=geometry)
    with pytest.raises(CommandError, match="built on geo1 already"):
        d.do("set_geometry", system=s3, geometry=d.document.system(s1).geometry)
    assert audit(d.document) == []


def test_the_copy_of_a_variant_is_an_entry_of_its_own():
    d = Dispatcher(Document())
    s1, s2 = d.do("add_system", lattice="chain"), d.do("add_system", lattice="chain")
    c1 = d.do("add_calculation", system=s1, kind="bands")
    c2 = d.do("add_variant", entry=c1, target=s2)
    c3 = d.do("duplicate", entry=c2)
    copy = d.document.calculation(c3)
    assert copy.variant_of is None and copy.system == s2 and copy.kind == "bands"
    assert copy.params == d.document.calculation(c1).params
    d.do("add_term", system=s1, kind="onsite", region=None)
    geometry = d.do("add_geometry", lattice="chain")
    s3 = d.do("add_variant", entry=s1, target=geometry)
    follow = next(c.id for c in d.document.calculations if c.variant_of == c1 and c.system == s3)
    with pytest.raises(CommandError, match="duplicate c1 instead"):
        d.do("duplicate", entry=follow)
    c5 = d.do("duplicate", entry=c1)                # the copy of c1 follows s1's variant too
    assert [c.system for c in d.document.calculations if c.variant_of == c5] == [s3]
    for command in ("duplicate", "duplicate_linked"):
        key = "entry" if command == "duplicate" else "system"
        new = d.do(command, **{key: s3})
        copy = d.document.system(new)
        assert copy.variant_of is None and len(copy.hamiltonian.terms) == 1
        assert copy.hamiltonian.terms[0].id != d.document.system(s1).hamiltonian.terms[0].id
        assert (copy.geometry == geometry) == (command == "duplicate_linked")
        d.do("add_term", system=copy.id, kind="onsite")       # its own, not s1's
        assert len(d.document.system(s1).hamiltonian.terms) == 1
    assert audit(d.document) == []


@pytest.mark.parametrize("command, args", [
    ("add_calculation", {"kind": "bands", "system": "{v}"}),
    ("add_embedding", {"pristine": "{v}"}),
    ("add_embedding", {"pristine": "s1", "defect": "{v}"}),
    ("add_junction", {"left": "{v}"}),
    ("add_calculation", {"system": "s1", "kind": "local_probe", "params": {"probe": "{v}"}}),
    ("set_param", {"entry": "c1", "name": "probe", "value": "{v}"}),
    ("add_variant", {"entry": "c1", "target": "{v}"}),
])
def test_a_variant_is_named_by_nothing_but_its_original(command, args):
    """A variant is no node: naming it as a target, a lead, a tip or a system
    of an embedding would draw a socket linked to nothing."""
    d = Dispatcher(Document())
    d.do("add_system", lattice="chain")
    v = d.do("add_variant", entry="s1", target=d.do("add_geometry", lattice="chain"))
    d.do("add_system", lattice="chain")
    d.do("add_calculation", system="s3", kind="local_probe")   # c1, on another system
    args = {k: (val.format(v=v) if isinstance(val, str) else
                {n: x.format(v=v) for n, x in val.items()} if isinstance(val, dict) else val)
            for k, val in args.items()}
    with pytest.raises(CommandError, match=f"{v} is a variant of s1"):
        d.do(command, **args)
    assert audit(d.document) == []


def test_a_variant_needs_the_regions_of_its_original():
    d = Dispatcher(Document())
    s1 = d.do("add_system", lattice="chain")
    geometry = d.do("add_geometry", lattice="chain")
    region = d.do("add_region", system=s1, select={"kind": "expression", "expr": "x > 0"})
    d.do("add_term", system=s1, kind="onsite", region=region)
    with pytest.raises(CommandError, match="does not have"):
        d.do("set_geometry", system=s1, geometry=geometry)
    with pytest.raises(CommandError, match=r"geometry of 's2' \(a variant of 's1'\)"):
        apply(d, graph.connect(d.document, geometry, s1, "geometry"))  # add_variant
    d.do("remove", entry=d.document.system(s1).hamiltonian.terms[0].id)
    d.do("add_variant", entry=s1, target=geometry)
    with pytest.raises(CommandError, match="a variant of"):
        d.do("add_term", system=s1, kind="onsite", region=region)


def test_the_tip_of_a_probe_is_not_the_system_it_runs_on():
    d = Dispatcher(Document())
    s1, s2, s3 = (d.do("add_system", lattice="chain") for _ in range(3))
    c1 = d.do("add_calculation", system=s1, kind="local_probe")
    with pytest.raises(graph.GraphError, match="the system it runs on"):
        graph.connect(d.document, s1, c1, "probe")
    d.do("add_variant", entry=c1, target=s3)
    with pytest.raises(graph.GraphError, match="the system it runs on"):
        graph.connect(d.document, s3, c1, "probe")    # its variant runs on s3
    assert graph.connect(d.document, s2, c1, "probe") == (
        "set_param", {"entry": c1, "name": "probe", "value": s2})


def test_a_variant_is_not_made_on_the_tip_of_its_probe():
    d = Dispatcher(Document())
    s1, s2 = (d.do("add_system", lattice="chain") for _ in range(2))
    c1 = d.do("add_calculation", system=s1, kind="local_probe", params={"probe": s2})
    for replace in (False, True):    # a variant, or a move onto the tip
        with pytest.raises(graph.GraphError, match="names s2 as its tip"):
            graph.connect(d.document, s2, c1, "target", replace=replace)
    with pytest.raises(CommandError, match="names s2 as its tip"):
        d.do("add_variant", entry=c1, target=s2)
    assert not [c for c in d.document.calculations if c.variant_of == c1]


def test_the_k_paths_sit_under_the_systems():
    """A k-path is in the systems' column, below them (decision 272), so its
    link to a calculation crosses no system."""
    d = Dispatcher(Document())
    for _ in range(3):
        d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_calculation", system="s1", kind="bands")
    nodes = {n.id: n for n in graph.nodes(d.document)}
    assert nodes["k1"].column == nodes["s1"].column
    assert nodes["k1"].row == 3 and [nodes[s].row for s in ("s1", "s2", "s3")] == [0, 1, 2]
    assert [nodes[g].row for g in ("geo1", "geo2", "geo3")] == [0, 1, 2]
    where = graph.layout(list(nodes.values()))
    assert where["k1"][1] > max(where[s][1] for s in ("s1", "s2", "s3"))
