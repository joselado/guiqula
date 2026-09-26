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


DRIVER = """import os, runpy, sys
for folder in sys.argv[1:]:
    os.chdir(folder)
    print("running", folder, flush=True)
    runpy.run_path("exported.py", run_name="__main__")
"""


def run_scripts(sources, repo, tmp_path):
    """Run several exported scripts in one interpreter, each in its own
    folder (pyqula is imported and its kernels compiled once); returns the
    arrays each saved."""
    folders = []
    for i, source in enumerate(sources):
        folder = tmp_path / f"script{i}"
        folder.mkdir()
        (folder / "exported.py").write_text(source)
        folders.append(folder)
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER)
    env = dict(os.environ, PYTHONPATH=str(repo / "vendor"))
    done = subprocess.run([sys.executable, str(driver), *map(str, folders)], cwd=tmp_path,
                          env=env, capture_output=True, text=True, timeout=1800)
    failed = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    assert done.returncode == 0, f"{failed}\n{done.stderr[-3000:]}"
    return [dict(np.load(folder / "result.npz")) for folder in folders]


def assert_same_arrays(expected, got, label):
    assert set(got) == set(expected), label
    for name, value in expected.items():
        assert np.allclose(got[name], value, rtol=0, atol=1e-10), f"{label}: {name}"


def assert_reproduces(document, calc_id, repo, tmp_path):
    result = run_calculation(document, calc_id)
    skipped = {r["id"]: r["message"] for r in result.skipped}
    arrays = run_script(export_script(document, calc_id, skipped), repo, tmp_path)
    assert set(arrays) == set(result.arrays)
    for name, value in result.arrays.items():
        assert np.allclose(arrays[name], value, rtol=0, atol=1e-12), name
    return result


@pytest.mark.parametrize("preset", project.presets())
def test_preset_bands(pyqula, repo, tmp_path, preset):
    result = assert_reproduces(project.load(preset), "c1", repo, tmp_path)
    assert result.skipped == []
    if preset == "honeycomb_hubbard":        # the Neel state opens a gap at half filling
        energies = result.arrays["energies"]
        assert result.meanfield["total_energy"] < 0
        assert energies[energies > 0].min() - energies[energies < 0].max() > 0.5


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


def test_piecewise_pairing_and_mean_field(pyqula, repo, tmp_path):
    """A piecewise Field over two regions, a Nambu upgrade by s-wave pairing,
    Kane-Mele, and a mean field seeded with a random guess."""
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_construction", system=s, has_spin=False)
    d.do("add_geometry_op", system=s, kind="supercell", params={"n": [2, 1, 1]})
    left = d.do("add_region", system=s, select={"kind": "expression", "expr": "x < 0.5"})
    picked = d.do("add_region", system=s, select={"kind": "positions",
                                                  "positions": [[1.0, 0.0, 0.0]], "tol": 0.3})
    d.do("add_term", system=s, kind="onsite", params={"mu": {
        "kind": "piecewise", "default": "0.1*y",
        "pieces": [{"region": left, "value": 0.2}, {"region": picked, "value": "-0.3*x"}]}})
    d.do("add_term", system=s, kind="kane_mele", params={"t": 0.03})
    d.do("add_term", system=s, kind="swave", params={"delta": 0.05})
    d.do("set_meanfield", system=s, enabled=True,
         params={"U": -1.0, "mf": "random", "seed": 4, "nk": 3, "mix": 0.5})
    c = d.do("add_calculation", system=s, kind="bands", params={"nk": 12})
    source = export_script(d.document, c)
    assert "h = g.get_hamiltonian(has_spin=True)\nh.turn_nambu()" in source
    assert "np.random.seed(4)" in source and "get_mean_field_hamiltonian(U=-1.0" in source
    result = assert_reproduces(d.document, c, repo, tmp_path)
    assert result.mode == "nambu" and result.reports[-1]["notes"]["total_energy"] < 0


def test_meanfield_engines_and_site_filling(pyqula, repo, tmp_path):
    """A per-site filling (a Field) with the numpy engine and an
    antiferromagnetic vector field; then the jax engine."""
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_geometry_op", system=s, kind="supercell", params={"n": [2, 1, 1]})
    d.do("add_term", system=s, kind="antiferromagnetism", params={"m": [0.05, 0, "0.1*tanh(x)"]})
    d.do("set_meanfield", system=s, enabled=True, params={
        "U": 3.0, "filling": "0.5 + 0.03*cos(x)", "mf": "antiferro", "nk": 4, "mix": 0.5})
    c = d.do("add_calculation", system=s, kind="bands", params={"nk": 10})
    source = export_script(d.document, c)
    assert "filling = np.array([(lambda r:" in source and "afm = [0.05, 0.0, lambda r:" in source
    assert "T=" not in source and "maxite=" not in source         # the engine's defaults
    assert_reproduces(d.document, c, repo, tmp_path)
    d.do("set_meanfield", system=s, params={"filling": 0.5, "engine": "jax",
                                            "solver": "linear_mixing"})
    assert "use_jax=True, solver='linear_mixing'" in export_script(d.document, c)
    assert_reproduces(d.document, c, repo, tmp_path)


