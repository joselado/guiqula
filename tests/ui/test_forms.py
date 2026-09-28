"""A properties form builds for every entry of the registry, with one
editor per parameter, and an edit of every kind of editor goes through
the dispatcher (PLAN.md 3.2: the form is derived from the declaration)."""
import pytest

from guiqula import registry
from guiqula.session import Session
from guiqula.ui.forms import FloatVectorEditor, LineEditor
from guiqula.ui.properties import EntryForm, PropertiesPanel

FAMILIES = {"geometry_op": "add_geometry_op", "term": "add_term",
            "calculation": "add_calculation"}


@pytest.fixture
def panel(qapp, no_jobs):
    session = Session(jobs=no_jobs)
    session.do("add_system", lattice="honeycomb_lattice")

    def run(command, /, **args):          # the window's convention: (ok, result or message)
        try:
            return True, session.run(command, **args)
        except Exception as error:
            return False, str(error)
    panel = PropertiesPanel(run)
    panel.resize(360, 700)
    yield panel, session
    session.close()


@pytest.mark.parametrize("spec", [s for f in FAMILIES for s in registry.entries(f)],
                         ids=lambda s: f"{s.family}:{s.kind}")
def test_every_entry_has_a_form(panel, spec):
    panel, session = panel
    system = "s1"
    if "quantum" not in spec.systems:             # a system of a kind it applies to
        system = session.do("add_system", lattice="square_lattice", kind=spec.systems[0])
    entry = session.do(FAMILIES[spec.family], system=system, kind=spec.kind)
    panel.show_item(session, entry)
    form = panel.form
    assert isinstance(form, EntryForm) and form.spec is spec
    assert set(form.editors) == {p.name for p in spec.params}


def test_new_editors_commit(panel):
    panel, session = panel
    op = session.do("add_geometry_op", system="s1", kind="shift")
    panel.show_item(session, op)
    editor = panel.form.editors["d"]
    assert isinstance(editor, FloatVectorEditor)
    editor.edits[1].setText("0.25")
    editor.edits[1].editingFinished.emit()
    assert session.document.find(op)[-1].params["d"] == [0.5, 0.25, 0.0]
    keep = session.do("add_geometry_op", system="s1", kind="keep_where")
    panel.show_item(session, keep)
    editor = panel.form.editors["condition"]
    assert isinstance(editor, LineEditor)
    editor.edit.setText("abs(y) < 3")
    editor.edit.editingFinished.emit()
    assert session.document.find(keep)[-1].params["condition"] == "abs(y) < 3"
    editor.edit.setText("import os")                 # refused: the form shows the stored value
    editor.edit.editingFinished.emit()
    assert session.document.find(keep)[-1].params["condition"] == "abs(y) < 3"


def test_an_optional_vector_can_be_empty(panel):
    """The LDOS's k-point (phase 7): empty boxes are None, over the k-mesh;
    three numbers are one k-point; emptied again, it is None again."""
    panel, session = panel
    calc = session.do("add_calculation", system="s1", kind="ldos")
    panel.show_item(session, calc)
    editor = panel.form.editors["k"]
    assert isinstance(editor, FloatVectorEditor)
    assert [e.text() for e in editor.edits] == ["", "", ""]
    assert editor.edits[0].placeholderText() == "empty"
    for edit, text in zip(editor.edits, ("0.5", "0", "0")):
        edit.setText(text)
    editor.edits[2].editingFinished.emit()
    assert session.document.calculation(calc).params["k"] == [0.5, 0.0, 0.0]
    panel.show_item(session, calc)
    editor = panel.form.editors["k"]
    for edit in editor.edits:
        edit.setText("")
    editor.edits[0].editingFinished.emit()
    assert session.document.calculation(calc).params["k"] is None


def test_lattice_parameters(panel):
    """A lattice that takes parameters (a ribbon's width) shows them in the
    system's form; an edit goes through set_param on the system."""
    from guiqula.ui.forms import IntEditor
    from guiqula.ui.properties import SystemForm
    panel, session = panel
    session.do("set_lattice", system="s1", lattice="honeycomb_zigzag_ribbon")
    panel.show_item(session, "s1")
    assert isinstance(panel.form, SystemForm)
    editor = panel.form.editors["width"]
    assert isinstance(editor, IntEditor) and editor.value() == 10
    editor.spin.setValue(4)
    assert session.document.system("s1").geometry.base.params == {"width": 4}
    session.do("set_lattice", system="s1", lattice="multilayer_graphene")
    panel.show_item(session, "s1")
    assert panel.form.editors["stacking"].value() == "AB"
