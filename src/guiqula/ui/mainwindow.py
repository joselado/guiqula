"""The main window (PLAN.md section 4): one document, three workspaces
(Geometry, Hamiltonian, Calculate) that change the palette toolbar and
the emphasis, not the data; the outliner on the left, the viewport (the
Structure tab and one closable tab per calculation's result, which can be
detached into floating docks) in the centre, the properties form and the
jobs on the right, the log at the bottom, and the status bar.

The structure canvas has three views: the sites and bonds (the Geometry
workspace), the Hamiltonian (13.8, the Hamiltonian workspace), and the
preview of the Field being edited (PLAN.md 3.8), which a Field editor
selects when the user looks at it. The cost guard (13.12) shows the rough
duration of the selected calculation in the status bar and asks, in a
non-modal bar, before running one that takes minutes; stale results of
cheap calculations can be re-run automatically (opt-in, Run menu).

The window is a client of a Session: every change goes through the
dispatcher. The selected item, the workspace, the canvas tool and the site
selection are window state, not Document mutations; they are registered on
the dispatcher as actions (select, workspace, tool, select_sites), so
tools/drive.py and the future remote API reach them without putting clicks
on the undo stack. region_from_selection and remove_selected are actions
that apply one mutation each (add_region; add_geometry_op, or set_param on
a trailing removal op, PLAN.md 3.1). The same state is saved with the
project as the Document's ui block (view_state, through the session) and
restored when a document is opened or recovered (apply_view_state).

The window does not start workers by itself: start_session() creates the
Session (app.run calls it right after the window is shown, so the window
appears before the workers spawn), or attach() takes an existing one.
Unexpected errors go to report_exception (ui/errors.py installs it as the
exception hook): logged, a crash report written, the error bar shown.
"""
import time
import traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QCompleter, QDockWidget, QFileDialog,
                               QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QPlainTextEdit, QPushButton, QTabBar, QTabWidget, QToolBar,
                               QToolButton, QVBoxLayout, QWidget)

import guiqula
from guiqula import vendoring
from guiqula.core import fields
from guiqula.core import regions as region_tools
from guiqula.io import crashreport, project
from guiqula.registry import base as registry
from guiqula.registry import cost, pipeline
from guiqula.registry.params import VectorFieldParam
from guiqula.ui.bars import MessageBar
from guiqula.ui.jobpanel import JobPanel
from guiqula.ui.outliner import Outliner, system_of
from guiqula.ui.plots import PlotView
from guiqula.ui.properties import PropertiesPanel
from guiqula.ui import structure as structure_tools
from guiqula.ui.structure import StructureView

POLL_MS = 30
BUILD_DELAY_MS = 150
PREVIEW_DELAY_MS = 120
WORKSPACES = ("geometry", "hamiltonian", "calculate")
# actions of the window itself: they change what is shown, not the Document
WINDOW_ACTIONS = ("select", "workspace", "tool", "select_sites", "canvas_view", "preview",
                  "auto_rerun")
STRUCTURE_TAB = 0
REGION_TOLERANCE = 0.05      # positions regions made from a canvas selection
AUTO_RERUN_SECONDS = 3.0     # stale results re-run automatically when cheaper than this
CANVAS_VIEW_OF = {"geometry": "structure", "hamiltonian": "hamiltonian"}


def _grouped(family):
    """Registry entries sorted by group, then label."""
    return sorted(registry.entries(family), key=lambda s: (s.group, s.label))


def search_entries(family, text):
    """Registry entries whose label, kind, group or doc contain the text
    (case-insensitive); an exact label (or "label (group)") first."""
    text = text.strip().lower()
    if not text:
        return []
    found = []
    for spec in _grouped(family):
        exact = text in (spec.label.lower(), f"{spec.label} ({spec.group})".lower(), spec.kind)
        words = " ".join((spec.label, spec.kind, spec.group, spec.doc)).lower()
        if exact or text in words:
            found.append((not exact, spec))
    return [spec for _, spec in sorted(found, key=lambda item: item[0])]


