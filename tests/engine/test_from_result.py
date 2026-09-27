"""from_result Fields (PLAN.md 3.8): a quantum system's exchange field read
from a classical system's texture, as pyqula's modulated_ladder example
does by hand. The key hashes the result read, so running the source again
makes the reader stale; references to the same system, in a circle, to a
missing result or array are refused."""
import numpy as np
import pytest

from guiqula.commands import Dispatcher
from guiqula.core.results import ResultRef
from guiqula.engine.build import build_system
from guiqula.engine.calculations import run_calculation
from guiqula.io.script import export_script
from guiqula.registry import pipeline

from .conftest import assert_same_hamiltonian
from .test_script_export import run_scripts


def texture_field(calc, scale=0.5):
    return [{"kind": "from_result", "calculation": calc, "array": "magnetization",
             "component": i, "scale": scale} for i in range(3)]


def bridge():
    """s1: classical spins on a finite ladder; s2: electrons on the same
    ladder whose exchange field is the texture of s1, times 0.5."""
    d = Dispatcher()
    s1 = d.do("add_system", lattice="ladder", kind="classical_spin")
    d.do("add_geometry_op", system=s1, kind="supercell", params={"n": [6, 1, 1]})
    d.do("add_geometry_op", system=s1, kind="finite")
    d.do("add_term", system=s1, kind="heisenberg", params={"J1": -1.0})
    d.do("add_term", system=s1, kind="spin_field", params={"b": ["0.3*tanh(x - 3)", 0, 0.1]})
    c1 = d.do("add_calculation", system=s1, kind="minimize_spins", params={"tries": 2})
    s2 = d.do("add_system", lattice="ladder")
    d.do("add_geometry_op", system=s2, kind="supercell", params={"n": [6, 1, 1]})
    d.do("add_geometry_op", system=s2, kind="finite")
    t = d.do("add_term", system=s2, kind="zeeman", params={"m": texture_field(c1)})
    c2 = d.do("add_calculation", system=s2, kind="bands", params={"nk": 2})
    return d, s1, s2, c1, t, c2


def test_texture_as_exchange_field(pyqula, repo, tmp_path):
    from pyqula import geometry
    d, s1, s2, c1, t, c2 = bridge()
    report = next(r for r in build_system(d.document, s2).reports if r["id"] == t)
    assert report["status"] == "invalid" and "run c1 first" in report["message"]
    texture = run_calculation(d.document, c1)
    refs = {c1: ResultRef.of(texture, {"magnetization"})}
    built = build_system(d.document, s2, results=refs)
    assert next(r for r in built.reports if r["id"] == t)["status"] == "ok"
    g = geometry.ladder().get_supercell([6, 1, 1])
    g.set_finite()
    h = g.get_hamiltonian(has_spin=True)
    h.add_zeeman(0.5 * texture.arrays["magnetization"])        # one vector per site
    assert_same_hamiltonian(built.h, h)
    result = run_calculation(d.document, c2, results=refs)
    arrays = run_scripts([export_script(d.document, c2, results=refs)], repo, tmp_path)[0]
    assert np.allclose(arrays["energies"], result.arrays["energies"], rtol=0, atol=1e-10)


def test_the_key_follows_the_result_read(pyqula):
    d, s1, s2, c1, t, c2 = bridge()
    first = run_calculation(d.document, c1)
    refs = {c1: ResultRef.of(first)}
    key = pipeline.calculation_key(d.document, c2, results=refs)
    d.do("set_param", entry=c1, name="tries", value=3)             # c1 goes stale
    stage = pipeline.plan_system(d.document, s2, results=refs).stage(t)
    assert stage.warnings == ["reads a stale result of c1 (run c1 again)"]
    assert pipeline.calculation_key(d.document, c2, results=refs) == key   # same data read
    second = run_calculation(d.document, c1)
    refs = {c1: ResultRef.of(second)}
    assert pipeline.calculation_key(d.document, c2, results=refs) != key   # new data: stale
    assert pipeline.plan_system(d.document, s2, results=refs).stage(t).warnings == []


def test_a_result_keeps_what_it_read(pyqula, repo, tmp_path):
    """A result keeps the results its from_result Fields read (the arrays
    read only), through a save and a load: the bundle of a stale reader
    reproduces it after its source ran again with another field and the
    term stopped reading it (its script read the current result, or
    commented the term out)."""
    from guiqula.core.document import Document, terms_of
    from guiqula.io import bundle
    from guiqula.io import results as result_files
    d, s1, s2, c1, t, c2 = bridge()
    refs = {c1: ResultRef.of(run_calculation(d.document, c1))}
    reader = run_calculation(d.document, c2, results=refs)
    assert set(reader.reads) == {c1} and set(reader.reads[c1].arrays) == {"magnetization"}
    reader = result_files.load(result_files.save(reader, tmp_path / "c2")[0])
    field = terms_of(d.document.system(s1))[1].id
    d.do("set_param", entry=field, name="b", value=[0.0, 0.0, 3.0])
    now = {c1: ResultRef.of(run_calculation(d.document, c1))}
    d.do("set_param", entry=t, name="m", value=[0.0, 0.0, 0.1])
    snapshot = Document.from_json(reader.document)
    assert pipeline.calculation_key(snapshot, c2, results=now) != reader.key
    assert pipeline.calculation_key(snapshot, c2, results=reader.reads) == reader.key
    bundle.write(tmp_path / "bundle", reader, None, results=now, stale=True)   # as the window
    source = (tmp_path / "bundle" / "script.py").read_text()
    arrays = run_scripts([source], repo, tmp_path)[0]
    assert np.allclose(arrays["energies"], reader.arrays["energies"], rtol=0, atol=1e-10)


def test_references_that_cannot_work(pyqula):
    d, s1, s2, c1, t, c2 = bridge()
    refs = {c1: ResultRef.of(run_calculation(d.document, c1))}

    def problem(entry, system):
        return pipeline.plan_system(d.document, system, results=refs).stage(entry).problem
    d.do("set_param", entry=t, name="m", value=[{"kind": "from_result", "calculation": c1,
                                                  "array": "magnetization"}, 0, 0])
    assert "choose a component" in problem(t, s2)
    d.do("set_param", entry=t, name="m", value=[{"kind": "from_result", "calculation": c1,
                                                  "array": "nope", "component": 0}, 0, 0])
    assert "no array 'nope'" in problem(t, s2)
    d.do("set_param", entry=t, name="m", value=texture_field(c2))
    assert "own system" in problem(t, s2)
    d.do("set_param", entry=t, name="m", value=texture_field(c1))
    back = d.do("add_term", system=s1, kind="spin_field", params={"b": [
        {"kind": "from_result", "calculation": c2, "array": "energies", "component": 0}, 0, 0]})
    assert "circle" in problem(back, s1)
    assert pipeline.result_references(d.document) == [c1, c2]
    with pytest.raises(Exception, match="piecewise Field cannot hold a from_result"):
        d.do("set_param", entry=t, name="m", value=[{"kind": "piecewise", "default": 0,
                                                      "pieces": [{"region": "r1", "value": {
                                                          "kind": "from_result",
                                                          "calculation": c1, "array": "x"}}]},
                                                     0, 0])
