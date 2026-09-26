"""The registry catalogue (PLAN.md 3.2) and the planning half of the engine."""
import pytest

from guiqula import registry
from guiqula.commands import Dispatcher
from guiqula.registry import pipeline
from guiqula.registry.params import FieldParam, FloatParam, IntParam


def test_catalogue():
    assert "honeycomb_lattice" in registry.kinds("lattice")
    assert {"supercell", "ribbon", "remove_atoms"} <= set(registry.kinds("geometry_op"))
    assert {"zeeman", "rashba", "onsite", "haldane"} <= set(registry.kinds("term"))
    assert {"bands", "dos"} <= set(registry.kinds("calculation"))
    for spec in registry.entries():
        assert spec.describe()["kind"] == spec.kind


@pytest.mark.parametrize("spec", registry.entries("term"), ids=lambda s: s.kind)
def test_term_numbers_are_fields(spec):
    """Every numeric term parameter is a Field (CLAUDE.md hard rule)."""
    for p in spec.params:
        if isinstance(p, (FloatParam, IntParam)) and p.type_name != "seed":
            pytest.fail(f"{spec.kind}.{p.name} is a bare number, not a Field")


def test_stochastic_terms_have_seeds():
    assert registry.get("term", "anderson_disorder").seed_param is not None


def pipeline_doc():
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_construction", system=s, has_spin=False)
    op = d.do("add_geometry_op", system=s, kind="supercell", params={"n": [2, 2, 1]})
    t1 = d.do("add_term", system=s, kind="onsite")
    t2 = d.do("add_term", system=s, kind="zeeman")
    c = d.do("add_calculation", system=s, kind="bands")
    return d, s, op, t1, t2, c


def test_mode_prescan():
    d, s, op, t1, t2, c = pipeline_doc()
    plan = pipeline.plan_system(d.document, s)
    assert plan.mode == "spinful" and plan.upgraded_by == [t2]
    assert plan.construction["has_spin"] is True
    d.do("set_enabled", entry=t2, enabled=False)          # disabled: no upgrade
    plan = pipeline.plan_system(d.document, s)
    assert plan.mode == "spinless" and plan.upgraded_by == []


def test_keys_follow_physics_only():
    d, s, op, t1, t2, c = pipeline_doc()
    key = pipeline.calculation_key(d.document, c)
    d.do("rename", entry=s, name="another name")
    d.do("move", entry=c, index=0)
    assert pipeline.calculation_key(d.document, c) == key         # cosmetics
    d.do("set_param", entry=op, name="n", value=[3, 2, 1])
    assert pipeline.calculation_key(d.document, c) != key         # upstream edit: stale
    d.undo()
    assert pipeline.calculation_key(d.document, c) == key         # fresh again
    d.do("set_enabled", entry=t1, enabled=False)
    off = pipeline.calculation_key(d.document, c)
    d.do("remove", entry=t1)
    assert pipeline.calculation_key(d.document, c) == off         # disabled == absent


def test_keys_follow_references():
    """A term restricted to a region depends on the region's selection
    (DAG-aware keys, decision 14.9)."""
    d, s, op, t1, t2, c = pipeline_doc()
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x < 0"})
    d.do("set_region", entry=t1, region=r)
    key = pipeline.calculation_key(d.document, c)
    d.do("rename", entry=r, name="left half")
    assert pipeline.calculation_key(d.document, c) == key
    d.do("set_selection", entry=r, select={"kind": "expression", "expr": "x < 1"})
    assert pipeline.calculation_key(d.document, c) != key


def test_invalid_entries_are_flagged_not_removed():
    d, s, op, t1, t2, c = pipeline_doc()
    data = d.document.model_dump()
    data["systems"][0]["hamiltonian"]["terms"].append(
        {"id": "t9", "kind": "no_such_term", "params": {}})
    data["systems"][0]["hamiltonian"]["terms"].append(
        {"id": "t10", "kind": "rashba", "params": {"c": "x +"}})
    data["systems"][0]["hamiltonian"]["terms"].append(
        {"id": "t11", "kind": "anderson_disorder", "params": {}, "region": None})
    from guiqula.core.document import Document
    document = Document.from_data(data)
    plan = pipeline.plan_system(document, s)
    assert "unknown term 'no_such_term'" in plan.stage("t9").problem
    assert "syntax error" in plan.stage("t10").problem
    assert plan.stage("t11").problem is None
    assert plan.stage("t9").key == plan.stage(t2).key          # skipped: no effect


def test_region_on_constant_only_term_is_invalid():
    d, s, op, t1, t2, c = pipeline_doc()
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x < 0"})
    t = d.do("add_term", system=s, kind="anderson_disorder", region=r)
    assert "cannot be restricted to a region" in pipeline.plan_system(d.document, s).stage(t).problem