class MainWindow(QMainWindow):
    def __init__(self, parent=None, ask_before_close=False, autosave=True):
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setWindowTitle("guiqula")
        self.resize(1280, 820)
        self.session = None
        self.ask_before_close = ask_before_close   # the interactive program asks (ui/app.py)
        self.autosave = autosave
        self.selected = ""
        self.workspace = "geometry"
        self.last_crash_report = None
        self._owns_session = False
        self._unsubscribe = None
        self._last_crash_text = None
        self._pending_sites = None     # (system, positions) to select once it is built
        self.plots = {}                # calculation id -> PlotView (a tab or a floating dock)
        self.plot_docks = {}           # calculation id -> QDockWidget of a detached view
        self.canvas_view = "structure"
        self.field_preview = None      # (entry, parameter) the field view draws
        self.auto_rerun = False
        self._auto_keys = {}           # calculation id -> key it was last re-run for
        self._auto_jobs = set()        # ids of the jobs the auto re-run started
        self._searched = (None, 0.0)   # (text, time) of the last palette search

        self.outliner = Outliner()
        self.outliner.selected.connect(self.select)
        self.outliner.command.connect(self._outliner_command)
        self.properties = PropertiesPanel(self._do)
        self.properties.preview.connect(self._preview_requested)
        self.structure = StructureView()
        self.structure.selection_changed.connect(self._selection_changed)
        self.structure.view_chosen.connect(self.set_canvas_view)
        self.viewport = QTabWidget()
        self.viewport.setObjectName("viewport")
        self.viewport.setTabsClosable(True)
        self.viewport.addTab(self.structure, "Structure")
        for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
            self.viewport.tabBar().setTabButton(STRUCTURE_TAB, side, None)   # always there
        self.viewport.tabCloseRequested.connect(self._close_tab)
        self.error_bar = MessageBar("errorBar")
        self.recovery_bar = MessageBar("recoveryBar")
        self.cost_bar = MessageBar("costBar")
        central = QWidget()
        central.setObjectName("central")
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.recovery_bar)
        column.addWidget(self.error_bar)
        column.addWidget(self.cost_bar)
        column.addWidget(self.viewport, 1)
        self.setCentralWidget(central)

        self.jobs = JobPanel()
        self.jobs.cancel_requested.connect(self.cancel_job)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        outliner_dock = self._dock("Outliner", self.outliner, "outlinerDock",
                                   Qt.DockWidgetArea.LeftDockWidgetArea)
        properties_dock = self._dock("Properties", self.properties, "propertiesDock",
                                     Qt.DockWidgetArea.RightDockWidgetArea)
        jobs_dock = self._dock("Jobs", self.jobs, "jobsDock", Qt.DockWidgetArea.RightDockWidgetArea)
        self.splitDockWidget(properties_dock, jobs_dock, Qt.Orientation.Vertical)
        log_dock = self._dock("Log", self.log, "logDock", Qt.DockWidgetArea.BottomDockWidgetArea)
        self.resizeDocks([outliner_dock, properties_dock], [320, 340], Qt.Orientation.Horizontal)
        self.resizeDocks([properties_dock, jobs_dock], [480, 180], Qt.Orientation.Vertical)
        self.resizeDocks([log_dock], [130], Qt.Orientation.Vertical)
        self.docks = {d.objectName(): d for d in (outliner_dock, properties_dock, jobs_dock,
                                                  log_dock)}

        self._build_toolbars()
        self._build_menus()
        self.statusBar().setObjectName("statusBar")
        self.status_label = QLabel("no document")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setToolTip(vendoring.describe())
        self.autosave_label = QLabel("")
        self.autosave_label.setObjectName("autosaveLabel")
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.autosave_label)

        self.timer = QTimer(self)
        self.timer.setObjectName("pollTimer")
        self.timer.timeout.connect(self._poll)
        self.build_timer = QTimer(self)
        self.build_timer.setSingleShot(True)
        self.build_timer.timeout.connect(self._request_builds)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._refresh_structure)
        self.set_workspace("geometry")
        self._update_actions()

    # ---- construction helpers
    def _dock(self, title, widget, name, area):
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def _menu_button(self, bar, text, name, entries, handler, prefix):
        """A tool button whose menu lists registry entries by group."""
        button = QToolButton()
        button.setText(text)
        button.setObjectName(name)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        group = None
        for spec in entries:
            if spec.group != group:
                group = spec.group
                menu.addSection(group or "other")
            action = menu.addAction(spec.label)
            action.setObjectName(f"{prefix}_{spec.kind}")
            action.setToolTip(spec.doc)
            action.triggered.connect(lambda checked=False, k=spec.kind: handler(k))
        button.setMenu(menu)
        bar.addWidget(button)
        return button

    def _toolbar(self, title, name):
        bar = QToolBar(title)
        bar.setObjectName(name)
        bar.setMovable(False)
        self.addToolBar(bar)
        return bar

    def _build_toolbars(self):
        bar = self._toolbar("Workspace", "workspaceToolbar")
        self.workspace_tabs = QTabBar()
        self.workspace_tabs.setObjectName("workspaceTabs")
        for name in WORKSPACES:
            self.workspace_tabs.addTab(name.capitalize())
        self.workspace_tabs.currentChanged.connect(lambda i: self.set_workspace(WORKSPACES[i]))
        bar.addWidget(self.workspace_tabs)
        run = self._toolbar("Run", "runToolbar")
        run.addWidget(QLabel(" Calculation "))
        self.calc_box = QComboBox()
        self.calc_box.setObjectName("calculationBox")
        self.calc_box.setMinimumWidth(240)
        self.calc_box.currentIndexChanged.connect(self._calculation_chosen)
        run.addWidget(self.calc_box)
        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("runButton")
        self.run_button.clicked.connect(self.run_selected)
        run.addWidget(self.run_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self.cancel_selected)
        run.addWidget(self.cancel_button)
        self.addToolBarBreak()              # the palettes get a row of their own

        self.palettes = {}
        geometry = self._toolbar("Geometry", "geometryToolbar")
        self._menu_button(geometry, "New system", "newSystemButton", _grouped("lattice"),
                          self.new_system, "newSystem")
        self._menu_button(geometry, "Add op", "addOpButton", _grouped("geometry_op"),
                          self.add_op, "addOp")
        self._search_box(geometry, "geometry_op", self.add_op, "opSearch", "find an op")
        self.add_region_button = QPushButton("Add region")
        self.add_region_button.setObjectName("addRegionButton")
        self.add_region_button.setToolTip("a region of the current system, by expression")
        self.add_region_button.clicked.connect(self.add_region)
        geometry.addWidget(self.add_region_button)
        geometry.addSeparator()
        self.tool_buttons = QButtonGroup(self)
        for tool, text, tip in (("pick", "Pick", "click an atom; shift adds, ctrl toggles"),
                                ("box", "Box", "drag a rectangle"),
                                ("lasso", "Lasso", "draw around the atoms")):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(f"select sites: {tip}")
            button.setObjectName(f"tool_{tool}")
            button.setCheckable(True)
            button.setChecked(tool == "pick")
            button.clicked.connect(lambda checked=False, t=tool: self.set_tool(t))
            self.tool_buttons.addButton(button)
            geometry.addWidget(button)
        select = QToolButton()
        select.setText("Select")
        select.setObjectName("selectSitesButton")
        select.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(select)
        for text, name, args in (("All", "selectAll", {"all": True}),
                                 ("Sublattice A", "selectSublatticeA", {"sublattice": 1}),
                                 ("Sublattice B", "selectSublatticeB", {"sublattice": -1}),
                                 ("Edge sites", "selectEdge", {"edge": True}),
                                 ("Invert", "selectInvert", {"all": True, "mode": "toggle"}),
                                 ("Nothing", "selectNone", {"indices": []})):
            action = menu.addAction(text)
            action.setObjectName(name)
            action.triggered.connect(lambda checked=False, a=args: self._act("select_sites", **a))
        select.setMenu(menu)
        geometry.addWidget(select)
        self.region_button = QPushButton("Region from selection")
        self.region_button.setObjectName("regionFromSelectionButton")
        self.region_button.clicked.connect(lambda: self._act("region_from_selection"))
        geometry.addWidget(self.region_button)
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.setObjectName("removeSelectedButton")
        self.remove_button.setToolTip("remove the selected atoms (a Remove atoms op, by position)")
        self.remove_button.clicked.connect(lambda: self._act("remove_selected"))
        geometry.addWidget(self.remove_button)
        self.palettes["geometry"] = geometry

        hamiltonian = self._toolbar("Hamiltonian", "hamiltonianToolbar")
        self._menu_button(hamiltonian, "Add term", "addTermButton", _grouped("term"),
                          self.add_term, "addTerm")
        self.term_search = self._search_box(hamiltonian, "term", self.add_term, "termSearch",
                                            "find a term")
        hamiltonian.addSeparator()
        self.meanfield_button = QPushButton("Mean field")
        self.meanfield_button.setObjectName("meanfieldButton")
        self.meanfield_button.setToolTip("interactions solved self-consistently after the "
                                         "terms (the mean-field block of the current system)")
        self.meanfield_button.clicked.connect(self.show_meanfield)
        hamiltonian.addWidget(self.meanfield_button)
        self.palettes["hamiltonian"] = hamiltonian

        calculate = self._toolbar("Calculate", "calculateToolbar")
        self._menu_button(calculate, "Add calculation", "addCalculationButton",
                          _grouped("calculation"), self.add_calculation, "addCalc")
        self._search_box(calculate, "calculation", self.add_calculation, "calculationSearch",
                         "find a calculation")
        self.palettes["calculate"] = calculate

    def _search_box(self, bar, family, handler, name, placeholder):
        """A line with completion over a family's entries; Enter (or a
        completion) adds the best match with handler(kind)."""
        edit = QLineEdit()
        edit.setObjectName(name)
        edit.setPlaceholderText(placeholder)
        edit.setClearButtonEnabled(True)
        edit.setMaximumWidth(220)
        completer = QCompleter([f"{spec.label} ({spec.group})" for spec in _grouped(family)],
                               edit)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        edit.setCompleter(completer)
        completer.activated.connect(lambda text: self.add_searched(edit, family, handler, text))
        edit.returnPressed.connect(lambda: self.add_searched(edit, family, handler, edit.text()))
        bar.addWidget(edit)
        return edit

    def add_searched(self, edit, family, handler, text):
        """Add the best match of a palette search; returns its kind or None."""
        now = time.monotonic()
        if not text.strip() or (self._searched[0] == text and now - self._searched[1] < 0.5):
            return None                  # Enter and the completion both fire for one choice
        self._searched = (text, now)
        matches = search_entries(family, text)
        if not matches:
            self.message(f"no {family.replace('_', ' ')} matches {text.strip()!r}", error=True)
            return None
        handler(matches[0].kind)
        QTimer.singleShot(0, edit.clear)
        return matches[0].kind

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
        self._action(file_menu, "&Recover unsaved work...", self.offer_recovery,
                     name="recoverAction")
        file_menu.addSeparator()
        self._action(file_menu, "&Quit", self.close, QKeySequence.StandardKey.Quit)
        edit = self.menuBar().addMenu("&Edit")
        self.undo_action = self._action(edit, "&Undo", self.undo, QKeySequence.StandardKey.Undo,
                                        "undoAction")
        self.redo_action = self._action(edit, "&Redo", self.redo, "Ctrl+Shift+Z", "redoAction")
        view = self.menuBar().addMenu("&View")
        for i, name in enumerate(WORKSPACES):
            self._action(view, f"{name.capitalize()} workspace",
                         lambda checked=False, n=name: self.set_workspace(n), f"Ctrl+{i + 1}")
        view.addSeparator()
        for dock in self.docks.values():
            view.addAction(dock.toggleViewAction())
        run = self.menuBar().addMenu("&Run")
        self._action(run, "&Run calculation", self.run_selected, "F5", "runAction")
        self._action(run, "&Cancel", self.cancel_selected, "Esc", "cancelAction")
        run.addSeparator()
        self.auto_rerun_action = self._action(
            run, "Re-run cheap results &automatically", lambda: self.set_auto_rerun(
                self.auto_rerun_action.isChecked()), name="autoRerunAction")
        self.auto_rerun_action.setCheckable(True)
        self.auto_rerun_action.setToolTip(f"a stale result is computed again as soon as the "
                                          f"geometry is rebuilt, when it takes less than "
                                          f"{AUTO_RERUN_SECONDS:g} s")
        help_menu = self.menuBar().addMenu("&Help")
        self._action(help_menu, "&About", lambda: self.message(
            f"guiqula {guiqula.__version__}, {vendoring.describe()}"))
        self._action(help_menu, "Open &crash reports folder", lambda: self._open_folder(
            crashreport.reports_dir()))

    # ---- session
    def start_session(self, document=None, **options):
        """Create and attach a Session (starts the worker processes)."""
        from guiqula.session import Session
        options.setdefault("autosave", self.autosave)
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
        dispatcher = session.dispatcher
        dispatcher.register_action("select", lambda entry="": self.select(entry))
        dispatcher.register_action("workspace", lambda name: self.set_workspace(name))
        dispatcher.register_action("tool", lambda name: self.set_tool(name))
        dispatcher.register_action("select_sites", self.select_sites)
        dispatcher.register_action("region_from_selection", self.region_from_selection)
        dispatcher.register_action("remove_selected", self.remove_selected)
        dispatcher.register_action("canvas_view", lambda name: self.set_canvas_view(name))
        dispatcher.register_action("preview", lambda entry, param: self.preview_field(entry,
                                                                                      param))
        dispatcher.register_action("auto_rerun", lambda enabled=True: self.set_auto_rerun(enabled))
        session.view_state = self.view_state
        self.timer.start(POLL_MS)
        self._document_changed()
        self.apply_view_state(session.document.ui)
        self.offer_recovery(quiet=True)

    def closeEvent(self, event):
        if self.ask_before_close and self.session is not None and self.session.modified:
            if not self._confirm_discard():
                event.ignore()
                return
        self.timer.stop()
        self.build_timer.stop()
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        if self.session is not None and self._owns_session:
            self.session.close()     # a clean close: the autosave is deleted
        super().closeEvent(event)

    def _confirm_discard(self):
        name = self.session.path.name if self.session.path else "this document"
        answer = QMessageBox.question(
            self, "Unsaved changes", f"Save the changes to {name} before closing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            self.save()
            return not self.session.modified
        return True

    def _poll(self):
        try:
            self.session.poll(0)
        except Exception:
            self.message("error while polling the workers:\n" + traceback.format_exc(), error=True)
        self._update_autosave_label()

    def _on_session_event(self, kind, payload):
        if kind == "document":
            self._document_changed(payload)
        elif kind == "job":
            self._job_changed(payload)
        elif kind == "worker":
            self.jobs.update_workers(self.session.jobs.status())
            if payload["starts"] > 1 and payload["ready"] is False:
                self.message(f"{payload['role']} worker restarted (pid {payload['pid']})")

    def _document_changed(self, event=None):
        if event is not None and event["type"] == "action":
            # actions do not change the Document (new, load and recover reset it, and
            # region_from_selection and remove_selected announce their mutation): only
            # the title (save clears the asterisk) and the buttons can change
            self._update_title()
            self._update_actions()
            return
        if self.selected and not self._exists(self.selected):
            self.selected = ""
        self._refresh_calculations()
        self.outliner.refresh(self.session)
        self.outliner.set_current(self.selected)
        if self.properties.session is None or self.properties.item_id != self.selected:
            self.properties.show_item(self.session, self.selected)
        else:
            self.properties.refresh()
        self._refresh_structure()
        self._update_actions()
        self._refresh_results()
        self._update_status()
        self.build_timer.start(BUILD_DELAY_MS)
        self._update_title()
        if event is not None and event["type"] == "reset":      # new, open, recover
            self.apply_view_state(self.session.document.ui)

    def _update_title(self):
        path = self.session.path
        title = f"guiqula — {path.name}" if path else "guiqula"
        self.setWindowTitle(title + (" *" if self.session.modified else ""))

    def _exists(self, item_id):
        if item_id == "calculations":
            return True
        system = system_of(item_id)
        try:
            if system is not None:
                self.session.document.system(system)
            else:
                self.session.document.find(item_id)
            return True
        except Exception:
            return False

    @property
    def builds(self):
        """system id -> latest build summary (kept by the session)."""
        return self.session.builds if self.session is not None else {}

    def _request_builds(self):
        """Ask the interactive worker to build every system (geometry for
        the canvas, modes, entries pyqula rejects); requests coalesce."""
        if self.session is None:
            return
        try:
            self.session.build_all()
        except Exception as error:
            self.message(f"could not ask for a build: {error}", error=True)

    def _job_changed(self, job):
        if job.kind == "build":
            system = job.payload["system"]
            if job.status == "done" and self.builds.get(system) is job.value:
                self.outliner.refresh(self.session)
                self.properties.refresh()
                if system == self.current_system():
                    self._refresh_structure()
                self._update_status()
                self._rerun_stale()
            elif job.status == "failed":
                self.message(f"{system} cannot be built: {job.error}", error=True)
                self.outliner.refresh(self.session)
                self._refresh_structure()
            self.jobs.update_workers(self.session.jobs.status())
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
            self.outliner.refresh(self.session)
            self.properties.refresh()
            if job.status == "done" and job.kind == "run":
                if job.label in self.plots:
                    self._draw_result(job.label)
                if job.label == self.selected_calculation() and job.id not in self._auto_jobs:
                    self.show_result(job.label)      # an automatic re-run never steals the view
            self._auto_jobs.discard(job.id)
        elif job.kind == "run":
            self.outliner.update_calculation(self.session, job.label)   # queued, progress
        self.jobs.update_workers(self.session.jobs.status())

    # ---- selection and workspaces
    def select(self, entry=""):
        """Select an outliner item (an entry id, a system's pseudo id such
        as s1/base, or "" for nothing): properties, canvas overlays and the
        viewport tab follow."""
        entry = entry or ""
        if self.session is None:
            return ""
        if entry and not self._exists(entry):
            raise ValueError(f"nothing called {entry!r} in the document")
        self.selected = entry
        self.outliner.set_current(entry)
        self.properties.show_item(self.session, entry)
        family = None
        if entry and "/" not in entry and entry != "calculations":
            family = self.session.document.find(entry)[0]
        if family == "calculation":
            self.select_calculation(entry)
            self.show_result(entry)
        elif entry and entry != "calculations":
            self.viewport.setCurrentIndex(STRUCTURE_TAB)
        self._refresh_structure()
        self._update_status()
        return entry

    def set_workspace(self, name):
        if name not in WORKSPACES:
            raise ValueError(f"unknown workspace {name!r}; workspaces: {list(WORKSPACES)}")
        self.workspace = name
        index = WORKSPACES.index(name)
        if self.workspace_tabs.currentIndex() != index:
            self.workspace_tabs.blockSignals(True)
            self.workspace_tabs.setCurrentIndex(index)
            self.workspace_tabs.blockSignals(False)
        for key, bar in self.palettes.items():
            bar.setVisible(key == name)
        if name in CANVAS_VIEW_OF and self.canvas_view != CANVAS_VIEW_OF[name]:
            self.set_canvas_view(CANVAS_VIEW_OF[name])
        calc = self.selected_calculation()
        if name == "calculate" and calc is not None:
            self.show_result(calc)
        else:
            self.viewport.setCurrentIndex(STRUCTURE_TAB)
        return name

    # ---- the canvas views and the Field preview
    def set_canvas_view(self, name):
        """What the structure canvas shows: structure, hamiltonian or field."""
        if name not in structure_tools.VIEWS:
            raise ValueError(f"unknown view {name!r}; views: {list(structure_tools.VIEWS)}")
        self.canvas_view = name
        self.structure.set_view(name)
        if self.session is not None:
            self._refresh_structure()
        return name

    def preview_field(self, entry, param):
        """Draw a Field of a term (or of a mean field, <system>/meanfield) on
        the structure; the canvas switches to the field view."""
        self._field_entry(entry, param)          # raises for a wrong entry or parameter
        self.field_preview = (entry, param)
        self.viewport.setCurrentIndex(STRUCTURE_TAB)
        return self.set_canvas_view("field")

    def _preview_requested(self, entry, param):
        """A Field editor is being looked at (debounced: typing redraws)."""
        self.field_preview = (entry, param)
        if self.canvas_view != "field":
            self.canvas_view = "field"
            self.structure.set_view("field")
        self.preview_timer.start(PREVIEW_DELAY_MS)

    def _field_entry(self, entry, param):
        """(system, spec, params, restricting region or None) of a Field."""
        document = self.session.document
        if entry.endswith("/meanfield"):
            system = document.system(system_of(entry))
            block = system.hamiltonian.meanfield
            spec, params, region = registry.get("meanfield", block.kind), block.params, None
        else:
            family, system, _, _, obj = document.find(entry)
            if family != "term":
                raise ValueError(f"{entry!r} is a {family}; Fields are parameters of terms "
                                 f"and of the mean field")
            spec, params = registry.get("term", obj.kind), obj.params
            region = next((r for r in system.regions if r.id == obj.region), None)
        if param not in spec.param_map or not hasattr(spec.param_map[param], "native"):
            fields_of = [p.name for p in spec.params if hasattr(p, "native")]
            raise ValueError(f"{entry} has no Field {param!r}; its Fields: {fields_of}")
        return system, spec, params, region

    def _field_overlay(self, system_id, build):
        """(overlays, caption) of the field view."""
        if self.field_preview is None:
            return {}, "click into a Field of a term (its f(r) panel) to preview it here"
        entry, name = self.field_preview
        try:
            system, spec, params, region = self._field_entry(entry, name)
        except (ValueError, KeyError, registry.RegistryError) as error:
            return {}, str(error).strip("\"'")
        if system.id != system_id:
            return {}, f"{entry} belongs to {system.id}"
        param = spec.param_map[name]
        value = params.get(name, param.default)
        form = self.properties.form
        if form is not None and getattr(form, "item_id", None) == entry:
            live = form.live_value(name)
            value = live if live is not None else value
        positions = build["positions"]
        regions = {r.id: r.select for r in system.regions}
        weight = np.ones(len(positions))
        if region is not None and param.native:
            weight = region_tools.evaluate_positions(region.select, positions).astype(float)
        label = f"{entry} {param.label}"
        try:
            if isinstance(param, VectorFieldParam):
                vectors = np.stack([fields.evaluate_positions(v, positions, regions)
                                    for v in value], axis=1) * weight[:, None]
                overlays = {"arrows": {"vectors": vectors, "label": label}}
                size = np.linalg.norm(vectors, axis=1)
                return overlays, f"{label}: |value| from {size.min():.4g} to {size.max():.4g}"
            values = fields.evaluate_positions(value, positions, regions) * weight
        except Exception as error:
            return {}, f"{label}: {error}"
        return ({"site_values": {"values": values, "label": label}},
                f"{label}: from {values.min():.4g} to {values.max():.4g}")

    def _hamiltonian_overlay(self, build):
        view = build.get("hamiltonian")
        if view is None:
            return {}, "the Hamiltonian view is not computed for this many sites"
        overlays = {"site_values": {"values": view["onsite"], "label": "onsite energy"},
                    "hoppings": view}
        parts = [f"onsite {np.min(view['onsite']):.3g} to {np.max(view['onsite']):.3g}"]
        if len(view["amplitude"]):
            parts.append(f"|t| up to {np.max(view['amplitude']):.3g}")
        if len(view["spin"]) and np.max(view["spin"]) > 1e-9:
            parts.append(f"spin-dependent hopping up to {np.max(view['spin']):.3g}")
        exchange = view.get("exchange")
        if exchange is not None and np.max(np.abs(exchange)) > 1e-12:
            overlays["arrows"] = {"vectors": exchange, "label": "exchange field"}
            parts.append(f"exchange up to {np.max(np.linalg.norm(exchange, axis=1)):.3g} "
                         f"(arrows: in-plane part)")
        pairing = view.get("pairing")
        if pairing is not None:
            parts.append(f"pairing up to {np.max(pairing):.3g}")
        return overlays, "Hamiltonian before the mean field: " + ", ".join(parts)

    # ---- view state, saved with the project
    def view_state(self):
        """What the window shows, as the Document's ui block."""
        state = {"workspace": self.workspace, "selected": self.selected,
                 "tool": self.structure.tool, "tab": self.current_tab(),
                 "canvas_view": self.canvas_view, "results": list(self.plots)}
        if self.auto_rerun:
            state["auto_rerun"] = True
        if self.field_preview is not None:
            state["preview"] = list(self.field_preview)
        if self.selected_calculation():
            state["calculation"] = self.selected_calculation()
        if self.structure.system_id is not None and len(self.structure.selected()):
            state["sites"] = {"system": self.structure.system_id,
                              "positions": [[round(float(c), 10) for c in p]
                                            for p in self.structure.selected_positions]}
        return state

    def apply_view_state(self, ui):
        """Show what a saved ui block describes; whatever no longer fits the
        Document (a removed entry, an unknown tool) is skipped, never an
        error. An empty block leaves the workspace and the tool as they are
        and selects nothing."""
        ui = ui if isinstance(ui, dict) else {}
        self._pending_sites = None
        for calc in list(self.plots):
            self.close_result(calc)
        self.field_preview = None
        preview = ui.get("preview")
        if isinstance(preview, list) and len(preview) == 2 and all(isinstance(p, str)
                                                                   for p in preview):
            try:
                self._field_entry(*preview)
                self.field_preview = tuple(preview)
            except Exception:
                pass
        self.set_auto_rerun(ui.get("auto_rerun") is True)
        if ui.get("workspace") in WORKSPACES:
            self.set_workspace(ui["workspace"])
        if ui.get("canvas_view") in structure_tools.VIEWS:
            self.set_canvas_view(ui["canvas_view"])
        if ui.get("tool") in structure_tools.TOOLS:
            self.set_tool(ui["tool"])
        if isinstance(ui.get("calculation"), str) and self.calc_box.findData(ui["calculation"]) >= 0:
            self.select_calculation(ui["calculation"])
        selected = ui.get("selected", "")
        self.select(selected if isinstance(selected, str) and self._exists(selected) else "")
        for calc in ui.get("results", []) if isinstance(ui.get("results"), list) else []:
            if isinstance(calc, str) and self.calc_box.findData(calc) >= 0:
                self.result_view(calc)
        tab = ui.get("tab")
        if tab == "result" and self.selected_calculation():           # before phase 3
            tab = self.selected_calculation()
        if tab == "structure":
            self.viewport.setCurrentIndex(STRUCTURE_TAB)
        elif isinstance(tab, str) and self.calc_box.findData(tab) >= 0:
            self.show_result(tab)
        sites = ui.get("sites")
        if isinstance(sites, dict) and isinstance(sites.get("positions"), list):
            self._pending_sites = (sites.get("system"), sites["positions"])
            self._refresh_structure()

    # ---- canvas tools and the site selection
    def set_tool(self, name):
        self.structure.set_tool(name)
        for button in self.tool_buttons.buttons():
            button.setChecked(button.objectName() == f"tool_{name}")
        return name

    def select_sites(self, mode="replace", indices=None, box=None, polygon=None, point=None,
                     positions=None, sublattice=None, edge=False, all=False):
        """Select sites of the geometry on the Structure tab, as the canvas
        tools do; give one of: indices, box [x0, y0, x1, y1], polygon
        [[x, y], ...], point [x, y], positions [[x, y, z], ...], sublattice
        (1 or -1), edge (sites with fewer neighbours than the most
        connected), all. mode: replace, add, toggle, remove. Returns the
        number of selected sites."""
        build = self.structure.build
        if build is None:
            raise ValueError("there is no geometry on the Structure tab to select from")
        r = build["positions"]
        given = [k for k, v in dict(indices=indices, box=box, polygon=polygon, point=point,
                                    positions=positions, sublattice=sublattice).items()
                 if v is not None] + (["edge"] if edge else []) + (["all"] if all else [])
        if len(given) != 1:
            raise ValueError(f"give exactly one way of selecting, got {given or 'none'}")
        if indices is not None:
            chosen = [int(i) for i in indices]
            if any(not 0 <= i < len(r) for i in chosen):
                raise ValueError(f"site indices go from 0 to {len(r) - 1}")
        elif box is not None:
            chosen = structure_tools.indices_in_box(r, *box)
        elif polygon is not None:
            chosen = structure_tools.indices_in_polygon(r, polygon)
        elif point is not None:
            i = structure_tools.nearest_index(r, *point)
            chosen = [] if i is None else [i]
        elif positions is not None:
            chosen = structure_tools.match_positions(r, positions, REGION_TOLERANCE)
        elif sublattice is not None:
            chosen = structure_tools.sublattice_indices(build, sublattice)
        elif edge:
            chosen = structure_tools.edge_indices(build)
        else:
            chosen = range(len(r))
        return self.structure.select(chosen, mode)

    def _selection_positions(self):
        system = self.structure.system_id
        positions = self.structure.selected_positions
        if system is None or not len(self.structure.selected()):
            raise ValueError("no sites are selected")
        if not self.session.build_is_current(system):
            raise ValueError("the geometry is being rebuilt; select again when it is shown")
        return system, [[float(c) for c in p] for p in positions]

    def region_from_selection(self, name=""):
        """A region holding the selected sites, by position; returns its id."""
        system, positions = self._selection_positions()
        region = self.session.do("add_region", system=system, name=name, select={
            "kind": "positions", "positions": positions, "tol": REGION_TOLERANCE})
        self.select(region)
        return region

    def remove_selected(self):
        """Remove the selected sites: extend the system's last op if it is
        an enabled Remove atoms op, else add one. Returns the op id."""
        system, positions = self._selection_positions()
        ops = self.session.document.system(system).geometry.ops
        last = ops[-1] if ops else None
        if last is not None and last.kind == "remove_atoms" and last.enabled:
            stored = last.params["positions"]
            new = [p for p in positions if not len(structure_tools.match_positions(
                [p], stored, structure_tools.SAME_SITE))]
            self.session.do("set_param", entry=last.id, name="positions", value=stored + new)
            op = last.id
        else:
            op = self.session.do("add_geometry_op", system=system, kind="remove_atoms",
                                 params={"positions": positions})
        self.structure.select([], "replace")
        self.select(op)
        return op

    def _selection_changed(self, count):
        self.region_button.setEnabled(count > 0)
        self.remove_button.setEnabled(count > 0)

    def current_system(self):
        """The system of the selected item, else the first one, else None."""
        if self.session is None or not self.session.document.systems:
            return None
        entry = self.selected
        if entry and entry != "calculations":
            system = system_of(entry)
            if system is not None:
                return system
            family, owner, _, _, obj = self.session.document.find(entry)
            if family == "system":
                return obj.id
            if family == "calculation":
                return obj.system
            return owner.id
        return self.session.document.systems[0].id

    def _overlays(self, system_id, build):
        """What the selected entry touches, drawn over the structure."""
        entry = self.selected
        if not entry or "/" in entry or entry == "calculations":
            return {}
        family, owner, _, _, obj = self.session.document.find(entry)
        if owner is None or owner.id != system_id:
            return {}
        region = obj if family == "region" else None
        if family == "term" and obj.region:
            region = next((r for r in owner.regions if r.id == obj.region), None)
        if region is not None:
            try:
                return {"highlight": region_tools.evaluate_positions(region.select,
                                                                     build["positions"])}
            except Exception:
                return {}
        if family == "op" and "positions" in obj.params:
            return {"removed": obj.params["positions"]}
        return {}

    def _refresh_structure(self):
        system = self.current_system()
        if system is None:
            self.structure.clear("No system yet: add one with New system (Geometry toolbar).")
            return
        build = self.builds.get(system)
        error = self.session.build_errors.get(system)
        if build is None:
            self.structure.clear(f"{system} cannot be built: {error}" if error
                                 else f"{system}: building…")
            return
        caption = (f"{system} · {build['dimensionality']}D · {build['sites']} sites · "
                   f"{build['mode']}")
        if error:
            caption += f" · the latest change cannot be built: {error}"
        elif not self.session.build_is_current(system):
            caption += " · updating…"
        overlays = self._overlays(system, build)
        if self.canvas_view == "hamiltonian":
            extra, text = self._hamiltonian_overlay(build)
        elif self.canvas_view == "field":
            extra, text = self._field_overlay(system, build)
        else:
            extra, text = {}, ""
        overlays.update(extra)
        caption += f"\n{text}" if text else ""
        self.structure.show_structure(system, build, caption, **overlays)
        pending = self._pending_sites
        if pending is not None and pending[0] == system and self.session.build_is_current(system):
            self._pending_sites = None
            try:
                self.structure.select(structure_tools.match_positions(
                    build["positions"], pending[1], REGION_TOLERANCE))
            except (ValueError, TypeError):
                pass

    def _update_status(self):
        system = self.current_system()
        if system is None:
            self.status_label.setText("empty document")
            return
        build = self.builds.get(system)
        if build is None:
            self.status_label.setText(f"{system}: building…")
            return
        text = (f"{system} · {build['dimensionality']}D · {build['sites']} sites · "
                f"{build['mode']} · dimension {build['dimension']}")
        calc = self.selected_calculation()
        estimate = self.session.estimate(calc) if calc else None
        if estimate is not None:
            text += f" · {calc}: {cost.describe(estimate['seconds'])}"
            if estimate["meanfield"]:
                text += " with the mean field"
        self.status_label.setText(text)

    def _update_autosave_label(self):
        saver = self.session.autosaver if self.session is not None else None
        if saver is None:
            text = ""
        elif saver.error:
            text = saver.error
        elif saver.saved_at:
            text = "autosaved " + time.strftime("%H:%M:%S", time.localtime(saver.saved_at))
        else:
            text = ""
        if self.autosave_label.text() != text:
            self.autosave_label.setText(text)

    # ---- palettes
    def _do_and_select(self, command, /, **args):
        ok, out = self._do(command, **args)
        if ok and isinstance(out, str):
            self.select(out)
        return out if ok else None

    def new_system(self, lattice):
        return self._do_and_select("add_system", lattice=lattice)

    def _target_system(self):
        system = self.current_system()
        if system is None:
            self.message("add a system first (New system)", error=True)
        return system

    def add_op(self, kind):
        system = self._target_system()
        return self._do_and_select("add_geometry_op", system=system, kind=kind) if system else None

    def add_term(self, kind):
        system = self._target_system()
        return self._do_and_select("add_term", system=system, kind=kind) if system else None

    def add_calculation(self, kind):
        system = self._target_system()
        return self._do_and_select("add_calculation", system=system, kind=kind) if system else None

    def add_region(self, select=None, name=""):
        system = self._target_system()
        if system is None:
            return None
        select = select or {"kind": "expression", "expr": "x > 0"}
        return self._do_and_select("add_region", system=system, select=select, name=name)

    def _outliner_command(self, name, args):
        if name == "run_calculation":                 # its context menu: the cost guard too
            self.run_guarded(args["calculation"])
            return
        ok, out = self._do(name, **args)
        if ok and name == "duplicate":
            self.select(out)

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

    def _calculation_chosen(self, index):
        """The calculation box changed: follow it when a result is shown."""
        calc = self.selected_calculation()
        if calc is not None and self.current_tab() != "structure":
            self.show_result(calc)
        self._update_status()

    # ---- result views: one tab (or floating dock) per calculation
    @property
    def plot(self):
        """The result view of the selected calculation (made on first use)."""
        calc = self.selected_calculation()
        return self.result_view(calc) if calc is not None else None

    def current_tab(self):
        """"structure", or the id of the calculation whose tab is shown."""
        widget = self.viewport.currentWidget()
        return widget.calc_id if isinstance(widget, PlotView) else "structure"

    def result_view(self, calc):
        """The PlotView of a calculation, made (as a tab) if needed."""
        view = self.plots.get(calc)
        if view is None:
            self.session.document.calculation(calc)
            view = PlotView(calc)
            view.save_requested.connect(self.save_result_dialog)
            view.detach_requested.connect(self.toggle_detached)
            self.plots[calc] = view
            self.viewport.addTab(view, calc)
            self._draw_result(calc)
        return view

    def show_result(self, calc):
        """Bring a calculation's result view forward (its tab, or its dock)."""
        view = self.result_view(calc)
        dock = self.plot_docks.get(calc)
        if dock is not None:
            dock.show()
            dock.raise_()
        else:
            self.viewport.setCurrentWidget(view)
        return calc

    def close_result(self, calc):
        view = self.plots.pop(calc, None)
        dock = self.plot_docks.pop(calc, None)
        if view is None:
            return
        index = self.viewport.indexOf(view)
        if index >= 0:
            self.viewport.removeTab(index)
        view.hide()
        view.deleteLater()               # may run inside a signal of its own tab bar
        if dock is not None:
            dock.hide()
            dock.deleteLater()

    def _close_tab(self, index):
        widget = self.viewport.widget(index)
        if isinstance(widget, PlotView):
            self.close_result(widget.calc_id)

    def toggle_detached(self, calc):
        """Move a result view into a floating dock, or back into its tab."""
        view = self.plots[calc]
        dock = self.plot_docks.pop(calc, None)
        if dock is not None:
            dock.setWidget(None)
            view.setParent(None)
            dock.hide()
            dock.deleteLater()
            self.viewport.addTab(view, self._tab_text(calc))
            self.viewport.setCurrentWidget(view)
            view.set_detached(False)
            return False
        self.viewport.removeTab(self.viewport.indexOf(view))
        dock = QDockWidget(f"Result {calc}", self)
        dock.setObjectName(f"resultDock_{calc}")
        dock.setWidget(view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.setFloating(True)
        dock.resize(640, 480)
        dock.show()
        view.show()
        view.set_detached(True)
        self.plot_docks[calc] = dock
        return True

    def _tab_text(self, calc):
        try:
            kind = self.session.document.calculation(calc).kind
        except Exception:
            return calc
        return f"{calc} {kind}" + (" (stale)" if self.session.is_stale(calc) else "")

    def _draw_result(self, calc):
        """Draw a calculation's latest result into its view, unless the view
        already shows exactly that (a redraw would lose the zoom)."""
        view = self.plots[calc]
        result = self.session.result(calc)
        stale = self.session.is_stale(calc) if result is not None else False
        index = self.viewport.indexOf(view)
        if index >= 0:
            self.viewport.setTabText(index, self._tab_text(calc))
        dock = self.plot_docks.get(calc)
        if dock is not None:
            dock.setWindowTitle(f"Result {self._tab_text(calc)}")
        if result is None:
            if view.result is not None or not view.caption.text().startswith(calc):
                view.clear(f"{calc}: no result yet; press Run (F5).")
            return
        if view.result is result and view.stale == stale:
            return
        title = f"{calc} · {result.kind} · {result.mode}" + (" · STALE" if stale else "")
        notes = [f"{result.meta.get('seconds', 0):.2f} s"]
        if result.meta.get("build_seconds", 0) >= 0.05:
            notes[0] += f" after {result.meta['build_seconds']:.2f} s of building"
        if result.meanfield:
            notes.append(f"mean-field total energy {result.meanfield.get('total_energy', 0):.6g}")
        if result.skipped:
            notes.append("skipped: " + ", ".join(f"{r['id']} ({r['message']})"
                                                 for r in result.skipped))
        if stale:
            notes.append("the document changed since this result was computed; run again")
        view.show_result(result, title, " · ".join(notes), stale=stale)

    def _refresh_results(self):
        """After a document change: close the views of removed calculations,
        mark stale results."""
        present = {c.id for c in self.session.document.calculations}
        for calc in list(self.plots):
            if calc not in present:
                self.close_result(calc)
            else:
                self._draw_result(calc)

    def save_result_dialog(self, calc):
        path, _ = QFileDialog.getSaveFileName(self, f"Save the data of {calc}", f"{calc}.npz",
                                              "arrays and metadata (*.npz)")
        if path:
            self._act("save_result", calculation=calc, path=path)

    def run_selected(self):
        """Run the selected calculation (the Run button, F5)."""
        calc = self.selected_calculation()
        if calc is None:
            self.message("no calculation to run", error=True)
            return None
        return self.run_guarded(calc)

    def run_guarded(self, calc, confirmed=False):
        """Run a calculation; one that would take longer than cost.SLOW
        asks first, in the cost bar (non-modal)."""
        estimate = self.session.estimate(calc)
        if not confirmed and estimate is not None and estimate["seconds"] > cost.SLOW:
            extra = " including the mean field" if estimate["meanfield"] else ""
            self.cost_bar.show_message(
                f"{calc} will take {cost.describe(estimate['seconds'])}{extra} (Hilbert space "
                f"dimension {estimate['dimension']}). Run it anyway?",
                [("Run anyway", lambda: self.run_guarded(calc, confirmed=True),
                  "runAnywayButton"),
                 ("Cancel", self.cost_bar.dismiss, "costCancelButton")])
            return None
        self.cost_bar.dismiss()
        return self._act("run_calculation", calculation=calc)

    def set_auto_rerun(self, enabled=True):
        """Re-run stale results automatically when they are cheap (opt-in)."""
        self.auto_rerun = bool(enabled)
        self.auto_rerun_action.setChecked(self.auto_rerun)
        if self.auto_rerun and self.session is not None:
            self._rerun_stale()
        return self.auto_rerun

    def _rerun_stale(self):
        """Run again the stale results whose system is built from the
        current Document and whose estimate is below AUTO_RERUN_SECONDS;
        a calculation is re-run once per key, so a failure does not loop."""
        if not self.auto_rerun or self.session is None:
            return []
        started = []
        for calc in self.session.document.calculations:
            if calc.id not in self.session.results or not self.session.is_stale(calc.id) \
                    or not self.session.build_is_current(calc.system):
                continue
            try:
                key = pipeline.calculation_key(self.session.document, calc.id)
            except Exception:
                continue
            estimate = self.session.estimate(calc.id)
            if self._auto_keys.get(calc.id) == key or estimate is None \
                    or estimate["seconds"] > AUTO_RERUN_SECONDS:
                continue
            self._auto_keys[calc.id] = key
            self.session.jobs.supersede("run", calc.id)
            job = self._act("run_calculation", calculation=calc.id)
            if job is not None:
                self._auto_jobs.add(job["id"])
                started.append(calc.id)
        return started

    def show_meanfield(self):
        system = self._target_system()
        if system is not None:
            self.select(f"{system}/meanfield")

    def cancel_selected(self):
        calc = self.selected_calculation()
        job = self.session.calc_jobs.get(calc) if calc else None
        if job is not None and not job.done:
            self.cancel_job(job.id)

    def cancel_job(self, job_id):
        self._act("cancel", target=job_id)

    # ---- files, recovery and undo
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
        path, _ = QFileDialog.getSaveFileName(self, "Save", "",
                                              "guiqula (*.guiqula);;JSON (*.json)")
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

    def offer_recovery(self, quiet=False):
        """Show the recovery bar for the newest autosave a session that did
        not close cleanly left behind (non-modal; drivers use the recover
        action)."""
        entries = [e for e in (self._act("list_recoverable") or []) if "error" not in e]
        if not entries:
            self.recovery_bar.dismiss()
            if not quiet:
                self.message("there is no unsaved work to recover")
            return
        entry = entries[0]
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry["saved"]))
        what = ", ".join(entry["systems"]) or "an empty document"
        source = f" (from {Path(entry['source']).name})" if entry.get("source") else ""
        more = f"; {len(entries) - 1} more after this one" if len(entries) > 1 else ""
        self.recovery_bar.show_message(
            f"A session did not close cleanly ({when}), leaving unsaved work: {what}{source}"
            f"{more}.",
            [("Recover", lambda: self.recover(entry["path"]), "recoverButton"),
             ("Discard", lambda: self._discard_recovery(entry["path"]), "discardRecoveryButton")])

    def recover(self, path=None):
        info = self._act("recover", **({"path": path} if path else {}))
        if info is not None:
            self.recovery_bar.dismiss()
            self.message(f"recovered {info['path']}")
        return info

    def _discard_recovery(self, path):
        self._act("discard_recovery", path=path)
        self.offer_recovery(quiet=True)

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
        self.add_region_button.setEnabled(has and bool(self.session.document.systems))
        self.meanfield_button.setEnabled(has and bool(self.session.document.systems))
        self._selection_changed(len(self.structure.selected()))

    # ---- commands and messages
    def _do(self, command, /, **args):
        """Run a mutation or an action; returns (True, result) or (False,
        message), reporting the refusal in the log instead of raising (a UI
        error never takes the window down, PLAN.md 3.5)."""
        try:
            return True, self.session.run(command, **args)
        except Exception as error:
            text = str(error)
            self.message(text if text.startswith(f"{command}:") else f"{command}: {text}",
                         error=True)
            return False, text

    def _act(self, command, /, **args):
        ok, out = self._do(command, **args)
        return out if ok else None

    def message(self, text, error=False):
        self.log.appendPlainText(("ERROR: " if error else "") + text)
        self.statusBar().showMessage(text.splitlines()[0], 8000)

    def report_exception(self, kind, value, tb):
        """An exception nobody caught (ui/errors.py): log it, write a crash
        report (once per distinct traceback) and show the error bar."""
        text = "".join(traceback.format_exception(kind, value, tb))
        self.log.appendPlainText("UNEXPECTED ERROR\n" + text)
        if text != self._last_crash_text:
            self._last_crash_text = text
            document = self.session.document.to_json() if self.session is not None else None
            try:
                self.last_crash_report = crashreport.write(
                    text, document, self.log.toPlainText(),
                    extra={"selected": self.selected, "workspace": self.workspace})
            except OSError as error:
                self.last_crash_report = None
                self.log.appendPlainText(f"could not write a crash report: {error}")
        where = f" A crash report is in {self.last_crash_report}." if self.last_crash_report else ""
        buttons = [("Open report folder", lambda: self._open_folder(self.last_crash_report),
                    "openReportButton")] if self.last_crash_report else []
        self.error_bar.show_message(f"Unexpected error: {kind.__name__}: {value}. The program "
                                    f"keeps running.{where}", buttons)

    def _open_folder(self, folder):
        Path(folder).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
