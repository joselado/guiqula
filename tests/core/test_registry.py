"""The registry catalogue (PLAN.md 3.2) and the planning half of the engine."""
import pytest

from guiqula import registry
from guiqula.commands import Dispatcher
from guiqula.registry import pipeline
from guiqula.registry.params import FieldParam, FloatParam, IntParam, IntVectorParam


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
        if isinstance(p, (FloatParam, IntParam, IntVectorParam)) and p.type_name != "seed":
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


def test_piecewise_fields_resolve_regions():
    """A piecewise Field depends on the selections of its regions, not on
    their ids; a missing region makes the entry invalid (skipped)."""
    d, s, op, t1, t2, c = pipeline_doc()
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x < 0"})
    d.do("set_param", entry=t1, name="mu", value={
        "kind": "piecewise", "default": 0.0, "pieces": [{"region": r, "value": 0.3}]})
    plan = pipeline.plan_system(d.document, s)
    assert plan.stage(t1).problem is None and plan.stage(t1).regions == {
        r: {"kind": "expression", "expr": "x < 0"}}
    key = pipeline.calculation_key(d.document, c)
    d.do("set_selection", entry=r, select={"kind": "expression", "expr": "x < 1"})
    assert pipeline.calculation_key(d.document, c) != key
    d.undo()
    twin = d.do("duplicate", entry=r)                 # same selection, another id
    d.do("set_param", entry=t1, name="mu", value={
        "kind": "piecewise", "default": 0.0, "pieces": [{"region": twin, "value": 0.3}]})
    assert pipeline.calculation_key(d.document, c) == key
    with pytest.raises(Exception, match="does not have"):     # refused at the command
        d.do("set_param", entry=t1, name="mu", value={
            "kind": "piecewise", "default": 0.0, "pieces": [{"region": "r99", "value": 0.3}]})
    data = d.document.model_dump()
    data["systems"][0]["regions"][-1]["select"] = {"kind": "lasso"}   # a broken selection
    from guiqula.core.document import Document
    assert "unknown selection kind" in pipeline.plan_system(
        Document.from_data(data), s).stage(t1).problem


def test_meanfield_stage():
    """The mean field is the last stage and needs spin."""
    d, s, op, t1, t2, c = pipeline_doc()
    d.do("set_enabled", entry=t2, enabled=False)         # no Zeeman: spinless
    plan = pipeline.plan_system(d.document, s)
    stage = plan.meanfield
    assert stage.id == f"{s}/meanfield" and not stage.applied and plan.mode == "spinless"
    assert plan.stages[-1] is stage and stage.key == plan.stage(t2).key
    key = pipeline.calculation_key(d.document, c)
    d.do("set_meanfield", system=s, enabled=True, params={"U": 2.0})
    plan = pipeline.plan_system(d.document, s)
    assert plan.meanfield.applied and plan.mode == "spinful"
    assert plan.upgraded_by == [f"{s}/meanfield"]
    assert pipeline.calculation_key(d.document, c) != key
    before = plan.key
    d.do("set_meanfield", system=s, params={"U": 3.0})
    assert pipeline.plan_system(d.document, s).key != before
    assert d.document.system(s).hamiltonian.meanfield.params["U"] == 3.0
    d.do("set_meanfield", system=s, enabled=False)
    assert pipeline.calculation_key(d.document, c) == key               # disabled == absent
    with pytest.raises(Exception, match="mix"):
        d.do("set_meanfield", system=s, params={"mix": 0})
    with pytest.raises(Exception, match="constant"):
        d.do("set_meanfield", system=s, params={"V1": "x"})          # pyqula takes a number


def test_cost_estimate():
    from guiqula.registry import cost
    d, s, op, t1, t2, c = pipeline_doc()
    assert cost.estimate(d.document, c, {}) is None                     # not built yet
    small = cost.estimate(d.document, c, {s: {"dimension": 16, "dimensionality": 2, "sites": 8}})
    big = cost.estimate(d.document, c, {s: {"dimension": 4000, "dimensionality": 2,
                                            "sites": 2000}})
    assert small["seconds"] < 1 < cost.SLOW < big["seconds"] and small["meanfield"] == 0
    d.do("set_meanfield", system=s, enabled=True)
    with_mf = cost.estimate(d.document, c, {s: {"dimension": 16, "dimensionality": 2, "sites": 8}})
    assert with_mf["meanfield"] > 0 and with_mf["seconds"] > small["seconds"]
    assert cost.describe(0.2) == "under a second" and cost.describe(600) == "about 10 min"
