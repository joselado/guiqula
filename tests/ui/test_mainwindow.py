"""The window without workers: its parts exist under stable objectNames
(tools/drive.py and the tests find widgets by name)."""
from PySide6.QtWidgets import (QComboBox, QDockWidget, QFrame, QLabel, QPushButton, QTabBar,
                               QTabWidget, QToolBar, QTreeWidget, QWidget)

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
                       (QWidget, "structureCanvas"), (QWidget, "plotView"),
                       (QTabBar, "workspaceTabs"), (QComboBox, "calculationBox"),
                       (QPushButton, "runButton"), (QPushButton, "cancelButton"),
                       (QPushButton, "addRegionButton"), (QFrame, "errorBar"),
                       (QFrame, "recoveryBar"), (QLabel, "statusLabel"), (QLabel, "autosaveLabel"),
                       (QDockWidget, "outlinerDock"), (QDockWidget, "propertiesDock"),
                       (QDockWidget, "jobsDock"), (QDockWidget, "logDock"),
                       (QToolBar, "geometryToolbar"), (QToolBar, "hamiltonianToolbar"),
                       (QToolBar, "calculateToolbar"), (QToolBar, "runToolbar")]:
        assert window.findChild(kind, name) is not None, name
    assert [window.viewport.tabText(i) for i in range(2)] == ["Structure", "Result"]
    assert window.status_label.toolTip().startswith("pyqula: ")
    assert shot(window, "main_window").stat().st_size > 1000


def test_workspaces_switch_palettes(qtbot):
    window = build_main_window()
    qtbot.addWidget(window)
    window.show()
    for name, tab in (("hamiltonian", 0), ("calculate", 1), ("geometry", 0)):
        window.set_workspace(name)
        assert window.workspace_tabs.currentIndex() == ["geometry", "hamiltonian",
                                                        "calculate"].index(name)
        assert [k for k, bar in window.palettes.items() if bar.isVisible()] == [name]
        assert window.viewport.currentIndex() == tab
    window.workspace_tabs.setCurrentIndex(2)           # the tab bar drives it too
    assert window.workspace == "calculate"
