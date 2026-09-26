"""Phase 1 acceptance, headless (PLAN.md section 7): honeycomb, supercell,
Zeeman and Rashba, bands, entirely through the command API and in the
worker; the arrays equal a direct pyqula script; the exported script runs
and reproduces them; undo restores the previous Document."""
import json
import os
import subprocess
import sys
import time

import numpy as np
import pytest

from guiqula.io import results as result_files
from guiqula.session import Session

DIRECT = """
import numpy as np
from pyqula import geometry
g = geometry.honeycomb_lattice()
g = g.get_supercell([2, 2, 1])
h = g.get_hamiltonian()
h.add_zeeman([0.0, 0.0, lambda r: 0.3*np.tanh(r[0]/4)])
h.add_rashba(0.1)
k, e, c = h.get_bands(nk=120, operator="sz", write=False)
np.savez("direct.npz", e=e.reshape(120, -1), c=c.reshape(120, -1))
"""


def run_python_file(source, name, tmp_path, repo):
    (tmp_path / name).write_text(source)
    done = subprocess.run([sys.executable, name], cwd=tmp_path, capture_output=True, text=True,
                          env=dict(os.environ, PYTHONPATH=str(repo / "vendor")), timeout=600)
    assert done.returncode == 0, done.stderr


@pytest.fixture(scope="module")
def session():
    with Session(warm=False) as s:
        yield s


def test_acceptance_pipeline(session, tmp_path, repo):
    s = session.do("add_system", lattice="honeycomb_lattice", name="graphene")
    op = session.do("add_geometry_op", system=s, kind="supercell", params={"n": [2, 2, 1]})
    session.do("add_term", system=s, kind="zeeman", params={"m": [0, 0, "0.3*tanh(x/4)"]})
    t2 = session.do("add_term", system=s, kind="rashba", params={"c": 0.1})
    c = session.do("add_calculation", system=s, kind="bands", params={"nk": 120, "operator": "sz"})

    summary = session.act("run_calculation", calculation=c, wait=True, timeout=600)
    assert summary["status"] == "done", summary
    result = session.result(c)
    assert session.status(c) == "done" and result.mode == "spinful"

    run_python_file(DIRECT, "direct.py", tmp_path, repo)
    direct = np.load(tmp_path / "direct.npz")
    assert np.allclose(result.arrays["energies"], direct["e"], rtol=0, atol=1e-12)
    assert np.allclose(result.arrays["weights"], direct["c"], rtol=0, atol=1e-12)

    session.act("export_script", calculation=c, path=str(tmp_path / "exported.py"))
    run_python_file((tmp_path / "exported.py").read_text(), "exported.py", tmp_path, repo)
    exported = np.load(tmp_path / "result.npz")
    for name in ("energies", "weights"):
        assert np.allclose(exported[name], result.arrays[name], rtol=0, atol=1e-12)

    before = session.document.to_json()
    session.do("set_param", entry=t2, name="c", value=0.25)
    assert session.status(c) == "stale"              # kept, marked stale, not deleted
    session.undo()
    assert session.document.to_json() == before
    assert session.status(c) == "done"

    session.do("set_param", entry=op, name="n", value=[3, 2, 1])    # requirement 2
    assert session.status(c) == "stale"
    session.act("run_calculation", calculation=c, wait=True, timeout=600)
    assert session.result(c).arrays["energies"].shape == (120, 24)
    assert session.status(c) == "done"


def test_journal_records_actions_and_mutations(session):
    kinds = {(e["type"], e["name"]) for e in session.dispatcher.journal}
    assert ("action", "run_calculation") in kinds and ("mutation", "add_term") in kinds
    assert ("undo", "set_param") in kinds


def test_load_save_and_results(session, tmp_path):
    session.act("load", path="honeycomb_zeeman_rashba")
    assert session.path is None and not session.results
    job = session.run_calculation("c2", wait=True, timeout=600)
    assert job.status == "done", job.error
    session.act("save", path=str(tmp_path / "project.guiqula"))
    files = session.act("save_result", calculation="c2", path=str(tmp_path / "dos"))
    loaded = result_files.load(files[0])
    assert np.allclose(loaded.arrays["dos"], session.result("c2").arrays["dos"])
    assert json.loads(loaded.document) == json.loads(session.document.to_json())
    session.act("load", path=str(tmp_path / "project.guiqula"))
    assert session.path == tmp_path / "project.guiqula"


def test_cli_run_and_script(tmp_path, repo):
    env = dict(os.environ, PYTHONPATH=str(repo / "src"))
    done = subprocess.run([sys.executable, "-m", "guiqula", "run", "honeycomb_zeeman_rashba",
                           "--calc", "c2", "--out", "out", "--script"],
                          cwd=tmp_path, capture_output=True, text=True, env=env, timeout=600)
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["status"] == "done" and report["kind"] == "dos"
    assert {p.name for p in (tmp_path / "out").iterdir()} == {"c2.npz", "c2.json", "c2.py"}
    script = subprocess.run([sys.executable, "-m", "guiqula", "script", "honeycomb_zeeman_rashba",
                             "--calc", "c1"], cwd=tmp_path, capture_output=True, text=True,
                            env=env, timeout=120)
    assert script.returncode == 0 and "h.add_rashba(0.1)" in script.stdout
    bad = subprocess.run([sys.executable, "-m", "guiqula", "run", "nope"], cwd=tmp_path,
                         capture_output=True, text=True, env=env, timeout=120)
    assert bad.returncode != 0 and "no such preset" in bad.stderr


