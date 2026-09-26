import json

import pytest

from guiqula.core.document import (Base, Calculation, Document, DocumentError, Entry, Geometry,
                                   Hamiltonian, System)
from guiqula.io import project


def small():
    return Document(systems=[System(id="s1", geometry=Geometry(base=Base(kind="chain")),
                                    hamiltonian=Hamiltonian(terms=[Entry(id="t1", kind="onsite")]))],
                    calculations=[Calculation(id="c1", system="s1", kind="bands")])


def test_roundtrip_and_ids():
    d = small()
    assert Document.from_json(d.to_json()) == d
    assert d.new_id("term") == "t2" and d.new_id("system") == "s2" and d.new_id("region") == "r1"
    assert d.find("t1")[0] == "term" and d.find("c1")[0] == "calculation"


@pytest.mark.parametrize("change, message", [
    (lambda data: data["calculations"][0].update(system="nope"), "missing system"),
    (lambda data: data["systems"][0]["hamiltonian"]["terms"][0].update(id="s1"), "duplicate"),
    (lambda data: data["systems"][0]["hamiltonian"]["terms"][0].update(region="r9"), "region"),
    (lambda data: data.update(version=99), "version"),
])
def test_inconsistent_documents_are_refused(change, message):
    data = json.loads(small().to_json())
    change(data)
    with pytest.raises(DocumentError, match=message):
        Document.from_data(data)


def test_unknown_keys_are_refused():
    data = json.loads(small().to_json())
    data["systems"][0]["geometry"]["bse"] = {}
    with pytest.raises(Exception):
        Document.from_data(data)


@pytest.mark.parametrize("suffix", [".guiqula", ".json"])
def test_save_load(tmp_path, suffix):
    path = project.save(small(), tmp_path / f"p{suffix}")
    assert project.load(path) == small()
    assert not list(tmp_path.glob("*.tmp"))


def test_presets_load_by_name():
    assert "honeycomb_zeeman_rashba" in project.presets()
    document = project.load("honeycomb_zeeman_rashba")
    assert [t.kind for t in document.systems[0].hamiltonian.terms] == ["zeeman", "rashba"]
    with pytest.raises(DocumentError, match="no such preset"):
        project.load("no_such_preset")
