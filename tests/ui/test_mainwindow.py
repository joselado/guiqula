from guiqula.ui.app import build_main_window


def test_main_window_builds(qtbot, shot):
    window = build_main_window()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    assert window.objectName() == "MainWindow"
    assert window.windowTitle() == "guiqula"
    assert window.findChild(type(window.centralWidget()), "placeholder") is not None
    status = window.statusBar().currentMessage()     # where pyqula comes from
    assert status.startswith("pyqula: ") and "not found" not in status
    path = shot(window, "main_window")
    assert path.stat().st_size > 1000
