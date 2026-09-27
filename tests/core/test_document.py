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
    assert {"honeycomb_zeeman_rashba", "honeycomb_hubbard"} <= set(project.presets())
    for name in project.presets():
        assert project.load(name).systems
    document = project.load("honeycomb_zeeman_rashba")
    assert [t.kind for t in document.systems[0].hamiltonian.terms] == ["zeeman", "rashba"]
    with pytest.raises(DocumentError, match="no such preset"):
        project.load("no_such_preset")


def test_a_preset_name_is_the_preset_beside_a_folder_of_that_name(tmp_path):
    """The gallery hands over bare names: a folder called like a preset in
    the working directory (a second `guiqula run P --out P`) must not hide
    the preset; a folder named with a path is refused plainly."""
    (tmp_path / "ssh_chain").mkdir()
    assert project.resolve("ssh_chain") == project.preset_path("ssh_chain")
    assert project.load("ssh_chain").systems
    with pytest.raises(DocumentError, match="a folder"):
        project.load(str(tmp_path / "ssh_chain"))


def _result(arrays):
    import numpy as np
    from guiqula.core.results import Result
    return Result(calculation="c1", kind="bands", key="k", params={},
                  arrays={k: np.asarray(v) for k, v in arrays.items()},
                  plot={"kind": "lines", "x": "k", "y": "energies"})


def test_a_damaged_result_does_not_keep_a_project_from_opening(tmp_path):
    """One unreadable result is left out, and said why; the Document still
    opens. Arrays of Python objects are not written at all (loading never
    unpickles), and a damaged file is a DocumentError, not a raw traceback."""
    import zipfile
    good = project.save(small(), tmp_path / "good.guiqula",
                        {"c1": _result({"k": [0.0, 1.0], "energies": [0.0, 1.0]})})
    assert set(project.load_results(good)) == {"c1"}
    damaged = tmp_path / "damaged.guiqula"
    with zipfile.ZipFile(good) as source, zipfile.ZipFile(damaged, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            target.writestr(name, data[:len(data) // 2] if name.endswith(".npz") else data)
    problems = []
    assert project.load(damaged) == small()
    assert project.load_results(damaged, problems) == {} and "c1" in problems[0]
    with pytest.raises(ValueError, match="allow_pickle"):
        from guiqula.io import results as result_files
        result_files.to_bytes(_result({"k": [0.0], "info": {"nk": 10}}))
    kept = project.save(small(), tmp_path / "objects.guiqula",
                        {"c1": _result({"k": [0.0], "info": {"nk": 10}})})
    assert project.load(kept) == small() and project.load_results(kept) == {}
    truncated = tmp_path / "truncated.guiqula"
    truncated.write_bytes(good.read_bytes()[:40])
    with pytest.raises(DocumentError, match="damaged"):
        project.load(truncated)
