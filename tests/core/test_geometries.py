"""The geometry as an object of the Document (PLAN.md phase 9, part B,
decisions 222 to 225 and 240 on): schema version 2, a version-1 file lifted
into one geometry per system, a geometry shared by several systems, one
starting from another, and what refuses an edit."""
import json

import pytest

from guiqula.commands.dispatcher import CommandError, Dispatcher
from guiqula.core.document import Document, DocumentError, SCHEMA_VERSION, geometry_chain
from guiqula.registry import pipeline

V1 = {
    "version": 1,
    "systems": [
        {"id": "s1", "geometry": {"base": {"kind": "honeycomb_lattice"},
                                  "ops": [{"id": "op1", "kind": "supercell",
                                           "params": {"n": [2, 2, 1]}}]},
         "regions": [{"id": "r1", "name": "left",
                      "select": {"kind": "expression", "expr": "x < 0"}}],
         "hamiltonian": {"terms": [{"id": "t1", "kind": "onsite", "region": "r1",
                                    "params": {"mu": 0.3}}]}},
        {"id": "s2", "geometry": {"base": {"kind": "square_lattice"}}},
    ],
    "calculations": [{"id": "c1", "system": "s1", "kind": "dos"}],
}


def test_a_version_1_file_gets_one_geometry_per_system():
    document = Document.from_data(json.loads(json.dumps(V1)))
    assert document.version == SCHEMA_VERSION == 2
    assert [g.id for g in document.geometries] == ["geo1", "geo2"]
    assert [s.geometry for s in document.systems] == ["geo1", "geo2"]
    assert [r.id for r in document.geometry("geo1").regions] == ["r1"]    # ids kept
    assert document.find("op1")[1].id == "geo1" and document.find("r1")[0] == "region"
    again = Document.from_json(document.to_json())                  # nothing more to lift
    assert again.to_json() == document.to_json()


def test_a_shared_geometry_is_built_once_and_edited_for_all():
    d = Dispatcher(Document.from_data(json.loads(json.dumps(V1))))
    key = pipeline.plan_system(d.document, "s1").stages[1].key
    s3 = d.do("add_system", geometry="geo1")                   # New Hamiltonian on it
    assert d.document.systems_on("geo1") == ["s1", s3]
    assert pipeline.plan_system(d.document, s3).stages[1].key == key   # one cache entry
    d.do("add_term", system=s3, kind="onsite", region="r1", params={"mu": -0.3})
    d.do("set_param", entry="op1", name="n", value=[3, 3, 1])
    assert pipeline.plan_system(d.document, s3).stages[1].key == \
        pipeline.plan_system(d.document, "s1").stages[1].key != key
    linked = d.do("duplicate_linked", system="s1")             # Alt+D
    assert d.document.system(linked).geometry == "geo1"
    assert d.document.system(linked).hamiltonian.terms[0].region == "r1"
    copy = d.do("duplicate", entry="s1")                       # Ctrl+D copies it
    assert d.document.system(copy).geometry not in ("geo1", "geo2")
    with pytest.raises(CommandError, match="geometry of systems"):
        d.do("remove", entry="geo1")
    with pytest.raises(CommandError, match=r"used by \['t1'"):
        d.do("remove", entry="r1")                             # by a term of any system on it


def test_a_geometry_starts_from_another_and_follows_it():
    """A ribbon cut from a decorated cell: its stages are the cell's, then
    its own, so an edit of the cell reaches it; a cycle is refused."""
    d = Dispatcher()
    cell = d.do("add_system", lattice="honeycomb_lattice")
    geo = d.document.system(cell).geometry
    d.do("add_geometry_op", system=cell, kind="supercell", params={"n": [2, 1, 1]})
    ribbon_geometry = d.do("add_geometry", parent=geo)
    d.do("add_geometry_op", system=ribbon_geometry, kind="ribbon")
    ribbon = d.do("add_system", geometry=ribbon_geometry)
    plan = pipeline.plan_system(d.document, ribbon)
    assert [s.kind for s in plan.stages[:3]] == ["honeycomb_lattice", "supercell", "ribbon"]
    before = plan.key
    d.do("set_param", entry=d.document.geometry(geo).ops[0].id, name="n", value=[3, 1, 1])
    assert pipeline.plan_system(d.document, ribbon).key != before
    assert [g.id for g in geometry_chain(d.document, ribbon_geometry)] == [geo, ribbon_geometry]
    with pytest.raises(CommandError, match="starts from itself"):
        d.do("set_parent", geometry=geo, parent=ribbon_geometry)
    with pytest.raises(CommandError, match="geometry of systems"):
        d.do("remove", entry=geo)
    d.do("set_geometry", system=cell, geometry=ribbon_geometry)  # the cell is nobody's now
    with pytest.raises(CommandError, match="start from it|where geometries"):
        d.do("remove", entry=geo)                               # but the ribbon starts there


def test_a_lock_of_a_geometry_covers_every_system_on_it():
    d = Dispatcher(Document.from_data(json.loads(json.dumps(V1))))
    s3 = d.do("add_system", geometry="geo1")
    d.do("lock", target="s1/geometry")
    with pytest.raises(CommandError, match="locked"):
        d.do("add_geometry_op", system=s3, kind="ribbon")      # through the other system
    d.do("unlock")
    d.do("lock", target="geo1")
    with pytest.raises(CommandError, match="locked"):
        d.do("set_param", entry="op1", name="n", value=[1, 1, 1])


def test_a_new_defect_is_built_on_the_pristine_geometry():
    """Decision 224: the two cells are one, so the check of the engine that
    they match holds by construction."""
    d = Dispatcher()
    s = d.do("add_system", lattice="chain")
    e = d.do("add_embedding", pristine=s)
    defect = d.document.embedding(e).defect
    assert d.document.system(defect).geometry == d.document.system(s).geometry


def test_a_broken_geometry_reference_is_refused():
    data = json.loads(Document.from_data(json.loads(json.dumps(V1))).to_json())
    data["systems"][1]["geometry"] = "geo9"
    with pytest.raises(DocumentError, match="missing geometry"):
        Document.from_data(data)
    data = json.loads(Document.from_data(json.loads(json.dumps(V1))).to_json())
    data["geometries"][1]["parent"] = "geo1"                    # a base and a parent
    with pytest.raises(DocumentError, match="one of the two"):
        Document.from_data(data)
