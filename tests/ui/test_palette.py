"""Adding things where they appear, and workspaces that follow (PLAN.md
phase 8, package P2): one searchable Add menu per family (ui/palette.py),
opened from the "+" of an outliner section, from the first row's Add and
New system, or with Ctrl+F; selecting an entry shows its workspace; the run
controls of the first row."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolBar, QToolButton, QWidget

from guiqula.ui import palette
from guiqula.ui.app import build_main_window
from guiqula.ui.mainwindow import WORKSPACE_FAMILIES, WORKSPACES


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


@pytest.fixture(autouse=True)
def no_popup_left(window):
    """A menu left open would keep the keyboard from the next test."""
    yield
    for _ in range(5):
        popup = QApplication.activePopupWidget()
        if popup is None:
            break
        popup.hide()
    assert QApplication.activePopupWidget() is None


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)


def fresh(qtbot, window):
    window.session.act("load", path="honeycomb_zeeman_rashba")
    window.select("")
    window.set_workspace("geometry")
    settle(qtbot, window)


def terms(window, system="s1"):
    return window.session.document.system(system).hamiltonian.terms


def test_the_menu_lists_by_group_and_filters(window, qtbot):
    fresh(qtbot, window)
    menu = window.palette_menu("term")
    assert menu.objectName() == "paletteMenu_term" and menu.actions()[0] is menu.search_action
    assert menu.search.objectName() == "paletteSearch" and menu.search.toolTip()
    offered = menu.offered()
    sections = [a.text() for a in menu.actions() if a.isSeparator() and a.text()]
    assert sections == sorted({spec.group for spec in offered}) + ["Interactions"]
    names = [a.objectName() for a in menu.actions() if a.objectName().startswith("addTerm_")]
    assert names == [f"addTerm_{spec.kind}" for spec in offered]        # by group, then label
    assert all(action.toolTip().startswith("<b>") for action in menu.entries.values())
    listed = menu.filter("kane")
    assert listed[0] == "addTerm_kane_mele" and menu.best is menu.entries["kane_mele"]
    assert menu.best.font().bold()
    expected = {spec.kind for spec in palette.search_entries("term", "kane")}
    assert {kind for kind, a in menu.entries.items() if a.isVisible()} == expected
    for section, actions in menu._sections:                  # a group with no match hides
        assert section.isVisible() == any(a.isVisible() for a in actions), section.text()
    assert not all(section.isVisible() for section, _ in menu._sections)
    assert menu.filter("mean field") == ["addMeanfield"]          # its own items take part
    assert menu.filter("hubbard") == ["addMeanfield"]             # by their tooltip too
    assert menu.best is menu.findChild(QAction, "addMeanfield")
    assert menu.filter("") == names + ["addMeanfield"]
    assert all(a.isVisible() and not a.font().bold() for a in menu.entries.values())
    # a classical system offers its own terms, without a mean field
    ising = window.new_classical_system("ising")
    menu = window.palette_menu("term")
    assert set(menu.entries) == {"ising_interaction", "ising_field", "python"}
    assert menu.filter("") == [f"addTerm_{k}" for k in menu.entries]
    assert window.workspace_tabs.tabText(1) == "Model"
    lattices = window.palette_menu("lattice")              # the lattices of quantum systems
    assert "newSystem_honeycomb_lattice" in lattices.filter("")
    assert lattices.filter("")[-3:] == ["newClassical_classical_spin", "newClassical_lattice_gas",
                                         "newClassical_ising"]
    assert "newClassical_ising" in lattices.filter("ising")
    window.session.do("remove", entry=ising)


def test_enter_adds_the_best_match_once(window, qtbot):
    fresh(qtbot, window)
    window.set_workspace("hamiltonian")
    count = len(terms(window))
    opened = window.open_add_menu(search="kane")
    menu = window.palette_menus["term"]
    assert (opened["menu"], opened["system"], opened["best"]) == \
        ("paletteMenu_term", "s1", "addTerm_kane_mele")
    assert opened["entries"][0] == "addTerm_kane_mele" and menu.isVisible()
    QTest.keyClick(menu.search, Qt.Key.Key_Return)
    assert len(terms(window)) == count + 1              # one Enter, one term
    assert terms(window)[-1].kind == "kane_mele" and window.selected == terms(window)[-1].id
    assert not menu.isVisible() and menu.search.text() == ""
    window.open_add_menu(search="superconduct")          # a word of a label
    QTest.keyClick(menu.search, Qt.Key.Key_Enter)
    assert terms(window)[-1].kind == "pairing" and len(terms(window)) == count + 2
    window.open_add_menu(search="no such physics")      # nothing matches: nothing added
    QTest.keyClick(menu.search, Qt.Key.Key_Return)
    assert len(terms(window)) == count + 2 and menu.isVisible()
    assert "no term matches 'no such physics'" in window.log.toPlainText()
    menu.hide()
    # a letter typed while an entry has the keyboard goes to the search line: QMenu would
    # trigger the entry it starts
    window.open_add_menu()
    menu.setActiveAction(menu.entries["haldane"])
    QTest.keyClick(menu, Qt.Key.Key_H)
    assert len(terms(window)) == count + 2 and menu.search.text() == "h"
    assert menu.best is not None and menu.best.text().lower().startswith("h")
    menu.hide()
    # the search line is the active item, so one Down reaches the first entry shown, which
    # Enter adds (not the best match, drawn in bold); a letter typed then goes to the search
    window.open_add_menu(search="spin")
    assert menu.activeAction() is menu.search_action
    shown = [a for a in menu.entries.values() if a.isVisible()]
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Down)
    assert menu.activeAction() is shown[0] and shown[0] is not menu.best
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Return)
    assert len(terms(window)) == count + 3 and terms(window)[-1].kind == next(
        kind for kind, a in menu.entries.items() if a is shown[0])
    assert not menu.isVisible()
    window.open_add_menu()
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Down)
    assert menu.activeAction() is next(a for a in menu.entries.values() if a.isVisible())
    QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Z)
    assert menu.search.text() == "z" and menu.search.hasFocus()
    assert len(terms(window)) == count + 3
    menu.hide()
    # the window action does the same, for drivers
    found = window.session.act("add_menu", section="s1/hamiltonian", search="haldane")
    assert found["best"] == "addTerm_haldane" and window.palette_menus["term"].isVisible()
    window.palette_menus["term"].hide()
    with pytest.raises(ValueError, match="unknown section"):
        window.session.act("add_menu", section="s1/nope")
    with pytest.raises(ValueError, match="terms are under s1/hamiltonian"):
        window.open_add_menu("s1/model")


def test_the_plus_of_a_section_adds_to_its_own_system(window, qtbot):
    fresh(qtbot, window)
    session = window.session
    second = window.new_system("square_lattice")
    settle(qtbot, window)
    assert window.current_system() == second
    outliner = window.outliner
    for path in ("s1/geometry", "s1/regions", "s1/hamiltonian", f"{second}/geometry",
                 f"{second}/regions", f"{second}/hamiltonian", "calculations"):
        button = outliner.add_button(path)
        assert isinstance(button, QToolButton) and button.isVisible(), path
        assert button.objectName() == "outlinerAdd_" + path.replace("/", "_")
        assert button.toolTip() and button.isEnabled(), path
    assert outliner.add_button("s1/model") is None
    # a piecewise Field of a system without regions says where they are made: the "+"
    window.select("t2")
    hint = window.properties.form.editors["c"].no_regions.text()
    assert "+ of its Regions row" in hint and "toolbar" not in hint
    # the button leaves the rest of the status cell to its row, whose height it keeps
    item = outliner.item("s1/regions")
    cell = outliner.visualRect(outliner.indexFromItem(item, 1))
    button = outliner.add_button("s1/regions")
    assert outliner.viewport().childAt(QPoint(cell.left() + 4, cell.center().y())) is None
    assert outliner.viewport().childAt(button.mapTo(outliner.viewport(),
                                                    button.rect().center())) is button
    assert button.height() <= cell.height() == outliner.visualItemRect(outliner.item("t1")) \
        .height()
    # the "+" of s1's Hamiltonian adds to s1, though s2 is the current system
    outliner.add_button("s1/hamiltonian").click()                # a popup: returns at once
    menu = window.palette_menus["term"]
    assert menu.isVisible() and menu.system == "s1"
    menu.entries["haldane"].trigger()
    menu.hide()
    assert session.document.find(window.selected)[1].id == "s1"
    assert terms(window)[-1].kind == "haldane" and window.workspace == "hamiltonian"
    outliner.add_button(f"{second}/geometry").click()
    menu = window.palette_menus["geometry_op"]
    assert menu.system == second
    menu.entries["island"].trigger()
    menu.hide()
    assert session.document.find(window.selected)[1].id == second
    assert window.workspace == "geometry"
    # Regions: by expression, and from a selection of that system's sites only
    window.select("s1")
    settle(qtbot, window)
    outliner.add_button("s1/regions").click()
    assert window.regions_menu.isVisible() and window.regions_system == "s1"
    assert not window.region_selection_action.isEnabled()
    window.findChild(QAction, "addRegion_expression").trigger()
    window.regions_menu.hide()
    region = window.selected
    assert session.document.find(region)[1].id == "s1" and window.workspace == "geometry"
    session.act("select_sites", sublattice=1)
    opened = window.open_regions_menu("s1")
    assert opened["entries"] == ["addRegion_expression", "addRegion_selection"]
    window.region_selection_action.trigger()
    window.regions_menu.hide()
    assert session.document.find(window.selected)[-1].select["kind"] == "positions"
    assert window.open_regions_menu(second)["entries"] == ["addRegion_expression"]
    window.regions_menu.hide()
    # the Hamiltonian menu ends with the mean field: turned on, its row selected
    outliner.add_button("s1/hamiltonian").click()
    window.palette_menus["term"].findChild(QAction, "addMeanfield").trigger()
    window.palette_menus["term"].hide()
    assert window.selected == "s1/meanfield" and window.workspace == "hamiltonian"
    assert session.document.system("s1").hamiltonian.meanfield.enabled
    # the "+" of Calculations adds on the current system
    window.select(second)
    outliner.add_button("calculations").click()
    window.palette_menus["calculation"].entries["dos"].trigger()
    window.palette_menus["calculation"].hide()
    assert session.document.find(window.selected)[-1].system == second
    assert window.workspace == "calculate" and window.current_tab() == window.selected


def test_selecting_an_entry_shows_its_workspace(window, qtbot):
    fresh(qtbot, window)
    for entry, workspace in (("t1", "hamiltonian"), ("op1", "geometry"), ("c1", "calculate"),
                             ("s1/meanfield", "hamiltonian"), ("s1/base", "geometry"),
                             ("calculations", "calculate"), ("s1/hamiltonian", "hamiltonian"),
                             ("s1", "geometry"), ("t2", "hamiltonian")):
        window.session.act("select", entry=entry)
        assert window.workspace == workspace, entry
        assert window.workspace_tabs.currentIndex() == WORKSPACES.index(workspace)
        assert window.add_button.menu() is window.palette_menus[WORKSPACE_FAMILIES[workspace]]
    window.select("")
    assert window.workspace == "hamiltonian"                  # nothing selected: it stays
    assert window.canvas_view == "hamiltonian"
    # an add selects what it adds, so it switches too
    window.palette_menu("calculation").entries["dos"].trigger()
    assert window.workspace == "calculate" and window.current_tab() == window.selected
    # a Field previewed stays while the workspace does not change
    window.select("t1")
    window.preview_field("t1", "m")
    window.select("t2")
    assert window.canvas_view == "field" and window.workspace == "hamiltonian"
    window.select("op1")
    assert window.canvas_view == "structure"
    # a saved workspace wins over the one of the saved selection
    window.apply_view_state({"selected": "t2", "workspace": "calculate",
                             "canvas_view": "structure"})
    assert window.selected == "t2" and window.workspace == "calculate"
    assert window.canvas_view == "structure"
    window.set_workspace("geometry")


def test_ctrl_f_opens_the_add_menu_of_the_workspace(window, qtbot):
    fresh(qtbot, window)
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow, timeout=5000)
    for workspace, family in (("geometry", "geometry_op"), ("hamiltonian", "term"),
                              ("calculate", "calculation")):
        window.set_workspace(workspace)
        QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        menu = window.palette_menus[family]
        qtbot.waitUntil(menu.isVisible, timeout=5000)
        assert QApplication.activePopupWidget() is menu and menu.system == "s1"
        menu.hide()
        assert window.focus_search() == family
        menu.hide()
    window.set_workspace("geometry")
    # with no system, Add waits and Ctrl+F opens New system
    window.session.act("new")
    assert not window.add_button.isEnabled()
    assert not window.outliner.add_button("calculations").isEnabled()
    assert window.focus_search() == "lattice"
    window.palette_menus["lattice"].hide()


def test_the_first_row(window, qtbot):
    fresh(qtbot, window)
    bars = [bar.objectName() for bar in window.findChildren(QToolBar) if bar.isVisible()
            and bar.parent() is window]
    assert bars == ["workspaceToolbar", "runToolbar"]       # the selection row went (P3)
    first = window.findChild(QToolBar, "workspaceToolbar")
    assert first.findChild(QToolButton, "newSystemButton") is window.new_system_button
    assert first.findChild(QToolButton, "addButton") is window.add_button
    for name in ("opSearch", "termSearch", "calculationSearch", "addOpButton",
                 "addTermButton", "addCalculationButton", "addRegionButton", "meanfieldButton",
                 "newClassicalButton", "hamiltonianToolbar", "calculateToolbar",
                 "geometryToolbar"):
        assert window.findChild(QWidget, name) is None, name
    selection = window.findChild(QWidget, "structureBar")       # on the canvas (P3)
    assert [w.objectName() for w in selection.findChildren(QToolButton)
            if w.objectName().startswith(("tool_", "select"))] == \
        ["tool_pick", "tool_box", "tool_lasso", "selectSitesButton"]
    for workspace in WORKSPACES:                                # in every workspace
        window.set_workspace(workspace)
        assert selection.isVisibleTo(window.structure)
    window.set_workspace("geometry")
    QApplication.processEvents()
    for bar in (b for b in window.findChildren(QToolBar) if b.parent() is window):
        chevron = bar.findChild(QToolButton, "qt_toolbar_ext_button")
        assert chevron is None or not chevron.isVisible(), bar.objectName()
    # New system and Add open their menus with a click that returns at once
    window.new_system_button.click()
    assert window.palette_menus["lattice"].isVisible()
    window.palette_menus["lattice"].hide()
    window.add_button.click()
    assert window.palette_menus["geometry_op"].isVisible()
    window.palette_menus["geometry_op"].hide()
    # Run's menu: the other calculations, then every stale result
    window.select("c1")
    assert window._fill_run_menu() == ["runCalc_c2", "runStaleAction"]
    assert window.run_menu.actions()[0].text() == "Run c2 · dos"
    assert not window.run_stale_action.isEnabled()              # nothing computed yet
    assert window.session.act("run_stale") == []
    assert window.run_button.toolTip().endswith("(F5)")
    # Follow mirrors Run > Re-run cheap results automatically
    window.auto_rerun_button.click()
    assert window.auto_rerun and window.auto_rerun_action.isChecked()
    window.auto_rerun_action.trigger()
    assert not window.auto_rerun and not window.auto_rerun_button.isChecked()
    window.set_workspace("geometry")
