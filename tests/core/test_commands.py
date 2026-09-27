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


def test_the_journal_keeps_one_record_per_merged_step_and_is_bounded(monkeypatch):
    """A brush stroke sets the whole painted Field at every mouse move: the
    journal keeps the stroke's last value only, not a copy per move."""
    from guiqula.commands import dispatcher
    d = Dispatcher()
    s = d.do("add_system")
    t = d.do("add_term", system=s, kind="onsite", params={"mu": 0.1})
    for stroke in range(2):
        for value in (0.2, 0.3, 0.4):
            d.do_merged("paint", "set_param", entry=t, name="mu", value=value + stroke)
        d.end_merge()
    values = [e["args"].get("value") for e in d.journal]
    assert values == [None, None, 0.4, 1.4]
    monkeypatch.setattr(dispatcher, "JOURNAL_LIMIT", 5)
    for value in range(10):
        d.do("set_param", entry=t, name="mu", value=float(value))
    assert [e["args"]["value"] for e in d.journal] == [5.0, 6.0, 7.0, 8.0, 9.0]


def test_one_journal_record_per_merged_step_whatever_actions_come_between():
    """With auto re-run on, the window runs the stale calculations after
    the rebuild that follows each slider move: the runs came between the
    moves, and every move of the drag kept its record."""
    d = Dispatcher()
    s = d.do("add_system")
    t = d.do("add_term", system=s, kind="onsite", params={"mu": 0.1})
    d.register_action("run_calculation", lambda calculation: None)
    for stroke in range(2):
        for step in range(50):
            d.do_merged("slider", "set_param", entry=t, name="mu", value=step + 100.0 * stroke)
            d.act("run_calculation", calculation="c1")
        d.end_merge()
    mutations = [e["args"].get("value") for e in d.journal if e["type"] == "mutation"]
    assert mutations == [None, None, 49.0, 149.0]
    assert sum(e["type"] == "action" for e in d.journal) == 100
    assert d.journal[-2]["args"]["value"] == 149.0       # the step's record is its last move
    d.do("set_param", entry=t, name="mu", value=0.5)      # a mutation in between ends a step
    d.do_merged("slider", "set_param", entry=t, name="mu", value=0.6)
    assert [e["args"].get("value") for e in d.journal if e["type"] == "mutation"][-3:] == \
        [149.0, 0.5, 0.6]


def test_a_failing_listener_does_not_make_a_done_command_look_refused(monkeypatch):
    """The mutation is done when the listeners are told: one that raised
    made do() raise too, so the window logged a refusal for an edit that was
    applied and on the undo stack, and the listeners after it were never
    told. Its error goes to sys.excepthook instead."""
    import sys
    reported, told = [], []
    monkeypatch.setattr(sys, "excepthook", lambda kind, value, tb: reported.append(kind))
    d = Dispatcher()
    d.subscribe(lambda event: 1 / 0)
    d.subscribe(told.append)
    assert d.do("add_system") == "s1"
    d.undo()
    assert [e["type"] for e in told] == ["mutation", "undo"]
    assert reported == [ZeroDivisionError, ZeroDivisionError] and d.can_redo()


def test_json_arguments_are_not_coerced():
    """Arguments come as JSON from the remote API and the console: "false"
    was read by bool() as true (a request to disable a term left it
    enabled), and a null note became the text "None". A number that is not
    finite or too large raised OverflowError instead of a refusal."""
    from guiqula.io import project
    d = Dispatcher(project.load("honeycomb_zeeman_rashba"))
    snapshot = d.document.to_json()
    for name, args in [("set_enabled", dict(entry="t1", enabled="false")),
                       ("set_enabled", dict(entry="t1", enabled=0)),
                       ("set_meanfield", dict(system="s1", enabled="false")),
                       ("add_term", dict(system="s1", kind="onsite", enabled="false")),
                       ("set_notes", dict(notes=None)),
                       ("rename", dict(entry="s1", name=None)),
                       ("set_param", dict(entry="c1", name="nk", value=float("inf"))),
                       ("add_term", dict(system="s1", kind="anderson_disorder",
                                         params={"seed": float("inf")})),
                       ("add_geometry_op", dict(system="s1", kind="supercell",
                                                params={"n": [float("inf"), 1, 1]}))]:
        with pytest.raises(CommandError, match="expected"):
            d.do(name, **args)
    assert d.document.to_json() == snapshot
    d.do("set_enabled", entry="t1", enabled=False)
    d.do("set_param", entry="c1", name="nk", value=40.0)          # a whole float is an int
    assert d.document.find("t1")[-1].enabled is False
    assert d.document.find("c1")[-1].params["nk"] == 40


