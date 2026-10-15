"""The embedding: an object of the Document naming two quantum systems, the
pristine crystal and the defect. A calculation runs on it as on a system:
the planner plans both (the defect keys the result), the engine puts them
in one Hilbert space and refuses a pair that does not share a cell, the
script builds the defect first, neither system can be removed while it is
named, and a sweep may change either. Its arrays against direct pyqula
calls are in test_entries.py (CALC_CASES "embedding_*")."""
import numpy as np
import pytest

from guiqula.commands import CommandError, Dispatcher
from guiqula.core.document import Document, DocumentError
from guiqula.engine.calculations import CalculationError, run_calculation
from guiqula.io.script import export_script
from guiqula.registry import cost, pipeline


def chain_and_impurity(kind="embedding_ldos", params=None):
    """A spinless metallic chain (s1), its copy with an onsite impurity (s2),
    the embedding of the two (e1) and a calculation on it."""
    d = Dispatcher()
    s = d.do("add_system", lattice="chain")
    d.do("set_construction", system=s, has_spin=False)
    e = d.do("add_embedding", pristine=s)
    defect = d.document.embedding(e).defect
    t = d.do("add_term", system=defect, kind="onsite", params={"mu": 1.0})
    c = d.do("add_calculation", system=e, kind=kind,
             params=params or {"window": 5, "nk": 50})
    return d, s, defect, e, t, c


def test_a_new_embedding_copies_the_pristine_system():
    """Without a defect named, the defect is a copy of the pristine system on
    the same geometry, so the two share their cell, and keep sharing it
    (decision 224); the embedding is saved and
    read back, and a document without one writes no embeddings at all."""
    d, s, defect, e, _, c = chain_and_impurity()
    document = d.document
    assert defect != s and document.system(defect).name == f"{s} (defect)"
    assert document.system(defect).geometry == document.system(s).geometry
    assert document.target_kind(e) == "embedding" and document.calculation(c).system == e
    again = Document.from_json(document.to_json())
    assert again.embedding(e).pristine == s and again.embedding(e).defect == defect
    assert "embeddings" not in Dispatcher().document.to_json()
    with pytest.raises(DocumentError, match="missing system 's9'"):
        Document.from_data({"systems": [], "embeddings": [
            {"id": "e1", "pristine": "s9", "defect": "s8"}]})


def test_the_two_systems_are_named_and_kept():
    """A system an embedding names cannot be removed, nor an embedding a
    calculation runs on; the undo history names the step."""
    d, s, defect, e, _, c = chain_and_impurity()
    with pytest.raises(CommandError, match="part of embeddings"):
        d.do("remove", entry=defect)
    with pytest.raises(CommandError, match="used by calculations"):
        d.do("remove", entry=e)
    d.do("remove", entry=c)
    d.do("remove", entry=e)
    d.do("remove", entry=defect)
    assert d.document.embeddings == []
    d.undo(3)
    assert d.document.embedding(e).defect == defect
    assert "new embedding of s1" in d.history()["undo"]


def test_what_cannot_be_embedded_is_refused():
    d, s, defect, e, _, c = chain_and_impurity()
    with pytest.raises(CommandError, match="its own"):
        d.do("set_embedding", embedding=e, defect=s)
    spins = d.do("add_system", kind="classical_spin", lattice="chain")
    with pytest.raises(CommandError, match="has to be a quantum one"):
        d.do("set_embedding", embedding=e, defect=spins)
    with pytest.raises(CommandError, match="does not apply to an embedding"):
        d.do("add_calculation", system=e, kind="bands")
    with pytest.raises(CommandError, match="does not apply to a quantum system"):
        d.do("add_calculation", system=s, kind="embedding_ldos")


def test_the_defect_keys_the_result():
    """Editing either system makes the result stale; a third one does not."""
    d, s, defect, e, t, c = chain_and_impurity()
    plan = pipeline.plan_calculation(d.document, c)
    assert plan.problem is None and plan.system_id == s and plan.embedding == e
    assert plan.others["defect"].system_id == defect
    key = plan.key
    other = d.do("add_system", lattice="square_lattice")
    d.do("add_term", system=other, kind="onsite", params={"mu": 0.3})
    assert pipeline.calculation_key(d.document, c) == key
    d.do("set_param", entry=t, name="mu", value=2.0)
    changed = pipeline.calculation_key(d.document, c)
    assert changed != key
    d.do("add_term", system=s, kind="onsite", params={"mu": 0.1})
    assert pipeline.calculation_key(d.document, c) != changed


def test_a_pair_without_a_common_cell_is_refused(pyqula):
    """The engine checks what the planner cannot know: the cells, the
    hoppings between them and the dimensionality."""
    d, s, defect, e, t, c = chain_and_impurity()
    shared = d.document.system(defect).geometry       # a new defect shares the cell (224)
    assert shared == d.document.system(s).geometry
    d.do("set_geometry", system=defect, geometry=d.do("duplicate", entry=shared))
    op = d.do("add_geometry_op", system=defect, kind="supercell", params={"n": [2, 1, 1]})
    with pytest.raises(CalculationError, match="not the pristine cell"):
        run_calculation(d.document, c)
    d.do("remove", entry=op)
    d.do("add_geometry_op", system=s, kind="supercell", params={"n": [2, 1, 1]})
    d.do("add_geometry_op", system=defect, kind="supercell", params={"n": [2, 1, 1]})
    d.do("add_term", system=defect, kind="strain",
         params={"s": {"kind": "expression", "expr": "1.0 + (x > 0.6)"}})
    with pytest.raises(CalculationError, match="hoppings between cells"):
        run_calculation(d.document, c)
    flake = Dispatcher()
    a = flake.do("add_system", lattice="chain")
    flake.do("add_geometry_op", system=a, kind="finite", params={})
    e2 = flake.do("add_embedding", pristine=a)
    c2 = flake.do("add_calculation", system=e2, kind="embedding_dos", params={"ne": 3})
    with pytest.raises(CalculationError, match="must be periodic"):
        run_calculation(flake.document, c2)


