"""The embedding in the window: its row in the outliner with the two
systems under it, which select those systems; its form, whose combos name
them; the Add menu of the calculations listing the embedding's entries
while it is selected; the New embedding of a quantum system's context
menu; and the warning when the two cells differ (from the builds)."""
import numpy as np
import pytest
from PySide6.QtWidgets import QComboBox, QLabel

from guiqula.session import Session
from guiqula.ui.app import build_main_window
from guiqula.ui.properties import EmbeddingForm, sweep_target


@pytest.fixture
def still(qapp, no_jobs):
    """A window over a session that runs nothing: a chain (s1), its copy as
    a defect with an onsite impurity (s2), their embedding (e1) and an
    in-gap state on it (c1)."""
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    session = Session(jobs=no_jobs)
    session.do("add_system", lattice="chain")
    window.attach(session)
    session.do("add_embedding", pristine="s1")
    session.do("add_term", system="s2", kind="onsite", params={"mu": 1.0})
    session.do("add_calculation", system="e1", kind="embedding_ingap")
    yield window, session
    window.close()
    session.close()


def test_the_outliner_shows_the_embedding_and_its_systems(still):
    window, session = still
    outliner = window.outliner
    assert outliner.item("e1").text(1) == "s2 in s1"
    assert outliner.item("e1/pristine").text(0).startswith("Pristine  s1")
    assert outliner.item("e1/defect").text(0).startswith("Defect  s2")
    window.select("e1/defect")                 # a row under the embedding selects its system
    assert window.selected == "s2" and window.current_system() == "s2"
    window.select("e1")
    assert window.workspace == "calculate" and window.current_system() == "s2"   # the canvas
    assert window.current_target() == "e1"
    window.select("c1")                        # a calculation on it: the same
    assert window.current_target() == "e1" and window.current_system() == "s2"


def test_the_form_names_the_two_systems(still):
    window, session = still
    other = session.do("add_system", lattice="chain")
    window.select("e1")
    form = window.properties.form
    assert isinstance(form, EmbeddingForm)
    box = form.findChild(QComboBox, "embedding_pristine")
    assert [box.itemData(i) for i in range(box.count())] == ["s1", "s2", other]
    box.setCurrentIndex(box.findData(other))
    box.activated.emit(box.currentIndex())
    assert session.document.embedding("e1").pristine == other
    box = window.properties.form.findChild(QComboBox, "embedding_defect")
    box.setCurrentIndex(box.findData(other))   # the pristine one: refused, said in the form
    box.activated.emit(box.currentIndex())
    assert session.document.embedding("e1").defect == "s2"
    assert "its own" in window.properties.form.error.text()


def test_the_add_menu_follows_the_embedding(still):
    """The calculations' Add menu lists the embedding's entries while it is
    selected, a system's otherwise, and adds to what it lists for."""
    window, session = still

    def listed():
        return set(window.palette_menu("calculation").entries)
    window.select("e1")
    kinds = listed()
    assert {"embedding_ldos", "embedding_dos", "embedding_ingap"} <= kinds
    assert "bands" not in kinds
    calc = window.add_calculation("embedding_dos")
    assert session.document.calculation(calc).system == "e1"
    window.select("s1")
    kinds = listed()
    assert "bands" in kinds and "embedding_dos" not in kinds


def test_a_quantum_system_offers_a_new_embedding(still):
    window, session = still
    window._outliner_command("add_embedding", {"pristine": "s1"})
    assert window.selected == "e2" and session.document.embedding("e2").defect == "s3"


def test_a_sweep_of_the_defect_runs_the_embedding(still):
    """A sweep from a parameter of the defect's terms runs a calculation of
    the embedding, which it is added to."""
    window, session = still
    assert sweep_target(session, "s2", "t1") == "c1"
    window.select("t1")
    sweep = window.properties.form.sweep("mu")
    assert session.document.calculation(sweep).system == "e1"


def test_cells_that_differ_are_said_before_a_run(still, monkeypatch):
    """From the builds the window holds: a defect in a supercell of the
    pristine cell is flagged on the embedding's row and in its form."""
    from types import SimpleNamespace

    from guiqula.ui import outliner, properties
    window, session = still
    embedding = session.document.embedding("e1")

    def build(positions, dimensionality=1):
        return {"positions": np.asarray(positions, dtype=float),
                "dimensionality": dimensionality}
    fake = SimpleNamespace(builds={"s1": build([[0.0, 0, 0]]),
                                   "s2": build([[0.0, 0, 0], [1.0, 0, 0]])})
    problem = outliner.cell_problem(fake, embedding)
    assert "(2 sites) is not the pristine cell (1 site)" in problem
    fake.builds["s2"] = build([[0.0, 0, 0]])
    assert outliner.cell_problem(fake, embedding) is None
    fake.builds = {"s1": build([[0.0, 0, 0]], 0), "s2": build([[0.0, 0, 0]], 0)}
    assert "must be periodic" in outliner.cell_problem(fake, embedding)
    assert outliner.cell_problem(SimpleNamespace(builds={}), embedding) is None   # not built
    monkeypatch.setattr(outliner, "cell_problem", lambda session, e: problem)
    monkeypatch.setattr(properties, "cell_problem", lambda session, e: problem)
    window.outliner.refresh(session)
    assert problem in window.outliner.item("e1").toolTip(0)
    window.select("e1")
    assert problem in window.properties.form.findChild(QLabel, "embeddingInfo").text()
