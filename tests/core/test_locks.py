"""Locked parameters (decision 13.16, PLAN.md phase 5 design item 12): the
dispatcher refuses whatever changes what a lock covers; lock and unlock
are undoable mutations; the locks are saved with the Document."""
import pytest

from guiqula.commands import CommandError, Dispatcher
from guiqula.core import locks
from guiqula.core.document import Document
from guiqula.io import project


@pytest.fixture
def d():
    d = Dispatcher(project.load("honeycomb_zeeman_rashba"))
    return d


def test_a_locked_parameter_refuses_changes_the_others_do_not(d):
    d.do("lock", target="t1.m")
    with pytest.raises(CommandError, match="t1.m is locked"):
        d.do("set_param", entry="t1", name="m", value=[0, 0, 1])
    with pytest.raises(CommandError, match="locked"):
        d.do("set_params", entry="t1", params={"m": [0, 0, 1]})
    with pytest.raises(CommandError, match="locked"):
        d.do("remove", entry="t1")
    d.do("set_enabled", entry="t1", enabled=False)       # the entry is not locked, m is
    d.do("set_param", entry="t2", name="c", value=0.3)
    d.do("move", entry="t1", index=1)
    copy = d.do("duplicate", entry="t1")
    d.do("set_param", entry=copy, name="m", value=[0, 0, 1])    # a copy is free


def test_entry_system_and_geometry_locks(d):
    d.do("lock", target="t2")
    for command, args in (("set_enabled", {"entry": "t2", "enabled": False}),
                          ("set_param", {"entry": "t2", "name": "c", "value": 0.2}),
                          ("remove", {"entry": "t2"})):
        with pytest.raises(CommandError, match="t2 is locked"):
            d.do(command, **args)
    d.do("unlock", target="t2")
    d.do("lock", target="s1/geometry")
    with pytest.raises(CommandError, match="s1/geometry is locked"):
        d.do("add_geometry_op", system="s1", kind="supercell")
    with pytest.raises(CommandError, match="locked"):
        d.do("set_param", entry="op1", name="n", value=[3, 3, 1])
    with pytest.raises(CommandError, match="locked"):
        d.do("set_lattice", system="s1", lattice="square_lattice")
    d.do("add_term", system="s1", kind="onsite")                # the Hamiltonian is not
    d.do("lock", target="s1")
    with pytest.raises(CommandError, match="s1 is locked"):
        d.do("add_term", system="s1", kind="haldane")
    d.do("set_param", entry="c1", name="nk", value=50)           # a calculation is not in it
    d.do("lock", target="c1.nk")
    d.do("lock", target="c1.nk")                                 # twice: once
    assert d.document.locks == ["s1/geometry", "s1", "c1.nk"]
    d.do("unlock")
    assert d.document.locks == []
    d.do("add_term", system="s1", kind="haldane")


def test_lock_targets_are_checked_and_undo_takes_locks_back(d):
    for target in ("t9", "t1.nope", "s1/hamiltonian", "s1/geometry.n", 3):
        with pytest.raises(CommandError, match="nothing to lock"):
            d.do("lock", target=target)
    with pytest.raises(CommandError, match="is not locked"):
        d.do("unlock", target="t1")
    d.do("lock", target="t1.m")
    assert d.undo_text() == "lock t1.m"
    d.undo()
    assert d.document.locks == []
    d.redo()
    assert len(d.document.locks) == 1


def test_locks_are_saved(d, tmp_path):
    d.do("lock", target="t1.m")
    path = project.save(d.document, tmp_path / "locked.json")
    assert project.load(path).locks == ["t1.m"]
    assert Document().locks == []
    assert locks.value(d.document, "t1.m") == d.document.find("t1")[-1].params["m"]


def test_a_lattice_parameter_lock():
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_zigzag_ribbon")
    name = next(iter(d.document.system(s).geometry.base.params))
    d.do("lock", target=f"{s}.{name}")
    with pytest.raises(CommandError, match="locked"):
        d.do("set_param", entry=s, name=name, value=7)
    d.do("add_geometry_op", system=s, kind="supercell")