def test_the_script_builds_the_defect_first(pyqula):
    d, s, defect, e, _, c = chain_and_impurity()
    script = export_script(d.document, c)
    assert script.index(f"# defect: system {defect}") < script.index("\ndefect = h\n") \
        < script.index(f"# system {s}") < script.index("h, defect = embedded_pair(h, defect)")
    assert f"on embedding {e} (pristine {s}, defect {defect})" in script
    assert "def embedded_pair(h, defect):" in script


def ysr_sweep():
    """A Yu-Shiba-Rusinov chain: the in-gap state of an exchange-field
    impurity in an s-wave chain, swept over the exchange of the defect."""
    d = Dispatcher()
    s = d.do("add_system", lattice="chain")
    d.do("add_term", system=s, kind="swave", params={"delta": 0.2})
    e = d.do("add_embedding", pristine=s)
    t = d.do("add_term", system=d.document.embedding(e).defect, kind="zeeman",
             params={"m": [0.0, 0.0, 0.3]})
    c = d.do("add_calculation", system=e, kind="embedding_ingap", params={"ne": 21, "nk": 30})
    sweep = d.do("add_calculation", system=e, kind="sweep",
                 params={"calculation": c, "entry": t, "param": "m", "component": 2,
                         "start": 0.1, "stop": 0.5, "steps": 3})
    return d, sweep


def test_a_sweep_follows_the_in_gap_state(pyqula):
    """A sweep on an embedding changes the defect, and the in-gap state is a
    number: a Yu-Shiba-Rusinov state moves into the gap as the exchange of
    the impurity grows."""
    d, sweep = ysr_sweep()
    assert pipeline.plan_calculation(d.document, sweep).problem is None
    result = run_calculation(d.document, sweep)
    energies, gap = result.arrays["energy"], result.arrays["gap"]
    assert np.all(np.abs(energies) < gap / 2)
    assert abs(energies[-1]) < abs(energies[0])      # deeper into the gap


def test_the_cost_follows_the_window_and_the_modes():
    """In 2D the Green's function of the window costs in proportion to the
    k-points and to its orbitals (5 s measured for a 5x5 window of a cell of
    64 orbitals); a magnetic defect on a spinless crystal doubles them, since
    both are made spinful."""
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_construction", system=s, has_spin=False)
    e = d.do("add_embedding", pristine=s)
    c = d.do("add_calculation", system=e, kind="embedding_ldos",
             params={"window": 1, "nk": 100})
    builds = {s: {"dimension": 64, "dimensionality": 2, "sites": 32}}
    one = cost.estimate(d.document, c, builds)["seconds"]
    d.do("set_param", entry=c, name="window", value=5)
    five = cost.estimate(d.document, c, builds)["seconds"]
    assert 0.1 < one < 1.0 and 2.0 < five < 20.0
    d.do("add_term", system=d.document.embedding(e).defect, kind="zeeman",
         params={"m": [0.0, 0.0, 0.3]})
    assert cost.estimate(d.document, c, builds)["seconds"] > 1.9 * five


def test_the_script_of_a_sweep_changes_the_defect(pyqula, repo, tmp_path):
    """The loop of an exported sweep builds the defect at every value, and
    gives the engine's numbers."""
    from .test_script_export import assert_same_arrays, run_scripts
    d, sweep = ysr_sweep()
    expected = run_calculation(d.document, sweep).arrays
    got, = run_scripts([export_script(d.document, sweep)], repo, tmp_path)
    assert_same_arrays(expected, got, "sweep of the defect")


def test_a_pick_on_an_embedding_moves_its_calculations():
    """An energy picked on the embedded DOS moves the embedded LDOS and
    offers a new one on the embedding; no site or Fermi level target."""
    from guiqula.registry import picks
    d, s, defect, e, _, c = chain_and_impurity()
    targets = picks.targets(d.document, e, {"energy": 2.24}, source=c)
    labels = [t["label"] for t in targets]
    assert f"{c} Embedded LDOS: energy = 2.24" in labels
    assert any(t["target"] == "add" and t["system"] == e and t["kind"] == "embedding_ldos"
               for t in targets)
    assert not any(t["target"] in ("fermi_level", "region") for t in targets)


def test_the_result_says_the_matched_hilbert_space(pyqula):
    """A magnetic impurity on a spinless chain is computed spinful."""
    d, s, defect, e, t, c = chain_and_impurity()
    d.do("add_term", system=defect, kind="zeeman", params={"m": [0.0, 0.0, 0.5]})
    assert run_calculation(d.document, c).mode == "spinful"
