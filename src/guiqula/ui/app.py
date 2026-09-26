"""QApplication setup and the entry point of the graphical program."""
import sys

from PySide6.QtWidgets import QApplication

from guiqula import env
from guiqula.ui.mainwindow import MainWindow


def create_application(argv=None):
    """Return the QApplication, creating it on first use.

    The Qt environment (platform plugin path) is fixed first; this is a
    no-op when the caller already did it.
    """
    app = QApplication.instance()
    if app is None:
        env.configure_qt()
        app = QApplication(list(argv) if argv is not None else sys.argv[:1])
        app.setApplicationName("guiqula")
        app.setStyle("Fusion")   # plain Qt look (decision 13.6)
    return app


def build_main_window():
    """Create (but do not show) the main window."""
    create_application()
    return MainWindow()


def run(argv=None):
    """Show the main window and run the event loop; return the exit code."""
    app = create_application(argv)
    window = build_main_window()
    window.show()
    return app.exec()
