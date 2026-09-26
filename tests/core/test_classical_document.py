"""Classical systems in the Document (decision 13.5): a model block in
place of the Hamiltonian, set up and edited through commands, with its
terms among the document's entries (ids, regions, duplicate, undo)."""
import pytest

from guiqula.commands import CommandError, Dispatcher
from guiqula.core.document import Document, DocumentError, terms_of
from guiqula.io import project
from guiqula.registry import pipeline


def gas():
    d = Dispatcher()
    s = d.do("add_system", lattice="triangular_lattice", kind="lattice_gas",
             model_params={"filling": 0.25})
    r = d.do("add_region", system=s, select={"kind": "expression", "expr": "x > 0"})
    t = d.do("add_term", system=s, kind="chemical_potential", params={"mu": 0.3}, region=r)
    return d, s, r, t


def test_a_classical_system_round_trips():
    d, s, r, t = gas()
    system = d.document.system(s)
    assert system.hamiltonian is None and system.model.kind == "lattice_gas"
    assert system.model.params == {"filling": 0.25, "seed": 1}
    assert d.document.find(t)[0] == "term" and t in d.document.all_ids()
    again = Document.from_json(d.document.to_json())
    assert again == d.document and terms_of(again.system(s))[0].id == t


def test_model_commands_and_undo():
    d, s, r, t = gas()
    d.do("set_model", system=s, params={"filling": 0.5})
    assert d.document.system(s).model.params["filling"] == 0.5
    with pytest.raises(CommandError, match="must be at most 1"):
        d.do("set_model", system=s, params={"filling": 2.0})
    d.undo()
    assert d.document.system(s).model.params["filling"] == 0.25
    q = d.do("add_system")
    with pytest.raises(CommandError, match="no classical model"):
        d.do("set_model", system=q, params={})
    with pytest.raises(CommandError, match="unknown system kind"):
        d.do("add_system", kind="quark")


def test_duplicate_and_remove():
    d, s, r, t = gas()
    copy = d.do("duplicate", entry=s)
    term = terms_of(d.document.system(copy))[0]
    assert term.id != t and term.region != r
    assert term.region == d.document.system(copy).regions[0].id
    with pytest.raises(CommandError, match="is used by"):
        d.do("remove", entry=r)                # a model term uses it
    d.do("remove", entry=t)
    d.do("remove", entry=r)


def test_the_schema_is_checked():
    d, s, r, t = gas()
    data = d.document.model_dump(mode="json")
    data["systems"][0]["model"] = None
    with pytest.raises(DocumentError, match="needs a model"):
        Document.from_data(data)
    data = d.document.model_dump(mode="json")
    data["systems"][0]["kind"] = "ising"
    with pytest.raises(DocumentError, match="its model is lattice_gas"):
        Document.from_data(data)


def test_plan_of_a_classical_system():
    d, s, r, t = gas()
    plan = pipeline.plan_system(d.document, s)
    assert [st.stage for st in plan.stages] == ["base", "model", "term"]
    assert plan.mode == "lattice gas" and plan.meanfield is None and plan.problem is None
    key = plan.key
    d.do("set_model", system=s, params={"seed": 2})     # another random start: another key
    assert pipeline.plan_system(d.document, s).key != key


@pytest.mark.parametrize("name", project.presets())
def test_presets_still_load(name):
    assert project.load(name).systems
