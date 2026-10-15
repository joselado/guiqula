"""The k-path as an object of the Document (PLAN.md phase 9, part A,
decisions 214 to 221 and 234 to 236): shared by id, resolved into its
vertices by the planner, lifted from older files, refused while used."""
import json

import pytest

from guiqula.commands.dispatcher import CommandError, Dispatcher
from guiqula.core.document import Document, kpath_users
from guiqula.registry import pipeline

# a document of before phase 9: two band structures and a spectral function of
# one system, two on pyqula's default path (null and left out) and one on its own
OLD = {
    "version": 1,
    "systems": [{"id": "s1", "geometry": {"base": {"kind": "honeycomb_lattice"}}},
                {"id": "s2", "geometry": {"base": {"kind": "square_lattice"}}}],
    "calculations": [
        {"id": "c1", "system": "s1", "kind": "bands", "params": {"kpath": None}},
        {"id": "c2", "system": "s1", "kind": "bands", "name": "along K",
         "params": {"kpath": ["G", "K", [0.5, 0.0]]}},
        {"id": "c3", "system": "s1", "kind": "dos"},
        {"id": "c4", "system": "s1", "kind": "bands"},
        {"id": "c5", "system": "s2", "kind": "bands"},
    ],
}


def test_an_older_file_is_lifted_into_shared_kpaths():
    document = Document.from_data(json.loads(json.dumps(OLD)))
    data = json.loads(document.to_json())
    assert data["kpaths"] == [{"id": "k1", "vertices": []},
                              {"id": "k2", "name": "along K",
                               "vertices": ["G", "K", [0.5, 0.0, 0.0]]},
                              {"id": "k3", "vertices": []}]
    kpath = {c["id"]: c["params"].get("kpath") for c in data["calculations"]}
    # the default path of one system is one k-path; another system has its own
    assert kpath == {"c1": "k1", "c2": "k2", "c3": None, "c4": "k1", "c5": "k3"}
    assert kpath_users(document, "k1") == ["c1", "c4"]
    # reading it again changes nothing (the worker keys the Document from its JSON)
    assert Document.from_json(document.to_json()).to_json() == document.to_json()


def test_the_key_hashes_the_vertices_and_never_the_id():
    document = Document.from_data(json.loads(json.dumps(OLD)))
    plan = pipeline.plan_calculation(document, "c2")
    assert plan.problem is None
    assert plan.params["kpath"] == ["G", "K", [0.5, 0.0, 0.0]]     # what the entry reads
    assert pipeline.plan_calculation(document, "c1").params["kpath"] is None   # the default
    d = Dispatcher(document)
    copy = d.do("add_kpath", vertices=["G", "K", [0.5, 0.0]])
    key = pipeline.calculation_key(d.document, "c2")
    d.do("set_param", entry="c2", name="kpath", value=copy)
    assert pipeline.calculation_key(d.document, "c2") == key      # the same path: current
    d.do("set_kpath", kpath=copy, vertices=["G", "M"])
    assert pipeline.calculation_key(d.document, "c2") != key


def test_a_new_calculation_walks_the_last_kpath_of_its_system():
    d = Dispatcher(Document())
    s1 = d.do("add_system", lattice="honeycomb_lattice")
    c1 = d.do("add_calculation", system=s1, kind="bands")
    k1 = d.document.calculation(c1).params["kpath"]
    assert d.document.kpath(k1).vertices == []                   # pyqula's default path
    d.do("set_kpath", kpath=k1, vertices=["G", "K", "M", "G"])
    c2 = d.do("add_calculation", system=s1, kind="bands")
    assert d.document.calculation(c2).params["kpath"] == k1      # the path last used
    s2 = d.do("add_system", lattice="square_lattice")
    c3 = d.do("add_calculation", system=s2, kind="bands")
    assert d.document.calculation(c3).params["kpath"] != k1      # another system: a new one
    c4 = d.do("add_calculation", system=s1, kind="bands", params={"kpath": ["G", "M"]})
    own = d.document.calculation(c4).params["kpath"]             # vertices: a k-path of its own
    assert d.document.kpath(own).vertices == ["G", "M"] and d.document.kpath(own).name == c4
    with pytest.raises(CommandError, match="no k-path"):
        d.do("set_param", entry=c2, name="kpath", value="k99")


def test_a_used_kpath_is_not_removed_and_single_user_copies_it():
    d = Dispatcher(Document())
    s1 = d.do("add_system", lattice="honeycomb_lattice")
    c1 = d.do("add_calculation", system=s1, kind="bands")
    c2 = d.do("add_calculation", system=s1, kind="bands")
    k1 = d.document.calculation(c1).params["kpath"]
    d.do("set_kpath", kpath=k1, vertices=["G", "K"])
    with pytest.raises(CommandError, match="walked by"):
        d.do("remove", entry=k1)
    own = d.do("single_user_kpath", calculation=c2)
    assert d.document.kpath(own).vertices == ["G", "K"] and kpath_users(d.document, k1) == [c1]
    new = d.do("single_user_kpath", calculation=c1, copy=False)
    assert d.document.kpath(new).vertices == []
    d.do("remove", entry=k1)                                    # nobody walks it any more
    assert k1 not in {k.id for k in d.document.kpaths}


def test_a_lock_of_a_calculation_covers_the_kpath_it_walks():
    """Decision 234: a k-path is shared, so editing it through anything else
    changes a locked calculation that walks it."""
    d = Dispatcher(Document())
    s1 = d.do("add_system", lattice="honeycomb_lattice")
    c1 = d.do("add_calculation", system=s1, kind="bands")
    c2 = d.do("add_calculation", system=s1, kind="bands")
    k1 = d.document.calculation(c1).params["kpath"]
    d.do("lock", target=c1)
    with pytest.raises(CommandError, match="locked"):
        d.do("set_kpath", kpath=k1, vertices=["G", "K"])
    own = d.do("single_user_kpath", calculation=c2)               # c2 alone: allowed
    d.do("set_kpath", kpath=own, vertices=["G", "K"])


def test_a_missing_kpath_is_a_problem_of_the_plan():
    document = Document.from_data(json.loads(json.dumps(OLD)))
    document.calculation("c1").params["kpath"] = "k9"
    assert "no k-path 'k9'" in pipeline.plan_calculation(document, "c1").problem
