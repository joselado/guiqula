"""Phase 1 acceptance, headless (PLAN.md section 7): honeycomb, supercell,
Zeeman and Rashba, bands, entirely through the command API and in the
worker; the arrays equal a direct pyqula script; the exported script runs
and reproduces them; undo restores the previous Document."""
import json
import os
import subprocess
import sys

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
