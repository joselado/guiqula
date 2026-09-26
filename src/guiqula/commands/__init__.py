"""Every mutation of the Document is a named Command, applied through one
dispatcher with undo, a journal and change notifications (PLAN.md 3.5).
The single API of the UI, the tests, the console, tools/drive.py and the
future Claude add-on.

No Qt and no pyqula imports (tests/test_layering.py). Phase 1.
"""
