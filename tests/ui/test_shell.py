"""The phase-2 shell driven offscreen: outliner, properties forms,
palettes, the structure canvas with its overlays, crash reports, the
recovery bar, the close prompt (PLAN.md section 4, 3.5, 13.14)."""
import json
import subprocess
import sys

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QToolButton

from guiqula.io import autosave, project
from guiqula.session import Session
from guiqula.ui import errors
from guiqula.ui.app import build_main_window
from guiqula.ui.properties import EntryForm, RegionForm, SystemForm


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def settled(window):
    session = window.session
    return not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems)


def settle(qtbot, window, timeout=120_000):
    qtbot.waitUntil(lambda: settled(window), timeout=timeout)


def fresh(qtbot, window):
    window.session.act("load", path="honeycomb_zeeman_rashba")
    window.select("")
    settle(qtbot, window)


def menu_action(window, button, name):
    menu = window.findChild(QToolButton, button).menu()
    return next(a for a in menu.actions() if a.objectName() == name)


def scatter(ax, zorder):
    return [c for c in ax.collections if c.get_zorder() == zorder]


def test_outliner_checkbox_toggles_and_undo(window, qtbot):
    fresh(qtbot, window)
    item = window.outliner.item("t2")
    assert item.checkState(0).name == "Checked"
    item.setCheckState(0, item.checkState(0).__class__.Unchecked)
    qtbot.waitUntil(lambda: not window.session.document.find("t2")[-1].enabled, timeout=5000)
    assert window.outliner.item("t2").text(1) == "disabled"
    window.undo_action.trigger()
    assert window.session.document.find("t2")[-1].enabled
    assert window.outliner.item("t2").checkState(0).name == "Checked"


def test_select_action_drives_properties_and_viewport(window, qtbot):
    fresh(qtbot, window)
    assert window.session.act("select", entry="t2") == "t2"
    form = window.properties.form
    assert isinstance(form, EntryForm) and form.title.text() == "Rashba spin-orbit coupling"
    assert window.outliner.current_id() == "t2" and window.viewport.currentIndex() == 0
    assert "Hilbert space after it: spinful" in form.status.text()
    window.session.act("select", entry="c2")
    assert window.viewport.currentIndex() == 1 and window.selected_calculation() == "c2"
    window.session.act("select", entry="s1/base")
    assert isinstance(window.properties.form, SystemForm)
    assert window.properties.form.lattice.currentData() == "honeycomb_lattice"
    assert "8 sites" in window.properties.form.info.text()
    assert not window.session.dispatcher.can_undo()          # selection is not undoable
    assert not window.build_timer.isActive()                 # nor a reason to rebuild
    with pytest.raises(ValueError, match="nothing called"):
        window.session.act("select", entry="t99")


def test_property_edit_commits_and_refusal_reverts(window, qtbot):
    fresh(qtbot, window)
    window.select("t2")
    editor = window.properties.form.editors["c"]
    editor.edit.setText("0.25")
    editor.edit.editingFinished.emit()
    assert window.session.document.find("t2")[-1].params["c"] == 0.25
    editor = window.properties.form.editors["c"]      # updated in place, same form
    editor.edit.setText("0.1*nope(x)")
    editor.edit.editingFinished.emit()
    assert "nope" in window.properties.form.error.text()
    assert window.session.document.find("t2")[-1].params["c"] == 0.25
    assert window.properties.form.editors["c"].edit.text() == "0.25"
    editor.edit.setText("0.2*tanh(x)")                  # an expression of position
    editor.edit.editingFinished.emit()
    assert window.session.document.find("t2")[-1].params["c"] == "0.2*tanh(x)"
    assert window.properties.form.error.text() == ""
    window.select("op1")
    spins = window.properties.form.editors["n"].spins
    spins[0].setValue(3)                                  # arrows commit immediately
    assert window.session.document.find("op1")[-1].params["n"] == [3, 2, 1]
    assert "ERROR: set_param" in window.log.toPlainText()


