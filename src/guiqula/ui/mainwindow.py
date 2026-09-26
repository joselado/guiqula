"""The main window. A phase-0 placeholder: phase 1 adds the job panel and a
plot tab (decision 14.2), phase 2 the outliner, viewport and properties."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow

import guiqula
from guiqula import vendoring


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setWindowTitle("guiqula")
        self.resize(1200, 800)
        placeholder = QLabel(
            f"guiqula {guiqula.__version__}\n\n"
            "Phase 0 skeleton. The job panel and the first plot arrive in "
            "phase 1, the workbench (outliner, viewport, properties) in phase 2.")
        placeholder.setObjectName("placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        self.setCentralWidget(placeholder)
        self.statusBar().setObjectName("statusBar")
        self.statusBar().showMessage(vendoring.describe())
