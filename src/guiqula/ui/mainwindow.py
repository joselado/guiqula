"""The main window, phase 1 (decision 14.2): a thin client of a Session
with a read-only document tree, one plot tab, a job panel with progress,
cancel and worker state, and a log. Phase 2 replaces the tree with the
outliner, viewport and properties panel of PLAN.md section 4.

The window does not start workers by itself: start_session() creates the
Session (app.run calls it right after the window is shown, so the window
appears before the workers spawn), or attach() takes an existing one.
"""
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QComboBox, QDockWidget, QFileDialog, QLabel, QMainWindow,
                               QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QToolBar)

import guiqula
from guiqula import vendoring
from guiqula.io import project
from guiqula.ui.doctree import DocumentTree
from guiqula.ui.jobpanel import JobPanel
from guiqula.ui.plots import PlotView

POLL_MS = 30
BUILD_DELAY_MS = 150


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setWindowTitle("guiqula")
        self.resize(1200, 800)
        self.session = None
        self._owns_session = False
        self._unsubscribe = None

        self.tree = DocumentTree()
        self.plot = PlotView()
        self.viewport = QTabWidget()
        self.viewport.setObjectName("viewport")
        self.viewport.addTab(self.plot, "Plot")
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.addWidget(self.tree)
        splitter.addWidget(self.viewport)
        splitter.setSizes([360, 840])
        self.setCentralWidget(splitter)

        self.jobs = JobPanel()
        self.jobs.cancel_requested.connect(self.cancel_job)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        for title, widget, name in (("Jobs", self.jobs, "jobsDock"), ("Log", self.log, "logDock")):
            dock = QDockWidget(title, self)
            dock.setObjectName(name)
            dock.setWidget(widget)
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

        self._build_toolbar()
        self._build_menus()
        self.statusBar().setObjectName("statusBar")
        self.status_label = QLabel(vendoring.describe())
        self.status_label.setObjectName("statusLabel")
        self.statusBar().addWidget(self.status_label, 1)

        self.timer = QTimer(self)
        self.timer.setObjectName("pollTimer")
        self.timer.timeout.connect(self._poll)
        self.build_timer = QTimer(self)
        self.build_timer.setSingleShot(True)
        self.build_timer.timeout.connect(self._request_builds)
        self._update_actions()

    # ---- construction helpers
    def _build_toolbar(self):
        bar = QToolBar("Run")
        bar.setObjectName("runToolbar")
        self.addToolBar(bar)
        bar.addWidget(QLabel(" Calculation "))
        self.calc_box = QComboBox()
        self.calc_box.setObjectName("calculationBox")
        self.calc_box.setMinimumWidth(260)
        self.calc_box.currentIndexChanged.connect(self._show_selected_result)
        bar.addWidget(self.calc_box)
        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("runButton")
        self.run_button.clicked.connect(self.run_selected)
        bar.addWidget(self.run_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self.cancel_selected)
        bar.addWidget(self.cancel_button)

    def _action(self, menu, text, slot, shortcut=None, name=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if name:
            action.setObjectName(name)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        self._action(file_menu, "&New", lambda: self._act("new"), QKeySequence.StandardKey.New)
        self._action(file_menu, "&Open...", self.open_dialog, QKeySequence.StandardKey.Open)
        presets = file_menu.addMenu("Open &preset")
        for name in project.presets():
            self._action(presets, name, lambda checked=False, n=name: self.open_document(n))
        self._action(file_menu, "&Save", self.save, QKeySequence.StandardKey.Save)
        self._action(file_menu, "Save &as...", self.save_as, QKeySequence.StandardKey.SaveAs)
        self._action(file_menu, "&Export pyqula script...", self.export_script)
        file_menu.addSeparator()
        self._action(file_menu, "&Quit", self.close, QKeySequence.StandardKey.Quit)
        edit = self.menuBar().addMenu("&Edit")
        self.undo_action = self._action(edit, "&Undo", self.undo, QKeySequence.StandardKey.Undo,
                                        "undoAction")
        self.redo_action = self._action(edit, "&Redo", self.redo, "Ctrl+Shift+Z", "redoAction")
        run = self.menuBar().addMenu("&Run")
        self._action(run, "&Run calculation", self.run_selected, "F5", "runAction")
        self._action(run, "&Cancel", self.cancel_selected, "Esc", "cancelAction")
        help_menu = self.menuBar().addMenu("&Help")
        self._action(help_menu, "&About", lambda: self.message(
            f"guiqula {guiqula.__version__}, {vendoring.describe()}"))

    # ---- session
    def start_session(self, document=None, **options):
        """Create and attach a Session (starts the worker processes)."""
        from guiqula.session import Session
        try:
            session = Session(document, **options)
        except Exception as error:
            self.message(f"could not start: {error}", error=True)
            raise
        self.attach(session, owned=True)
        return session

    def attach(self, session, owned=False):
        self.session = session
        self._owns_session = owned
        self._unsubscribe = session.subscribe(self._on_session_event)
        self.timer.start(POLL_MS)
        self._document_changed()

    def closeEvent(self, event):
        self.timer.stop()
        self.build_timer.stop()
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        if self.session is not None and self._owns_session:
            self.session.close()
        super().closeEvent(event)

    def _poll(self):
        try:
            self.session.poll(0)
        except Exception:
            self.message("error while polling the workers:\n" + traceback.format_exc(), error=True)

    def _on_session_event(self, kind, payload):
        if kind == "document":
            self._document_changed()
        elif kind == "job":
            self._job_changed(payload)
        elif kind == "worker":
            self.jobs.update_workers(self.session.jobs.status())
            if payload["starts"] > 1 and payload["ready"] is False:
                self.message(f"{payload['role']} worker restarted (pid {payload['pid']})")

    def _document_changed(self):
        self._refresh_calculations()
        self.tree.refresh(self.session, self.builds)
        self._update_actions()
        self._show_selected_result()
        self.build_timer.start(BUILD_DELAY_MS)
        path = self.session.path
        self.setWindowTitle(f"guiqula — {path.name}" if path else "guiqula")

    @property
    def builds(self):
        """system id -> latest build summary (kept by the session)."""
        return self.session.builds if self.session is not None else {}

    def _request_builds(self):
        """Ask the interactive worker to build every system (modes, sites,
        entries pyqula rejects), without blocking the batch workers."""
        if self.session is not None:
            self.session.build_all()

    def _job_changed(self, job):
        if job.kind == "build":
            system = job.payload["system"]
            if job.status == "done" and self.builds.get(system) is job.value:
                self.tree.refresh(self.session, self.builds)
                self.status_label.setText(
                    f"{system}: {job.value['mode']} · {job.value['sites']} sites · "
                    f"dimension {job.value['dimension']} · {vendoring.describe()}")
            elif job.status == "failed":
                self.message(f"{system} cannot be built: {job.error}", error=True)
            return
        self.jobs.update_job(job)
        for line in job.log:
            self.log.appendPlainText(f"[{job.id}] {line}")
        job.log.clear()
        if job.done:
            if job.status == "failed":
                self.message(f"{job.id} {job.label} failed: {job.error}", error=True)
            else:
                self.message(f"{job.id} {job.label} {job.status}")
            self.tree.refresh(self.session, self.builds)
            if job.status == "done" and job.label == self.selected_calculation():
                self._show_selected_result()
        self.jobs.update_workers(self.session.jobs.status())

    # ---- calculations and results
    def _refresh_calculations(self):
        current = self.selected_calculation()
        self.calc_box.blockSignals(True)
        self.calc_box.clear()
        for calc in self.session.document.calculations:
            self.calc_box.addItem(f"{calc.id} · {calc.kind} on {calc.system}", calc.id)
        index = self.calc_box.findData(current)
        self.calc_box.setCurrentIndex(index if index >= 0 else 0)
        self.calc_box.blockSignals(False)

    def selected_calculation(self):
        return self.calc_box.currentData()

    def select_calculation(self, calc_id):
        index = self.calc_box.findData(calc_id)
        if index < 0:
            raise KeyError(calc_id)
        self.calc_box.setCurrentIndex(index)

    def _show_selected_result(self):
        calc = self.selected_calculation()
        if self.session is None or calc is None:
            self.plot.clear("No calculation in this document.")
            return
        result = self.session.result(calc)
        if result is None:
            self.plot.clear(f"{calc}: no result yet; press Run (F5).")
            return
        stale = self.session.is_stale(calc)
        title = f"{calc} · {result.kind} · {result.mode}" + (" · STALE" if stale else "")
        notes = [f"{result.meta.get('seconds', 0):.2f} s"]
        if result.skipped:
            notes.append("skipped: " + ", ".join(f"{r['id']} ({r['message']})" for r in result.skipped))
        if stale:
            notes.append("the document changed since this result was computed; run again")
        self.plot.show_result(result, title, " · ".join(notes))

    def run_selected(self):
        calc = self.selected_calculation()
        if calc is None:
            self.message("no calculation to run", error=True)
            return
        self._act("run_calculation", calculation=calc)

    def cancel_selected(self):
        calc = self.selected_calculation()
        job = self.session.calc_jobs.get(calc) if calc else None
        if job is not None and not job.done:
            self.cancel_job(job.id)

    def cancel_job(self, job_id):
        self._act("cancel", target=job_id)

    # ---- files and undo
    def open_document(self, path_or_name):
        self._act("load", path=str(path_or_name))

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "guiqula (*.guiqula *.json)")
        if path:
            self.open_document(path)

    def save(self):
        if self.session.path is None:
            self.save_as()
        else:
            self._act("save", path=str(self.session.path))

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save", "", "guiqula (*.guiqula);;JSON (*.json)")
        if path:
            self._act("save", path=path)

    def export_script(self):
        calc = self.selected_calculation()
        if calc is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export pyqula script", f"{calc}.py",
                                              "Python (*.py)")
        if path:
            self._act("export_script", calculation=calc, path=path)

    def undo(self):
        if self.session.dispatcher.can_undo():
            self.session.undo()

    def redo(self):
        if self.session.dispatcher.can_redo():
            self.session.redo()

    def _update_actions(self):
        has = self.session is not None
        self.undo_action.setEnabled(has and self.session.dispatcher.can_undo())
        self.redo_action.setEnabled(has and self.session.dispatcher.can_redo())
        self.run_button.setEnabled(has and self.calc_box.count() > 0)

    def _act(self, name, **args):
        """Run a dispatcher action, reporting errors in the log instead of
        raising (a UI error never takes the window down, PLAN.md 3.5)."""
        try:
            return self.session.act(name, **args)
        except Exception as error:
            self.message(f"{name}: {error}", error=True)
            return None

    def message(self, text, error=False):
        self.log.appendPlainText(("ERROR: " if error else "") + text)
        self.statusBar().showMessage(text.splitlines()[0], 8000)
