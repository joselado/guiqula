"""The dispatcher: mutations with undo, actions with a journal (PLAN.md 3.5,
decision 14.7)."""
import pytest

from guiqula.commands import CommandError, Dispatcher


def test_undo_redo_and_journal():
    d = Dispatcher()
    events = []
    d.subscribe(events.append)
    s = d.do("add_system", lattice="honeycomb_lattice")
    t = d.do("add_term", system=s, kind="rashba")
    snapshot = d.document.to_json()
    d.do("set_param", entry=t, name="c", value=0.3)
    d.undo()
    assert d.document.to_json() == snapshot
    d.redo()
    assert d.document.find(t)[-1].params == {"c": 0.3}
    assert [e["type"] for e in events] == ["mutation", "mutation", "mutation", "undo", "redo"]
    assert [e["type"] for e in d.journal] == [e["type"] for e in events]


def test_refused_command_changes_nothing():
    d = Dispatcher()
    s = d.do("add_system")
    snapshot = d.document.to_json()
    for name, args in [("add_term", dict(system=s, kind="zeeman", params={"m": [0, 0]})),
                       ("add_term", dict(system=s, kind="nope")),
                       ("set_param", dict(entry=s, name="nope", value=1)),
                       ("add_term", dict(system="s9", kind="onsite")),
                       ("add_term", dict(system=s, kind="onsite", region="r1")),
                       ("add_system", dict(lattice="nope")),
                       ("nope", {})]:
        with pytest.raises(CommandError):
            d.do(name, **args)
    assert d.document.to_json() == snapshot and not d.can_redo()


def test_references_are_protected():
    d = Dispatcher()
    s = d.do("add_system")
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x > 0"})
    t = d.do("add_term", system=s, kind="onsite", region=r)
    d.do("add_calculation", system=s, kind="dos")
    with pytest.raises(CommandError, match="used by"):
        d.do("remove", entry=r)
    with pytest.raises(CommandError, match="used by calculations"):
        d.do("remove", entry=s)
    d.do("set_region", entry=t, region=None)
    d.do("remove", entry=r)


def test_move_and_enable():
    d = Dispatcher()
    s = d.do("add_system")
    t1 = d.do("add_term", system=s, kind="onsite")
    t2 = d.do("add_term", system=s, kind="rashba")
    d.do("move", entry=t2, index=0)
    assert [t.id for t in d.document.system(s).hamiltonian.terms] == [t2, t1]
    d.do("set_enabled", entry=t1, enabled=False)
    assert d.document.find(t1)[-1].enabled is False


def test_duplicate():
    d = Dispatcher()
    s = d.do("add_system", name="flake")
    op = d.do("add_geometry_op", system=s, kind="supercell", params={"n": [2, 2, 1]})
    d.do("add_geometry_op", system=s, kind="ribbon")
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x > 0"}, name="right")
    t = d.do("add_term", system=s, kind="onsite", params={"mu": 0.3}, region=r)
    c = d.do("add_calculation", system=s, kind="dos")
    op2 = d.do("duplicate", entry=op)
    assert [o.id for o in d.document.system(s).geometry.ops] == [op, op2, "op2"]
    assert d.document.find(op2)[-1].params == {"n": [2, 2, 1]}
    r2 = d.do("duplicate", entry=r)
    assert d.document.find(r2)[-1].name == "right (copy)"
    c2 = d.do("duplicate", entry=c)
    assert d.document.find(c2)[-1].system == s
    s2 = d.do("duplicate", entry=s)
    copy = d.document.system(s2)
    assert copy.name == "flake (copy)" and d.document.systems[1] is copy
    ids = d.document.all_ids()
    assert len(ids) == len(set(ids))
    term = copy.hamiltonian.terms[0]
    assert term.id != t and term.region == copy.regions[0].id != r
    d.undo()
    assert [x.id for x in d.document.systems] == [s]


def test_actions_are_journaled_not_undoable():
    d = Dispatcher()
    calls = []
    d.register_action("ping", lambda value: calls.append(value) or value * 2)
    assert d.act("ping", value=21) == 42
    assert calls == [21] and not d.can_undo()
    assert d.journal[-1]["type"] == "action" and d.journal[-1]["result"] == 42
    assert d.run("add_system") == "s1"               # run() routes both kinds
    with pytest.raises(CommandError, match="JSON"):
        d.act("ping", value=object())


def test_introspection_lists_signatures():
    d = Dispatcher()
    assert d.mutations()["set_param"] == ["entry", "name", "value"]
    d.register_action("run_calculation", lambda calculation, wait=False: None)
    assert d.actions()["run_calculation"] == ["calculation", "wait=False"]


def test_regions_used_by_piecewise_fields():
    d = Dispatcher()
    s = d.do("add_system")
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x > 0"})
    t = d.do("add_term", system=s, kind="onsite", params={"mu": {
        "kind": "piecewise", "default": 0.0, "pieces": [{"region": r, "value": 0.2}]}})
    d.do("set_meanfield", system=s, params={"U": {
        "kind": "piecewise", "default": 1.0, "pieces": [{"region": r, "value": 2.0}]}})
    with pytest.raises(CommandError, match=rf"used by \['{t}', '{s}/meanfield'\]"):
        d.do("remove", entry=r)
    copy = d.do("duplicate", entry=s)
    system = d.document.system(copy)
    new = system.regions[0].id
    assert new != r
    assert system.hamiltonian.terms[0].params["mu"]["pieces"][0]["region"] == new
    assert system.hamiltonian.meanfield.params["U"]["pieces"][0]["region"] == new


def test_merged_mutations_are_one_undo_step():
    """A slider drag: many set_param with one merge key, one undo step."""
    from guiqula.commands import Dispatcher
    d = Dispatcher()
    s = d.do("add_system")
    t = d.do("add_term", system=s, kind="onsite", params={"mu": 0.1})
    for value in (0.2, 0.3, 0.4):
        d.do_merged("slider:t1.mu", "set_param", entry=t, name="mu", value=value)
    d.do_merged("slider:other", "set_param", entry=t, name="mu", value=0.5)
    assert d.document.find(t)[-1].params["mu"] == 0.5
    d.undo()
    assert d.document.find(t)[-1].params["mu"] == 0.4
    d.undo()                                         # the whole first drag
    assert d.document.find(t)[-1].params["mu"] == 0.1
    d.redo()
    d.do_merged("slider:t1.mu", "set_param", entry=t, name="mu", value=0.6)   # after a redo:
    d.undo()                                                                  # a new step
    assert d.document.find(t)[-1].params["mu"] == 0.4