def test_removed_calculation_forgets_its_result(session):
    session.act("load", path="honeycomb_zeeman_rashba")
    assert session.run_calculation("c2", wait=True, timeout=600).status == "done"
    session.do("remove", entry="c2")
    assert session.result("c2") is None
    session.do("add_calculation", system="s1", kind="bands")      # reuses the id c2
    assert session.result("c2") is None and session.status("c2") == "none"


def test_builds_coalesce_and_are_kept_per_system(session):
    """A burst of edits costs one build per system (the carried-over phase-1
    item): requests still queued are superseded by the newest one."""
    session.act("load", path="honeycomb_zeeman_rashba")
    session.jobs.submit("sleep", {"seconds": 1.0}, role="interactive")    # keep the worker busy
    jobs = []
    for n in (2, 3, 4, 5):
        session.do("set_param", entry="op1", name="n", value=[n, n, 1])
        jobs.append(session.build("s1", wait=False))
    session.jobs.wait(jobs[-1], 300)
    assert [j.status for j in jobs] == ["cancelled"] * 3 + ["done"]
    build = session.builds["s1"]
    assert build["sites"] == 50 and build["positions"].shape == (50, 3)
    assert session.build_is_current("s1") and not session.build_errors
    assert all(j.id not in session.jobs.jobs for j in jobs)             # finished builds forgotten
    modes = [r.get("mode") for r in build["reports"] if r["stage"] in ("construction", "term")]
    assert modes == ["spinful"] * 3
    session.do("set_param", entry="op1", name="n", value=[1, 1, 1])
    assert not session.build_is_current("s1")
    session.do("remove", entry="c1")
    session.do("remove", entry="c2")
    session.do("remove", entry="s1")
    assert session.builds == {}


def test_console(session):
    """The Python console runs in its own worker (decision 14.1): doc, g
    and h of the system, variables that persist, echo of a final
    expression, tracebacks from the console's own code, do() through the
    dispatcher (undoable), and an interrupt that resets the namespace."""
    session.act("load", path="honeycomb_zeeman_rashba")
    out = session.act("console", code="n = len(g.r)\nn * 10", timeout=300)
    assert out["status"] == "done" and out["value"]["ok"], out
    assert out["output"] == ["80"]
    out = session.act("console", code="print(n, h.has_spin, doc.systems[0].id)")
    assert out["output"] == ["8 True s1"]
    out = session.act("console", code="x = 1\n1 / 0")
    assert out["value"]["ok"] is False and out["output"][0] == "Traceback (most recent call last):"
    assert out["output"][-1] == "ZeroDivisionError: division by zero"
    assert not any("process.py" in line for line in out["output"])   # the console's frames only
    terms = len(session.document.system("s1").hamiltonian.terms)
    out = session.act("console", code="t = do('add_term', system='s1', kind='onsite')\n"
                                      "t, len(doc.systems[0].hamiltonian.terms)")
    assert out["value"]["ok"], out
    assert out["output"] == [repr(("t3", terms + 1))]
    assert len(session.document.system("s1").hamiltonian.terms) == terms + 1
    session.undo()                                                # the console's edit
    assert len(session.document.system("s1").hamiltonian.terms) == terms
    out = session.act("console", code="len(h.geometry.r), n")
    assert out["output"] == ["(8, 8)"]
    session.interrupt_console()
    out = session.act("console", code="n", timeout=300)
    assert out["value"]["ok"] is False and out["output"][-1].startswith("NameError")
    job = session.console("import time\ntime.sleep(60)")
    deadline = time.monotonic() + 60
    while job.status != "running" and time.monotonic() < deadline:
        session.poll(0.05)
    session.interrupt_console()
    assert job.status == "cancelled"
    assert session.act("console", code="1 + 1", timeout=300)["output"] == ["2"]


def test_results_are_kept_in_the_project(session, tmp_path, no_jobs):
    """A .guiqula file keeps the results (PLAN.md 3.5): opened again they
    are there and current, and an edit makes them stale as before."""
    session.act("load", path="honeycomb_zeeman_rashba")
    job = session.run_calculation("c1", wait=True, timeout=600)
    assert job.status == "done", job.error
    path = tmp_path / "with_results.guiqula"
    session.act("save", path=str(path))
    session.act("new")
    assert not session.results
    session.act("load", path=str(path))
    kept = session.result("c1")
    assert kept is not None and session.status("c1") == "done"
    assert np.allclose(kept.arrays["energies"], job.value.arrays["energies"])
    assert kept.structure == job.value.structure and kept.reports == job.value.reports
    session.do("set_param", entry="t2", name="c", value=0.3)
    assert session.status("c1") == "stale"
    session.act("save", path=str(tmp_path / "bare.json"))        # bare JSON: no results
    reopened = Session(str(tmp_path / "bare.json"), jobs=no_jobs)
    assert reopened.results == {}
    reopened = Session(str(path), jobs=no_jobs)
    assert set(reopened.results) == {"c1"}
