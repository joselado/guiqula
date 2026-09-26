from PySide6.QtWidgets import QComboBox, QPushButton, QTabWidget, QTreeWidget

from guiqula.ui.app import build_main_window


def test_main_window_builds_without_workers(qtbot, shot):
    window = build_main_window()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    assert window.objectName() == "MainWindow" and window.session is None
    for kind, name in [(QTreeWidget, "documentTree"), (QTabWidget, "viewport"),
                       (QComboBox, "calculationBox"), (QPushButton, "runButton"),
                       (QPushButton, "cancelButton")]:
        assert window.findChild(kind, name) is not None, name
    assert window.status_label.text().startswith("pyqula: ")
    assert shot(window, "main_window").stat().st_size > 1000