def test_palettes_add_and_select(window, qtbot):
    fresh(qtbot, window)
    menu_action(window, "addOpButton", "addOp_island").trigger()
    op = window.selected
    assert window.session.document.find(op)[-1].kind == "island"
    assert isinstance(window.properties.form, EntryForm)
    settle(qtbot, window)
    assert window.builds["s1"]["dimensionality"] == 0
    assert "0D" in window.structure.caption.text()
    menu_action(window, "addTermButton", "addTerm_haldane").trigger()
    assert window.session.document.find(window.selected)[-1].kind == "haldane"
    menu_action(window, "addCalculationButton", "addCalc_dos").trigger()
    assert window.selected == "c3" and window.viewport.currentIndex() == 1
    menu_action(window, "newSystemButton", "newSystem_kagome_lattice").trigger()
    assert window.selected == "s2" and isinstance(window.properties.form, SystemForm)
    form = window.properties.form
    form.lattice.setCurrentIndex(form.lattice.findData("lieb_lattice"))
    form.lattice.activated.emit(form.lattice.currentIndex())
    assert window.session.document.system("s2").geometry.base.kind == "lieb_lattice"
    settle(qtbot, window)
    assert window.builds["s2"]["sites"] == 3 and window.structure.system_id == "s2"


def test_structure_canvas_and_overlays(window, qtbot, shot):
    fresh(qtbot, window)
    ax = window.structure.ax
    atoms = scatter(ax, 4)[0]
    assert len(atoms.get_offsets()) == 8                # the central cell's sites
    positions = window.builds["s1"]["positions"]
    removed = [list(positions[0]), list(positions[5])]
    op = window.session.do("add_geometry_op", system="s1", kind="remove_atoms",
                           params={"positions": removed})
    region = window.session.do("add_region", system="s1",
                               select={"kind": "expression", "expr": "x > 0.1"}, name="right")
    settle(qtbot, window)
    window.select(op)
    assert len(scatter(window.structure.ax, 7)[0].get_offsets()) == 2      # the removed sites
    assert len(scatter(window.structure.ax, 4)[0].get_offsets()) == 6
    window.select(region)
    assert isinstance(window.properties.form, RegionForm)
    rings = scatter(window.structure.ax, 5)[0].get_offsets()
    assert len(rings) == int((window.builds["s1"]["positions"][:, 0] > 0.1).sum()) > 0
    assert window.properties.form.sites.text().startswith(f"{len(rings)} of 6")
    shot(window, "region_overlay")


def test_selection_to_removal_and_region(window, qtbot, shot):
    """Select on the canvas, remove the selection (one Remove atoms op that
    grows), make a region from a selection, all undoable. The preset's 2x2
    honeycomb cell has sites at x = -2, -1, 1, 2 (y = 0) and x = +-0.5
    (y = +-0.87), sublattices alternating."""
    fresh(qtbot, window)
    session = window.session
    assert not window.remove_button.isEnabled()
    assert session.act("select_sites", box=[0.9, -2.0, 2.1, 2.0]) == 2      # x = 1 and 2
    assert window.remove_button.isEnabled() and "2 selected" in window.structure.caption.text()
    op = session.act("remove_selected")
    assert window.selected == op and window.structure.selected().tolist() == []
    assert len(session.document.find(op)[-1].params["positions"]) == 2
    settle(qtbot, window)
    assert window.builds["s1"]["sites"] == 6
    assert 0 < session.act("select_sites", edge=True) < 6    # the neighbours of the hole
    assert session.act("select_sites", sublattice=1) == 3
    assert session.act("remove_selected") == op          # the trailing removal op grows
    assert len(session.document.find(op)[-1].params["positions"]) == 5
    settle(qtbot, window)
    assert window.builds["s1"]["sites"] == 3
    shot(window, "removed")
    assert session.act("select_sites", point=[100.0, 100.0]) == 0
    with pytest.raises(ValueError, match="no sites are selected"):
        session.act("region_from_selection")
    with pytest.raises(ValueError, match="exactly one"):
        session.act("select_sites", all=True, edge=True)
    assert session.act("select_sites", all=True) == 3
    assert session.act("select_sites", indices=[0], mode="remove") == 2
    region = session.act("region_from_selection", name="picked")
    select = session.document.find(region)[-1].select
    assert select["kind"] == "positions" and len(select["positions"]) == 2
    assert isinstance(window.properties.form, RegionForm)
    session.act("select_sites", indices=[])
    window.properties.form.show_sites.click()            # the region form selects its sites
    assert len(window.structure.selected()) == 2
    session.undo()                                       # the region
    session.undo()                                       # the grown removal
    assert len(session.document.find(op)[-1].params["positions"]) == 2


