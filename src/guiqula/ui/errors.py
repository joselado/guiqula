"""Unexpected errors in the UI process (PLAN.md 3.5 (c), 13.14): an
exception that reaches the top of a Qt callback is logged, written to a
crash report and shown in the window's error bar; the program never
aborts. PySide6 passes such exceptions to sys.excepthook, which install()
replaces."""
import sys
import traceback


def install(window):
    """Route unhandled exceptions to window.report_exception; returns the
    previous hook."""
    previous = sys.excepthook

    def hook(kind, value, tb):
        if issubclass(kind, KeyboardInterrupt):
            return previous(kind, value, tb)
        try:
            window.report_exception(kind, value, tb)
        except Exception:                      # the reporting itself failed: say both
            sys.__excepthook__(kind, value, tb)
            traceback.print_exc()

    sys.excepthook = hook
    return previous
