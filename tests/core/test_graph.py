"""The Document as a graph (PLAN.md phase 9, part C): the nodes and their
sockets read from the declarations, the solid, dashed and dotted links, the
Command a link drawn by hand is, and what is refused."""
import pytest

from guiqula.commands.dispatcher import Dispatcher
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
                           "geometry"))
    assert d.document.system(ids["tip"]).geometry == d.document.system(other).geometry
    apply(d, graph.connect(d.document, other, ids["bands"], "target"))
    assert d.document.calculation(ids["bands"]).system == other
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
