"""The window without workers: its parts exist under stable objectNames
(tools/drive.py and the tests find widgets by name)."""
from PySide6.QtWidgets import (QComboBox, QDockWidget, QFrame, QLabel, QMenu, QPushButton,
                               QTabBar, QTabWidget, QToolBar, QToolButton, QTreeWidget, QWidget)

from guiqula.ui.app import build_main_window


def test_main_window_builds_without_workers(qtbot, shot):
    window = build_main_window()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    assert window.objectName() == "MainWindow" and window.session is None
    assert not window.ask_before_close
    for kind, name in [(QTreeWidget, "outliner"), (QTabWidget, "viewport"),
                       (QWidget, "properties"), (QWidget, "structureView"),
                       (QWidget, "structureCanvas"), (QComboBox, "canvasView"),
                       (QTabBar, "workspaceTabs"),
                       (QToolButton, "runButton"), (QToolButton, "cancelButton"),
                       (QToolButton, "autoRerunButton"), (QMenu, "runMenu"),
                       (QToolButton, "newSystemButton"), (QToolButton, "addButton"),
                       (QMenu, "paletteMenu_term"), (QMenu, "regionsMenu"),
                       (QPushButton, "regionFromSelectionButton"), (QFrame, "errorBar"),
                       (QFrame, "recoveryBar"), (QFrame, "costBar"), (QLabel, "statusLabel"),
                       (QLabel, "autosaveLabel"),
                       (QDockWidget, "outlinerDock"), (QDockWidget, "propertiesDock"),
                       (QDockWidget, "jobsDock"), (QDockWidget, "logDock"),
                       (QToolBar, "workspaceToolbar"), (QToolBar, "geometryToolbar"),
                       (QToolBar, "runToolbar")]:
        assert window.findChild(kind, name) is not None, name
    # one place to choose a calculation, the outliner or its tab: no Calculation combo, and
    # nothing to run or cancel without a document (PLAN.md phase 8, package P4)
    assert window.findChild(QComboBox, "calculationBox") is None
    assert window.selected_calculation() is None
    assert window.run_button.text() == "Run" and not window.run_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    # one tab per result, opened when a calculation is shown; Structure and k-space stay
    assert [window.viewport.tabText(i) for i in range(window.viewport.count())] == \
        ["Structure", "k-space"]
    assert window.status_label.toolTip().startswith("pyqula: ")
    assert shot(window, "main_window").stat().st_size > 1000


def test_workspaces_switch_palettes(qtbot):
    window = build_main_window()
    qtbot.addWidget(window)
    window.show()
    for name, view, family in (("hamiltonian", "hamiltonian", "term"),
                               ("calculate", "hamiltonian", "calculation"),
                               ("geometry", "structure", "geometry_op")):
        window.set_workspace(name)
        assert window.workspace_tabs.currentIndex() == ["geometry", "hamiltonian",
                                                        "calculate"].index(name)
        assert window.add_button.menu() is window.palette_menus[family]     # what Add lists
        assert window.findChild(QToolBar, "geometryToolbar").isVisible()    # the selection
        assert window.current_tab() == "structure"      # no calculation to show
        assert window.canvas_view == view and window.structure.view_box.currentData() == view
    window.workspace_tabs.setCurrentIndex(2)           # the tab bar drives it too
    assert window.workspace == "calculate"