def test_report_exception_writes_a_crash_report(window, tmp_path, monkeypatch):
    monkeypatch.setenv("GUIQULA_DATA_DIR", str(tmp_path))
    try:
        raise ZeroDivisionError("in a slot")
    except ZeroDivisionError:
        window.report_exception(*sys.exc_info())
    folder = window.last_crash_report
    assert folder.parent == tmp_path / "crash-reports"
    assert "ZeroDivisionError" in (folder / "traceback.txt").read_text()
    assert json.loads((folder / "document.json").read_text())["systems"]
    assert window.error_bar.isVisible() and "keeps running" in window.error_bar.label.text()
    assert window.error_bar.button("openReportButton") is not None
    window.error_bar.close_button.click()
    assert not window.error_bar.isVisible()


@pytest.mark.qt_no_exception_capture
def test_exception_hook_catches_qt_callbacks(window, qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("GUIQULA_DATA_DIR", str(tmp_path))
    previous = errors.install(window)
    try:
        QTimer.singleShot(0, lambda: {}["missing key in a timer"])
        qtbot.waitUntil(lambda: window.error_bar.isVisible(), timeout=5000)
    finally:
        sys.excepthook = previous
    assert "KeyError" in window.error_bar.label.text()
    assert (window.last_crash_report / "traceback.txt").exists()
    window.error_bar.dismiss()


def dead_pid():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_recovery_bar(window, qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("GUIQULA_DATA_DIR", str(tmp_path))
    document = project.load("honeycomb_zeeman_rashba")
    document.systems[0].name = "left behind"
    saver = autosave.Autosaver()
    saver.write(document, source=tmp_path / "work.guiqula")
    data = json.loads(saver.path.read_text())
    data["pid"] = dead_pid()
    saver.path.write_text(json.dumps(data))
    window.offer_recovery()
    bar = window.recovery_bar
    assert bar.isVisible() and "left behind" in bar.label.text() and "work.guiqula" in bar.label.text()
    bar.button("recoverButton").click()
    assert not bar.isVisible()
    assert window.session.document.systems[0].name == "left behind"
    assert window.windowTitle() == "guiqula — work.guiqula *"
    window.offer_recovery()
    assert not bar.isVisible()                    # taken over by this session: nothing left


def test_autosave_label(window, qtbot):
    fresh(qtbot, window)
    saver = window.session.autosaver
    window.session.do("rename", entry="s1", name="autosaved")
    assert saver.pending
    qtbot.waitUntil(lambda: not saver.pending, timeout=10_000)      # the poll timer wrote it
    saved = json.loads(saver.path.read_text())
    assert saved["document"]["systems"][0]["name"] == "autosaved" and saved["modified"]
    assert window.autosave_label.text().startswith("autosaved")
    assert window.windowTitle().endswith(" *")


def test_close_asks_about_unsaved_changes(qtbot, monkeypatch, no_jobs):
    window = build_main_window(ask_before_close=True)
    qtbot.addWidget(window)
    session = Session("honeycomb_zeeman_rashba", jobs=no_jobs)
    window.attach(session)
    window.show()
    answers = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answers.pop(0))
    assert window.close()                          # nothing changed: no question
    window.show()
    session.do("rename", entry="s1", name="changed")
    answers.append(QMessageBox.StandardButton.Cancel)
    assert not window.close() and window.isVisible()
    answers.append(QMessageBox.StandardButton.Discard)
    assert window.close()
