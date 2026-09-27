"""Test a plugin's entries as guiqula tests its own (its CLAUDE.md: every
registry entry against a direct pyqula call, and the exported script).

Run from the plugin's directory with the plugin installed (pip install -e
.) or on the path: python -m pytest. Every test runs in a scratch
directory, since pyqula writes files to the working directory.
"""
import subprocess
import sys

import numpy as np
import pytest

import guiqula                                         # puts guiqula's pyqula on sys.path
from guiqula import registry
from guiqula.commands import Dispatcher
from guiqula.engine.build import build_system
from guiqula.io.script import export_script


@pytest.fixture(autouse=True)
def scratch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def document():
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_construction", system=s, has_spin=False)
    d.do("add_geometry_op", system=s, kind="supercell", params={"n": [3, 3, 1]})
    d.do("add_term", system=s, kind="chiral_kekule", params={"t1": 0.2, "t2": 0.1})
    d.do("add_calculation", system=s, kind="bands", params={"nk": 20})
    return d.document, s


def test_it_is_registered_as_a_plugin_entry():
    spec = registry.get("term", "chiral_kekule")
    assert spec.plugin == "guiqula-example-plugin"


def test_the_engine_equals_pyqula():
    doc, s = document()
    h = build_system(doc, s).h
    from pyqula import geometry
    g = geometry.honeycomb_lattice().get_supercell([3, 3, 1])
    direct = g.get_hamiltonian(has_spin=False)
    direct.add_chiral_kekule(t1=0.2, t2=0.1)
    for k in ([0, 0, 0], [0.1, 0.3, 0]):
        assert np.allclose(h.get_hk_gen()(k), direct.get_hk_gen()(k))


def test_the_exported_script_runs(tmp_path):
    doc, _ = document()
    source = export_script(doc, "c1")
    assert "h.add_chiral_kekule(t1=0.2, t2=0.1)" in source
    (tmp_path / "script.py").write_text(source)
    import os
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    done = subprocess.run([sys.executable, "script.py"], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr
