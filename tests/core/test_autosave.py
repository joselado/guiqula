"""Autosave, recovery and the modified flag (PLAN.md 3.5, decision 14.4),
with a stand-in for the job manager: no worker processes."""
import json
import os
import subprocess
import sys

import pytest

from guiqula.commands import CommandError
from guiqula.io import autosave, project
from guiqula.session import Session


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GUIQULA_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


def dead_pid():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def session(document=None, clock=None, **options):
    saver = autosave.Autosaver(clock=clock) if clock else options.pop("autosave", False)
    return Session(document, jobs=NoJobs(), autosave=saver, **options)


class NoJobs:
    def subscribe(self, listener):
        return lambda: None

    def poll(self, timeout=0.0):
        return 0

    def shutdown(self):
        pass


def test_debounce(data_dir):
    clock = Clock()
    s = session(clock=clock)
    saver = s.autosaver
    s.do("add_system")
    s.poll()
    assert not saver.path.exists()                  # not yet: waits for a quiet second
    writes = []
    for step in range(12):                          # a slider drag: a change every 0.5 s
        clock.now += 0.5
        s.do("rename", entry="s1", name=f"n{step}")
        s.poll()
        if saver.path.exists():
            writes.append(json.loads(saver.path.read_text())["document"]["systems"][0]["name"])
    assert writes and writes[0] == "n9"             # max_delay (5 s) forced a write mid-drag
    clock.now += 1.0
    s.poll()
    last = json.loads(saver.path.read_text())
    assert last["document"]["systems"][0]["name"] == "n11" and last["modified"]
    assert last["pid"] == os.getpid() and not saver.pending
    s.act("list_recoverable")                       # actions change nothing to save...
    assert not saver.pending
    s.act("save", path=str(data_dir / "p.json"))    # ...except save: now nothing is unsaved
    assert saver.pending
    clock.now += 1.0
    s.poll()
    assert not json.loads(saver.path.read_text())["modified"]
    s.close()                                       # a clean close removes the file
    assert not saver.path.exists()


def test_modified_flag(data_dir, tmp_path):
    s = session("honeycomb_zeeman_rashba")
    assert s.path is None and not s.modified         # a preset has no path to save to
    s.do("set_param", entry="t2", name="c", value=0.3)
    assert s.modified
    s.undo()
    assert not s.modified                           # compared by content, not by history
    s.do("add_system")
    s.act("save", path=str(tmp_path / "p.guiqula"))
    assert not s.modified and s.path == tmp_path / "p.guiqula"
    s.act("new")
    assert not s.modified and s.path is None
    s.act("load", path=str(tmp_path / "p.guiqula"))
    assert not s.modified and s.path == tmp_path / "p.guiqula"
    assert Session(str(tmp_path / "p.guiqula"), jobs=NoJobs()).path == tmp_path / "p.guiqula"


def test_view_state_is_saved_but_is_not_a_change(data_dir, tmp_path):
    s = session("honeycomb_zeeman_rashba")
    view = {"workspace": "hamiltonian", "selected": "t2"}
    s.view_state = lambda: dict(view)
    assert not s.modified
    s.act("save", path=str(tmp_path / "p.json"))
    assert json.loads((tmp_path / "p.json").read_text())["ui"] == view
    view["selected"] = "t1"                         # clicking around changes nothing to save
    assert not s.modified and not s.dispatcher.can_undo()
    s.act("load", path=str(tmp_path / "p.json"))
    assert s.document.ui == {"workspace": "hamiltonian", "selected": "t2"} and not s.modified
    s.view_state = lambda: {"broken": object()}     # never blocks a save
    s.act("save", path=str(tmp_path / "q.json"))
    assert json.loads((tmp_path / "q.json").read_text())["ui"]["selected"] == "t2"


def write_orphan(directory, document, pid, source=None, modified=True, name="orphan.json"):
    saver = autosave.Autosaver(directory=directory)
    saver.path = directory / name
    saver.write(document, source, modified)
    data = json.loads(saver.path.read_text())
    data["pid"] = pid
    saver.path.write_text(json.dumps(data))
    return saver.path


def test_recoverable_lists_dead_sessions_only(data_dir, tmp_path):
    directory = autosave.autosave_dir()
    document = project.load("honeycomb_zeeman_rashba")
    write_orphan(directory, document, os.getpid(), name="alive.json")      # a running session
    write_orphan(directory, document, dead_pid(), modified=False, name="saved.json")
    orphan = write_orphan(directory, document, dead_pid(), source=tmp_path / "x.guiqula")
    (directory / "broken.json").write_text("{not json")
    found = autosave.recoverable()
    assert [e["path"] for e in found if "error" not in e] == [str(orphan)]
    assert found[0]["systems"] == ["graphene with exchange and Rashba"]
    assert any("error" in e and e["path"].endswith("broken.json") for e in found)
    assert {e["path"] for e in autosave.recoverable(include_unmodified=True)} >= {
        str(orphan), str(directory / "saved.json")}


def test_recover_action(data_dir, tmp_path):
    clock = Clock()
    s = session(clock=clock)
    with pytest.raises(CommandError, match="nothing to recover"):
        s.act("recover")
    document = project.load("honeycomb_zeeman_rashba")
    document.systems[0].name = "unsaved work"
    orphan = write_orphan(autosave.autosave_dir(), document, dead_pid(),
                          source=tmp_path / "work.guiqula")
    listed = s.act("list_recoverable")
    assert [e["path"] for e in listed] == [str(orphan)]
    info = s.act("recover")
    assert info["path"] == str(orphan) and s.document.systems[0].name == "unsaved work"
    assert s.modified and s.path == tmp_path / "work.guiqula"
    assert not s.dispatcher.can_undo()
    # the recovered file is taken over: rewritten with this pid, gone on a clean close
    clock.now += 2
    s.poll()
    assert s.autosaver.path == orphan and json.loads(orphan.read_text())["pid"] == os.getpid()
    assert autosave.recoverable() == []              # it belongs to a live session now
    s.close()
    assert not orphan.exists()


def test_discard_recovery(data_dir):
    s = session()
    orphan = write_orphan(autosave.autosave_dir(), project.load("honeycomb_zeeman_rashba"), dead_pid())
    s.act("discard_recovery", path=str(orphan))
    assert not orphan.exists() and s.act("list_recoverable") == []


def test_failed_write_is_reported_not_raised(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    saver = autosave.Autosaver(directory=blocker / "autosave")   # a file in the way
    assert saver.write(project.load("honeycomb_zeeman_rashba")) is None
    assert "autosave failed" in saver.error
