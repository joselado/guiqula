"""The junction (PLAN.md phase 9, part D): two leads and an optional central
region of the document, a target of calculations, planned as its left lead
with the other two named, refused when it would name the wrong systems."""
import json

import pytest

from guiqula.commands.dispatcher import CommandError, Dispatcher
from guiqula.core.document import Document
from guiqula.io import script
from guiqula.registry import graph, pipeline


def junction():
    d = Dispatcher(Document())
    left = d.do("add_system", lattice="chain")
    dot = d.do("add_system", lattice="chain", name="dot")
    j = d.do("add_junction", left=left, central=dot)
    right = d.document.junction(j).right
    d.do("add_term", system=right, kind="swave", params={"delta": 0.1})
    c = d.do("add_calculation", system=j, kind="junction_didv")
    return d, left, right, dot, j, c


def test_a_new_junction_copies_its_lead_on_the_same_geometry():
    d, left, right, dot, j, c = junction()
    assert d.document.system(right).geometry == d.document.system(left).geometry
    assert d.document.system(right).name.endswith("(right lead)")
    data = json.loads(d.document.to_json())
    assert data["junctions"] == [{"id": j, "name": j, "left": left, "right": right,
                                  "central": dot}]
    assert "junctions" not in Dispatcher().document.to_json()        # left out while empty
    assert Document.from_json(d.document.to_json()).junction(j).central == dot


def test_a_calculation_on_a_junction_is_planned_on_its_leads():
    d, left, right, dot, j, c = junction()
    plan = pipeline.plan_calculation(d.document, c)
    assert plan.problem is None and plan.junction == j and plan.system_id == left
    assert set(plan.others) == {"right", "central"}
    key = plan.key
    d.do("add_term", system=right, kind="onsite", params={"mu": 0.1})   # the right lead
    assert pipeline.calculation_key(d.document, c) != key
    d.do("set_junction", junction=j, clear_central=True)
    plan = pipeline.plan_calculation(d.document, c)
    assert plan.problem is None and set(plan.others) == {"right"}
    text = script.export_script(d.document, c)
    assert "central = None" in text and "junction_of(h, right, central" in text


def test_what_a_junction_refuses():
    d, left, right, dot, j, c = junction()
    with pytest.raises(CommandError, match="three systems"):
        d.do("set_junction", junction=j, central=left)
    with pytest.raises(CommandError, match="junctions"):
        d.do("remove", entry=right)                       # a lead of the junction
    with pytest.raises(CommandError, match="used by calculations"):
        d.do("remove", entry=j)
    spins = d.do("add_system", lattice="chain", kind="classical_spin")
    with pytest.raises(CommandError, match="quantum"):
        d.do("set_junction", junction=j, right=spins)
    with pytest.raises(CommandError, match="does not apply"):
        d.do("add_calculation", system=left, kind="junction_didv")    # a junction's only


def test_the_junction_in_the_graph():
    d, left, right, dot, j, c = junction()
    nodes = {n.id: n for n in graph.nodes(d.document)}
    sockets = {s.name: s for s in nodes[j].inputs}
    assert sockets["left"].source == left and not sockets["central"].required
    assert {s.accepts for s in nodes[c].inputs if s.name == "target"} == {("junction",)}
    assert graph.cut(d.document, j, "central") == ("set_junction",
                                                   {"junction": j, "clear_central": True})
    other = d.do("add_system", lattice="chain")
    name, args = graph.connect(d.document, other, j, "left")
    d.do(name, **args)
    assert d.document.junction(j).left == other
