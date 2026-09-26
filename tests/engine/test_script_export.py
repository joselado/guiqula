"""Exported scripts run on their own and reproduce the engine's arrays
(PLAN.md 3.5): the script is generated from the same registry entries."""
import os
import subprocess
import sys

import numpy as np
import pytest

from guiqula.commands import Dispatcher
from guiqula.engine.calculations import run_calculation
from guiqula.io import project
from guiqula.io.script import export_script


def run_script(source, repo, tmp_path):
    path = tmp_path / "exported.py"
    path.write_text(source)
    env = dict(os.environ, PYTHONPATH=str(repo / "vendor"))
    done = subprocess.run([sys.executable, str(path)], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr + "\n" + source
    return dict(np.load(tmp_path / "result.npz"))


def assert_reproduces(document, calc_id, repo, tmp_path):
    result = run_calculation(document, calc_id)
    skipped = {r["id"]: r["message"] for r in result.skipped}
    arrays = run_script(export_script(document, calc_id, skipped), repo, tmp_path)
    assert set(arrays) == set(result.arrays)
    for name, value in result.arrays.items():
        assert np.allclose(arrays[name], value, rtol=0, atol=1e-12), name
    return result


def test_preset_bands(pyqula, repo, tmp_path):
    assert_reproduces(project.load("honeycomb_zeeman_rashba"), "c1", repo, tmp_path)


def test_everything_at_once(pyqula, repo, tmp_path):
    """Regions, expressions, seeds, a spinless request upgraded by a term,
    a disabled entry, a skipped entry, removed atoms and DOS."""
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_construction", system=s, has_spin=False, tij=[1.0, 0.1])
    d.do("add_geometry_op", system=s, kind="supercell", params={"n": [3, 2, 1]})
    d.do("add_geometry_op", system=s, kind="remove_atoms",
         params={"positions": [[0.0, 0.0, 0.0]], "tol": 0.2})
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x > 1"})
    p = d.do("add_region", system=s, select={"kind": "positions",
                                             "positions": [[1.0, 0.0, 0.0]], "tol": 0.3})
    d.do("add_term", system=s, kind="onsite", params={"mu": "0.2*sin(x)"}, region=r)
    d.do("add_term", system=s, kind="haldane", params={"t": 0.05}, region=p)
    d.do("add_term", system=s, kind="anderson_disorder", params={"w": 0.3, "seed": 5})
    d.do("add_term", system=s, kind="zeeman", params={"m": [0.1, 0, "0.2*tanh(y)"]})
    d.do("add_term", system=s, kind="rashba", enabled=False)
    c = d.do("add_calculation", system=s, kind="dos", params={"ne": 40, "nk": 6, "delta": 0.1})
    source = export_script(d.document, c)
    assert "rashba: disabled" in source and "because of" in source
    assert "np.random.seed(5)" in source
    assert_reproduces(d.document, c, repo, tmp_path)


def test_skipped_entry_is_commented(pyqula, repo, tmp_path):
    d = Dispatcher()
    s = d.do("add_system", lattice="triangular_lattice")
    t = d.do("add_term", system=s, kind="sublattice_imbalance")
    d.do("add_term", system=s, kind="onsite")
    c = d.do("add_calculation", system=s, kind="bands", params={"nk": 20})
    result = assert_reproduces(d.document, c, repo, tmp_path)
    assert [r["id"] for r in result.skipped] == [t]
    source = export_script(d.document, c, {t: result.skipped[0]["message"]})
    assert f"# {t} sublattice_imbalance: skipped" in source


def test_export_refuses_a_broken_calculation():
    d = Dispatcher()
    s = d.do("add_system")
    c = d.do("add_calculation", system=s, kind="bands")
    d.document.calculations[0].kind = "nope"
    with pytest.raises(ValueError, match="unknown calculation"):
        export_script(d.document, c)