def test_island(pyqula, repo, tmp_path):
    """A module-level Call with a keyword geometry (islands.get_geometry)."""
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_geometry_op", system=s, kind="island", params={"n": 2.0, "rot": 0.1})
    d.do("add_term", system=s, kind="sublattice_imbalance", params={"mass": 0.2})
    c = d.do("add_calculation", system=s, kind="dos", params={"ne": 30, "nk": 1, "delta": 0.1})
    source = export_script(d.document, c)
    assert "from pyqula import geometry, islands" in source
    assert "g = islands.get_geometry(geo=g, n=2.0, nedges=6, rot=0.1, clean=True)" in source
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


def test_every_calculation_exports(pyqula, repo, tmp_path):
    """The script of every calculation case of the engine tests reproduces
    the engine's arrays (run in one interpreter)."""
    from .test_entries import CALC_CASES, calc_system
    cases, sources = [], []
    for kind, params_list in sorted(CALC_CASES.items()):
        for params, name, _ in params_list:
            d, s, _ = calc_system(name)
            c = d.do("add_calculation", system=s, kind=kind, params=params)
            cases.append((f"{kind} on {name}", run_calculation(d.document, c).arrays))
            sources.append(export_script(d.document, c))
    for (label, expected), got in zip(cases, run_scripts(sources, repo, tmp_path)):
        assert_same_arrays(expected, got, label)


def test_every_entry_exports(pyqula, repo, tmp_path):
    """Every lattice, geometry op and term case of the engine tests, with
    the bands on top, exported and run: the script builds the same system."""
    from .test_entries import (CLASSICAL_TERM_CASES, LATTICES, MODEL_CASES, OP_CASES,
                               TERM_CASES, TERM_SYSTEMS, classical, system)
    documents = []
    for lattice in LATTICES:
        d, s, _ = system(lattice)
        documents.append((f"lattice {lattice}", d, s))
    for kind, (params, lattice, before, _) in sorted(OP_CASES.items()):
        d, s, _ = system(lattice, ops=before + [(kind, params)])
        documents.append((f"op {kind}", d, s))
    for kind, cases in sorted(TERM_CASES.items()):
        options = TERM_SYSTEMS.get(kind, {})
        n = options.get("n", 2)
        ops = [("supercell", {"n": [n, n, 1]})] + ([("finite", {})] if options.get("finite")
                                                    else [])
        for params, _ in cases:
            d, s, _ = system(options.get("lattice", "honeycomb_lattice"), ops=ops,
                             terms=[(kind, params)], has_spin=options.get("has_spin", True))
            if "tij" in options:
                d.do("set_construction", system=s, tij=options["tij"])
            documents.append((f"term {kind} {params}", d, s))
    for kind, (params, lattice) in sorted(MODEL_CASES.items()):
        d, s, _ = classical(kind, lattice, 3, model_params=params)
        documents.append((f"model {kind}", d, s))
    for kind, cases in sorted(CLASSICAL_TERM_CASES.items()):
        for system_kind, lattice, params, _ in cases:
            d, s, _ = classical(system_kind, lattice, 3, [(kind, params)],
                                finite=kind == "spin_tensor")
            documents.append((f"term {kind} {params}", d, s))
    cheap = {"quantum": ("bands", {"nk": 6}), "classical_spin": ("minimize_spins", {"tries": 1}),
             "lattice_gas": ("anneal_gas", {"ntries": 200, "temperatures": 2}),
             "ising": ("anneal_ising", {"ntries": 200, "temperatures": 2})}
    cases, sources = [], []
    for label, d, s in documents:
        kind, params = cheap[d.document.system(s).kind]
        c = d.do("add_calculation", system=s, kind=kind, params=params)
        result = run_calculation(d.document, c)
        assert result.skipped == [], label
        cases.append((label, result.arrays))
        sources.append(export_script(d.document, c))
    for (label, expected), got in zip(cases, run_scripts(sources, repo, tmp_path)):
        assert_same_arrays(expected, got, label)