def test_neighbour_hoppings_are_finite():
    """nan or inf in the construction's hoppings (the System form parses
    its box with float()) was stored, broke every key of the system with a
    raw ValueError, and was saved as a bare NaN that loaded again."""
    import json

    from guiqula.core.document import Document
    from guiqula.io import project
    from guiqula.registry import pipeline
    d = Dispatcher(project.load("honeycomb_zeeman_rashba"))
    for bad in (float("nan"), float("inf")):
        with pytest.raises(CommandError, match=r"set_construction: tij: the neighbour "
                                               r"hoppings must be finite numbers, not (nan|inf)$"):
            d.do("set_construction", system="s1", tij=[1.0, bad])
    assert d.document.system("s1").hamiltonian.construction.tij == [1.0] and not d.can_undo()
    pipeline.calculation_key(d.document, "c1")
    data = json.loads(d.document.to_json())
    data["systems"][0]["hamiltonian"]["construction"]["tij"] = [float("nan")]
    with pytest.raises(ValueError, match="finite"):
        Document.from_data(data)


def test_undo_steps_are_named_and_taken_several_at_once():
    """Phase 5, design item 10: Undo and Redo name their step, the history
    lists them, several steps go back as one event carrying the entry the
    step touched."""
    d = Dispatcher()
    events = []
    d.subscribe(events.append)
    assert d.undo_text() is None and d.history() == {"undo": [], "redo": []}
    s = d.do("add_system", lattice="honeycomb_lattice")
    t = d.do("add_term", system=s, kind="zeeman")
    d.do("set_param", entry=t, name="m", value=[0, 0, 0.3])
    d.do("remove", entry=t)
    assert d.history()["undo"] == ["remove t1 (zeeman / exchange field)", "set m of t1",
                                   "add term zeeman / exchange field",
                                   "new system on the honeycomb lattice"]
    assert d.undo_text() == "remove t1 (zeeman / exchange field)"
    d.undo(steps=2)
    assert events[-1]["type"] == "undo" and events[-1]["steps"] == 2
    assert events[-1]["entry"] == t and events[-1]["system"] is None
    assert d.document.find(t)[-1].params["m"] == [0.0, 0.0, 0.1]      # before the set
    assert d.history()["redo"] == ["set m of t1", "remove t1 (zeeman / exchange field)"]
    assert d.redo_text() == "set m of t1"
    d.redo()
    assert events[-1]["entry"] == t
    with pytest.raises(CommandError, match="cannot undo 9 steps; there are 3"):
        d.undo(9)
    d.undo(3)
    assert d.document.systems == [] and events[-1]["entry"] == s
    d.redo(4)
    assert d.history()["redo"] == [] and len(d.history()["undo"]) == 4
    with pytest.raises(CommandError, match="nothing to redo"):
        d.redo()


def test_a_step_of_the_mean_field_or_the_model_touches_its_row():
    """The selection follows an undo of a mean-field or a model change to
    that row (s1/meanfield, s2/model), not to the system's form."""
    d = Dispatcher()
    events = []
    d.subscribe(events.append)
    s = d.do("add_system")
    d.do("set_meanfield", system=s, params={"U": 2.0})
    g = d.do("add_system", kind="lattice_gas")
    d.do("set_model", system=g, params={"filling": 0.5})
    d.undo()
    assert (events[-1]["entry"], events[-1]["system"]) == (f"{g}/model", g)
    d.undo(2)
    assert (events[-1]["entry"], events[-1]["system"]) == (f"{s}/meanfield", s)
    d.redo()
    assert events[-1]["entry"] == f"{s}/meanfield"


def test_every_mutation_has_a_step_text():
    """No mutation falls back to its bare name (a new one needs a text in
    commands/steps.py)."""
    from guiqula.commands import steps
    from guiqula.commands.dispatcher import MUTATIONS
    import inspect
    source = inspect.getsource(steps.describe)
    missing = [name for name in MUTATIONS if f'"{name}"' not in source
               and name not in steps.FAMILY_OF_COMMAND]
    assert not missing
