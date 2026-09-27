"""QApplication setup and the entry point of the graphical program."""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from guiqula import env
from guiqula.ui import errors, theme
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
    if not app.property("guiqula_theme"):    # also an application someone else made (pytest-qt)
        theme.apply(app)                     # plain Qt look (decision 13.6)
        app.setProperty("guiqula_theme", True)
    return app


def build_main_window(**options):
    """Create (but do not show) the main window, without workers. Built
    this way (tests, tools/drive.py) it never asks before closing."""
    create_application()
    return MainWindow(**options)


def run(argv=None, document=None, remote=False):
    """Show the main window, start the workers once it is visible, and run
    the event loop; return the exit code. remote: turn remote control on
    for this run (PLAN.md 3.7), whatever the settings say."""
    app = create_application(argv)
    window = build_main_window(ask_before_close=True, use_settings=True)
    if remote:
        window.set_remote(True, remember=False)
    errors.install(window)
    window.show()
    QTimer.singleShot(0, lambda: window.start_session(document))
    return app.exec()
