"""Variants: one calculation on two inputs, one Hamiltonian on two
geometries (a second link drawn onto an input of the node view). A variant
is an ordinary entry that follows its original, so everything downstream of
it works as for any other."""
import json

import pytest

from guiqula.commands.dispatcher import CommandError, Dispatcher
from guiqula.core.document import Document, variants_of
from guiqula.registry import pipeline


def two_hamiltonians():
    d = Dispatcher(Document())
    s1 = d.do("add_system", lattice="honeycomb_lattice")
    s2 = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_term", system=s2, kind="sublattice_imbalance", params={"mass": 0.3})
    c = d.do("add_calculation", system=s1, kind="dos", params={"ne": 20})
    return d, s1, s2, c


def test_a_calculation_on_two_hamiltonians():
    d, s1, s2, c = two_hamiltonians()
    v = d.do("add_variant", entry=c, target=s2)
    calc = d.document.calculation(v)
    assert calc.variant_of == c and calc.system == s2 and variants_of(d.document, c) == [v]
    assert json.loads(d.document.to_json())["calculations"][-1] == {
        "id": v, "system": s2, "kind": "dos", "variant_of": c}       # no parameters of its own
    plan = pipeline.plan_calculation(d.document, v)
    assert plan.problem is None and plan.params["ne"] == 20 and plan.system_id == s2
    assert plan.key != pipeline.calculation_key(d.document, c)       # another Hamiltonian
    d.do("set_param", entry=v, name="ne", value=30)                 # edits the original
    assert d.document.calculation(c).params["ne"] == 30
    assert pipeline.plan_calculation(d.document, v).params["ne"] == 30
    with pytest.raises(CommandError, match="already"):
        d.do("add_variant", entry=c, target=s2)
    with pytest.raises(CommandError, match="variants"):
        d.do("remove", entry=c)
    d.do("remove", entry=v)
    d.do("remove", entry=c)
    assert Document.from_json(d.document.to_json()).to_json() == d.document.to_json()


def test_a_hamiltonian_on_two_geometries_and_its_calculations_follow():
    d, s1, s2, c = two_hamiltonians()
    other = d.do("add_geometry", lattice="honeycomb_lattice")
    d.do("add_geometry_op", system=other, kind="supercell", params={"n": [2, 2, 1]})
    v = d.do("add_variant", entry=s1, target=other)
    system = d.document.system(v)
    assert system.variant_of == s1 and system.geometry == other and system.hamiltonian is None
    follow = [x.id for x in d.document.calculations if x.variant_of == c]
    assert len(follow) == 1 and d.document.calculation(follow[0]).system == v
    d.do("add_term", system=v, kind="onsite", params={"mu": 0.2})   # the original's terms
    assert [t.kind for t in d.document.system(s1).hamiltonian.terms] == ["onsite"]
    plan = pipeline.plan_system(d.document, v)
    assert plan.problem is None and [s.kind for s in plan.stages][-2:] == ["onsite",
                                                                          "interactions"]
    assert plan.key != pipeline.plan_system(d.document, s1).key      # another geometry
    later = d.do("add_calculation", system=s1, kind="bands")        # follows too
    assert [x.system for x in d.document.calculations if x.variant_of == later] == [v]
    d.do("remove", entry=v)                                          # its variants go with it
    assert all(x.system != v for x in d.document.calculations)
