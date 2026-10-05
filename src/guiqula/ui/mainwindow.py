"""The main window (PLAN.md section 4): one document, three workspaces
(Geometry, Hamiltonian, Calculate) that follow the selection and change
what Add lists and the emphasis, not the data; an entry is added from
where it will appear, the "+" of its outliner section or the first row's
Add, both one searchable menu (ui/palette.py, PLAN.md phase 8, package
P2); the outliner on the left, the viewport (the
Structure tab and one closable tab per calculation's result, which can be
detached into windows of their own) in the centre, the properties form on
the right with Help, Sliders and Jobs tabbed below it, so that the help never
hides the form it explains, the Log and the Console at the bottom, hidden
until the status bar's Log toggle shows them, and the status bar, which
shows the last message (PLAN.md phase 8, package P5). The panels never
float (decision 88); the program's window keeps their arrangement and its
size in the settings (layout), and View > Reset layout gives the default
back.

The structure canvas has three views: the sites and bonds (the Geometry
workspace), the Hamiltonian (13.8, the Hamiltonian workspace), and the
preview of the Field being edited (PLAN.md 3.8), which a Field editor
selects when the user looks at it. The cost guard (13.12) shows the rough
duration of the selected calculation in the status bar and asks, in a
non-modal bar, before running one that takes minutes; stale results of
cheap calculations can be re-run automatically (opt-in, Run menu), and
with Run at once (a setting, on in the interactive program) a calculation
runs as soon as it is added or one of its parameters is set.

A result view answers a right click (or a click with its Pick toggle, or
a box or a lasso on a result drawn on the atoms) with the menu of what the
point stands for and what can be done with it (PLAN.md phase 7): the
actions pick and pick_to, which emit ordinary commands, so an undo takes a
pick back and the Document holds plain numbers. The value a pick set stays
drawn on the plot it was picked on as a marker, a slider with "on" (the
calculation whose view draws it): dragging it sets the parameter, and it
follows the parameter whatever changes it.

The window is a client of a Session: every change goes through the
dispatcher. The selected item, the workspace, the canvas tool and the site
selection are window state, not Document mutations; they are registered on
the dispatcher as actions (select, workspace, tool, select_sites), so
tools/drive.py and the remote API (remote/) reach them without putting clicks
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
from PySide6.QtCore import QByteArray, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog,
                               QDockWidget, QFileDialog, QHeaderView, QLabel,
                               QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QStackedWidget, QStyle, QStyleOptionDockWidget, QStylePainter,
                               QTabBar, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
                               QToolButton, QVBoxLayout, QWidget)

import guiqula
from guiqula import vendoring
from guiqula.core import fields
from guiqula.core import picks as pick_tools
from guiqula.core import regions as region_tools
from guiqula.io import bundle, crashreport, project, settings
from guiqula.registry import base as registry
from guiqula.registry import cost, pipeline
from guiqula.registry import picks as pick_targets
from guiqula.registry.params import VectorFieldParam
from guiqula.ui.bars import MessageBar, StatusMessage
from guiqula.ui.console import ConsoleWidget
from guiqula.ui.help import HelpPanel
from guiqula.ui.kspace import KSpaceView
from guiqula.ui.sliders import SlidersPanel
from guiqula.ui.jobpanel import JobPanel
from guiqula.ui.outliner import Outliner, pseudo_ids, system_of
from guiqula.ui.palette import FAMILIES as PALETTE_FAMILIES, MenuButton, PaletteMenu
from guiqula.ui.marks import ERROR_STATES, calculation_state, mark
from guiqula.ui.plots import ROW_STATES, PlotView, ResultWindow, in_3d as plot_in_3d
from guiqula.ui.properties import PropertiesPanel
from guiqula.ui.start import StartPage
from guiqula.ui import structure as structure_tools
from guiqula.ui.structure import StructureView
from guiqula.ui import icons, pyvista_view, shortcuts, theme

POLL_MS = 30
BUILD_DELAY_MS = 150
PREVIEW_DELAY_MS = 120
WORKSPACES = ("geometry", "hamiltonian", "calculate")
# actions of the window itself: they change what is shown, not the Document
WINDOW_ACTIONS = ("select", "workspace", "tool", "select_sites", "region_from_selection",
                  "remove_selected", "canvas_view", "preview", "auto_rerun", "projection",
                  "overlay", "slider", "set_slider", "remove_slider", "paint", "theme",
                  "export_bundle", "help", "remote", "pick", "pick_to", "run_at_once",
                  "renderer_3d", "view_3d", "plot_text", "ui_text", "reset_layout", "log",
                  "panel", "add_menu", "run_stale", "start", "run")
STRUCTURE_TAB = 0
KSPACE_TAB = 1
# a new classical system: its lattice, and a supercell the usual orders fit in
CLASSICAL_STARTS = {"classical_spin": ("triangular_lattice", 3, "Classical spins"),
                    "lattice_gas": ("triangular_lattice", 6, "Lattice gas"),
                    "ising": ("square_lattice", 8, "Ising model")}
REGION_TOLERANCE = 0.05      # positions regions made from a canvas selection
AUTO_RERUN_SECONDS = 3.0     # stale results re-run automatically when cheaper than this
CANVAS_VIEW_OF = {"geometry": "structure", "hamiltonian": "hamiltonian"}
# what the toolbar's Add lists in each workspace (PLAN.md phase 8, package P2), and says
WORKSPACE_FAMILIES = {"geometry": "geometry_op", "hamiltonian": "term",
                      "calculate": "calculation"}
ADD_TIPS = {"geometry": "add a geometry op to the current system (a supercell, a ribbon, an "
                        "island, cuts, strain...): type to search, Enter adds the best match",
            "hamiltonian": "add a term to the current system's Hamiltonian (or model), applied "
                           "after the others, or turn on its mean field: type to search, Enter "
                           "adds the best match",
            "calculate": "add a calculation on the current system, which Run computes: type "
                         "to search, Enter adds the best match"}
# the panels' sides (PLAN.md phase 8, package P5); the bottom ones are hidden by default
DOCK_AREAS = {"outlinerDock": Qt.DockWidgetArea.LeftDockWidgetArea,
              "propertiesDock": Qt.DockWidgetArea.RightDockWidgetArea,
              "helpDock": Qt.DockWidgetArea.RightDockWidgetArea,
              "slidersDock": Qt.DockWidgetArea.RightDockWidgetArea,
              "jobsDock": Qt.DockWidgetArea.RightDockWidgetArea,
              "logDock": Qt.DockWidgetArea.BottomDockWidgetArea,
              "consoleDock": Qt.DockWidgetArea.BottomDockWidgetArea}
BOTTOM_DOCKS = ("logDock", "consoleDock")
PROPERTIES_SHARE = 0.6       # of the right column's height, the rest to Help, Sliders, Jobs
LOG_HEIGHT = 160             # pixels the bottom area takes when the Log toggle first shows it
# the version of the window's saveState() kept in the settings (layout): a change of the
# docks or the toolbars that a stored arrangement would misplace raises it, and a stored
# one of another version gives the default arrangement
LAYOUT_VERSION = 4           # 4: the first row shows icons, Properties has a footer (P8)
# what each panel is, in the tooltip of its entry of View > Panels
PANEL_TIPS = {"outlinerDock": "the systems, their geometry, terms and mean field, and the "
                              "calculations",
              "propertiesDock": "the form of the selected entry",
              "helpDock": "the help of the selected entry ({help}) and the guides",
              "slidersDock": "parameters moved by a slider",
              "jobsDock": "the calculations running and the last ones done",
              "logDock": "every message so far (the Log button of the status bar)",
              "consoleDock": "Python on the current system, run in the worker"}


class Dock(QDockWidget):
    """A panel whose title is drawn in the panel's own font. Qt draws a
    dock's title in the font the application had when the dock was made
    (QDockWidgetPrivate::font), so View > Interface text would leave the
    titles at their old size while everything else changes."""

    def paintEvent(self, event):
        if self.isFloating() or self.titleBarWidget() is not None:
            return super().paintEvent(event)
        painter = QStylePainter(self)
        option = QStyleOptionDockWidget()
        self.initStyleOption(option)
        painter.drawControl(QStyle.ControlElement.CE_DockWidgetTitle, option)


def workspace_of(entry, family=None):
    """The workspace an outliner item belongs to (family: what
    Document.find says of an entry id), or None for nothing selected."""
    if not entry:
        return None
    if entry == "calculations" or family == "calculation":
        return "calculate"
    if family is not None:
        return "hamiltonian" if family == "term" else "geometry"
    row = entry.split("/", 1)[1] if "/" in entry else ""
    return "hamiltonian" if row in ("hamiltonian", "meanfield", "model_stack", "model") \
        else "geometry"


class MainWindow(QMainWindow):
    def __init__(self, parent=None, ask_before_close=False, autosave=True, use_settings=False):
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setWindowTitle("guiqula")
        self.resize(1280, 820)
        self.session = None
        self.ask_before_close = ask_before_close   # the interactive program asks (ui/app.py)
        self.autosave = autosave
        # the interactive program reads and writes the settings file (theme, recent files,
        # always trust); tests and drivers leave it alone (io/settings.py)
        self.use_settings = use_settings
        self.theme_choice = theme.name
        self.selected = ""
        self.workspace = "geometry"
        self.last_crash_report = None
        self.remote = None             # the remote control server (PLAN.md 3.7), when on
        self.remote_wanted = False     # started with the session when it is wanted
        self._owns_session = False
        self._unsubscribe = None
        self._last_crash_text = None
        self._pending_sites = None     # (system, positions) to select once it is built
        self.plots = {}                # calculation id -> PlotView (a tab or a window)
        self.overlays = {}             # calculation id -> [(other calculation, mode)] drawn over it
        self.plot_windows = {}         # calculation id -> ResultWindow of a detached view
        self.canvas_view = "structure"
        self.field_preview = None      # (entry, parameter) the field view draws
        self.auto_rerun = False
        self.run_at_once = False       # the setting (io/settings.py) in the interactive program
        self._pick_menu = None         # the pick menu shown last (kept alive while it is open)
        self._auto_keys = {}           # calculation id -> key it was last re-run for
        self._auto_jobs = set()        # ids of the jobs the auto re-run started

        # the central column is in the window before what goes in it is made, so that each
        # part is parented into the window once (with the application's style sheet every
        # new parent restyles the whole subtree again: about 15 ms at start, test_startup)
        central = QWidget()
        central.setObjectName("central")
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.error_bar = MessageBar("errorBar")
        self.recovery_bar = MessageBar("recoveryBar")
        self.cost_bar = MessageBar("costBar")
        self.trust_bar = MessageBar("trustBar")
        column.addWidget(self.recovery_bar)
        column.addWidget(self.trust_bar)
        column.addWidget(self.error_bar)
        column.addWidget(self.cost_bar)
        self.central_stack = QStackedWidget()
        self.central_stack.setObjectName("centralStack")
        column.addWidget(self.central_stack, 1)
        self.setCentralWidget(central)

        self.outliner = Outliner()
        self.outliner.selected.connect(self.select)
        self.outliner.command.connect(self._outliner_command)
        self.outliner.add_requested.connect(self._section_add)
        self.properties = PropertiesPanel(self._do)
        self.properties.preview.connect(self._preview_requested)
        self.properties.help_requested.connect(lambda item: self.show_help(item))
        self.properties.regions_requested.connect(self.open_regions_menu)
        self.help_panel = HelpPanel()
        # the start page in the viewport's place while the document has no system (PLAN.md
        # phase 8, package P1), below the bars, so that the recovery bar shows over it
        self.start_page = StartPage({kind: label
                                     for kind, (_, _, label) in CLASSICAL_STARTS.items()},
                                    self.central_stack)
        self.central_stack.addWidget(self.start_page)
        self.viewport = QTabWidget()
        self.viewport.setObjectName("viewport")
        self.viewport.setTabsClosable(True)
        self.central_stack.addWidget(self.viewport)
        self.structure = StructureView()
        self.structure.selection_changed.connect(self._selection_changed)
        self.structure.view_chosen.connect(self.set_canvas_view)
        self.structure.projection_chosen.connect(self.set_projection)
        self.structure.paint_stroke.connect(self._paint_stroke)
        self.structure.navigation_changed.connect(self._navigation_changed)
        self.viewport.addTab(self.structure, "Structure")
        self.kspace_view = KSpaceView()
        self.kspace_view.path_edited.connect(
            lambda calc, vertices: self._do("set_param", entry=calc, name="kpath",
                                            value=vertices))
        self.kspace_view.calculation_chosen.connect(self._kpath_calculation_chosen)
        self.kspace_view.kpoint_picked.connect(self._kpoint_picked)
        self.kpath_calc = None         # the calculation whose k-path the k-space tab edits
        self.viewport.addTab(self.kspace_view, "k-space")
        for tab in (STRUCTURE_TAB, KSPACE_TAB):
            for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
                self.viewport.tabBar().setTabButton(tab, side, None)    # always there
        self.viewport.tabCloseRequested.connect(self._close_tab)
        self.start_page.lattice_chosen.connect(
            lambda kind: self.new_system(kind) if self.session is not None else None)
        self.start_page.classical_chosen.connect(
            lambda kind: self.new_classical_system(kind) if self.session is not None else None)
        self.start_page.preset_chosen.connect(
            lambda name: self.open_document(name) if self.session is not None else None)
        self.start_page.recent_chosen.connect(
            lambda path: self.open_document(path) if self.session is not None else None)
        self.start_page.open_requested.connect(
            lambda: self.open_dialog() if self.session is not None else None)
        self.start_page.guide_requested.connect(
            lambda: self._window_act("help", self.help, guide="guiqula"))
        self.start_page.set_recent(settings.load()["recent"] if use_settings else [])

        self.jobs = JobPanel()
        self.jobs.cancel_requested.connect(self.cancel_job)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.console = ConsoleWidget()
        self.console.run_requested.connect(self.run_console)
        self.console.interrupt_requested.connect(self.interrupt_console)
        self._console_lines = {}       # console job id -> log lines written so far
        self.sliders = []              # [{entry, param, component, min, max}] (13.10)
        self.sliders_panel = SlidersPanel()
        self.sliders_panel.add_requested.connect(
            lambda entry, param, component, low, high: self._act(
                "slider", entry=entry, param=param, component=component, minimum=low,
                maximum=high))
        self.sliders_panel.moved.connect(self._slider_moved)
        self.sliders_panel.removed.connect(lambda index: self._act("remove_slider",
                                                                   index=index))
        # the panels (PLAN.md phase 8, package P5): the outliner on the left; on the right
        # Properties alone at the top and, below it, Help, Sliders and Jobs tabbed, so that
        # the help never hides the form it explains; Log and Console at the bottom, hidden
        # until the status bar's Log toggle (or View > Panels) shows them
        self.help_panel.browser.setPlaceholderText("Select an entry and press F1 for its help.")
        self.jobs.job_added.connect(self._job_added)
        self.docks = {}
        for title, widget, name in (("Outliner", self.outliner, "outlinerDock"),
                                    ("Properties", self.properties, "propertiesDock"),
                                    ("Help", self.help_panel, "helpDock"),
                                    ("Sliders", self.sliders_panel, "slidersDock"),
                                    ("Jobs", self.jobs, "jobsDock"),
                                    ("Log", self.log, "logDock"),
                                    ("Console", self.console, "consoleDock")):
            self.docks[name] = self._dock(title, widget, name, DOCK_AREAS[name])
        self._arrange_docks()

        self._build_toolbars()
        self._build_menus()
        self.statusBar().setObjectName("statusBar")
        self.status_label = QLabel("no document")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setToolTip(vendoring.describe())
        self.autosave_label = QLabel("")
        self.autosave_label.setObjectName("autosaveLabel")
        self.statusBar().addWidget(self.status_label)
        # the last message, after the summary (the Log is hidden by default), and at the
        # right the toggle of the bottom area (PLAN.md phase 8, package P5)
        self.status_message = StatusMessage("statusMessage")
        self.statusBar().addWidget(self.status_message, 1)
        self.remote_label = QLabel("")
        self.remote_label.setObjectName("remoteLabel")
        self.statusBar().addPermanentWidget(self.remote_label)
        self.statusBar().addPermanentWidget(self.autosave_label)
        self.log_toggle = QToolButton()
        self.log_toggle.setObjectName("logToggle")
        self.log_toggle.setText("Log")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setToolTip("show or hide the bottom area: the Log, every message so "
                                   "far, and the Python console (View > Panels)")
        self.log_toggle.clicked.connect(lambda checked: self._window_act("log", self.set_log,
                                                                         enabled=checked))
        self.log_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.statusBar().addPermanentWidget(self.log_toggle)
        for name in BOTTOM_DOCKS:
            self.docks[name].toggleViewAction().toggled.connect(self._sync_log_toggle)

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
        self.theme_actions[self.theme_choice].setChecked(True)
        self.text_actions[theme.text_size].setChecked(True)
        self.ui_text_actions[theme.ui_text].setChecked(True)
        if use_settings:
            stored = settings.load()
            self.set_ui_text(stored["ui_text"], remember=False)
            self._restore_layout(stored["layout"])
            self.set_theme(stored["theme"])
            self.set_plot_text(stored["plot_text"], remember=False)
            self.always_trust_action.setChecked(stored["always_trust"])
            self.set_remote(stored["remote"], remember=False)
            self.set_run_at_once(stored["run_at_once"], remember=False)
            renderer = stored["renderer_3d"]
            if renderer == "pyvista" and not pyvista_view.available() \
                    and not settings.chosen("renderer_3d"):
                renderer = "matplotlib"          # the default, and pyvista is not installed
            try:
                self.set_renderer_3d(renderer, remember=False)
            except ValueError as error:          # pyvista chosen, and gone since
                self.message(f"3D drawing with matplotlib: {error}", error=True)
        # the icons of the controls (PLAN.md phase 8, package P8), set at the window's first
        # show and after every change of theme; each bar, view and row sets its own the same
        # way when it is first shown, so that what is out of sight at start costs nothing
        icons.follow(self, self._set_icons)

    def _set_icons(self):
        """The icons of the window's own controls (icons.follow): the first
        toolbar row, the Log toggle and the viewport's Structure and k-space
        tabs; the menus' are set as each opens first (_set_menu_icons)."""
        for button, name in ((self.new_system_button, "new"), (self.add_button, "add"),
                             (self.run_button, "run"), (self.cancel_button, "cancel"),
                             (self.auto_rerun_button, "follow"), (self.log_toggle, "log")):
            button.setIcon(icons.icon(name))
            button.setIconSize(icons.size())
        self.viewport.setTabIcon(STRUCTURE_TAB, icons.icon("structure"))
        self.viewport.setTabIcon(KSPACE_TAB, icons.icon("kspace"))

    def _set_menu_icons(self):
        """The icons of the menus' entries (icons.follow of each menu: at its
        first opening, and after every change of theme)."""
        for action, name in self._menu_icons.items():
            action.setIcon(icons.icon(name))

    # ---- construction helpers
    def _dock(self, title, widget, name, area):
        """A panel: it keeps its title and its close button, and can be
        moved to another side, but never floats (a floating dock cannot be
        moved on Wayland, decision 88)."""
        dock = Dock(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                         | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(area, dock)
        return dock

    def _arrange_docks(self):
        """The default arrangement of the panels: every dock put back on its
        side, Properties above the Help, Sliders and Jobs tabs (Help in
        front) at 60 and 40 percent of the column, the bottom area hidden.
        The window's size is left as it is."""
        docks = self.docks
        for name, dock in docks.items():
            self.addDockWidget(DOCK_AREAS[name], dock)        # takes it back from elsewhere
        self.splitDockWidget(docks["propertiesDock"], docks["helpDock"], Qt.Orientation.Vertical)
        self.tabifyDockWidget(docks["helpDock"], docks["slidersDock"])
        self.tabifyDockWidget(docks["slidersDock"], docks["jobsDock"])
        self.tabifyDockWidget(docks["logDock"], docks["consoleDock"])
        for name, dock in docks.items():
            dock.setVisible(name not in BOTTOM_DOCKS)
        docks["helpDock"].raise_()
        docks["logDock"].raise_()
        self.resizeDocks([docks["outlinerDock"], docks["propertiesDock"]], [320, 340],
                         Qt.Orientation.Horizontal)
        self.resizeDocks([docks["propertiesDock"], docks["helpDock"]],
                         [int(100 * PROPERTIES_SHARE), int(100 * (1 - PROPERTIES_SHARE))],
                         Qt.Orientation.Vertical)

    def _menu_button(self, bar, text, name, menu, tooltip, shortcut=None):
        """A tool button with a menu, which a click opens with popup() (the
        caller connects clicked, ui/palette.py's MenuButton)."""
        button = MenuButton(text, menu)
        button.setObjectName(name)
        self._tip(button, tooltip, shortcut)
        bar.addWidget(button)
        return button

    @staticmethod
    def _tip(widget, text, shortcut=None):
        """A tooltip, with the keys of a shortcut of the table."""
        widget.setToolTip(f"{text} ({shortcuts.text(shortcut)})" if shortcut else text)
        return widget

    def _toolbar(self, title, name):
        bar = QToolBar(title)
        bar.setObjectName(name)
        bar.setMovable(False)
        self.addToolBar(bar)
        return bar

    def _build_toolbars(self):
        """The first row: the workspace tabs, New system and Add (the Add
        menus of ui/palette.py, which the outliner's "+" open too), then the
        run controls (PLAN.md phase 8, package P2). The selection tools are
        on the structure canvas's bar (package P3), and the window connects
        them here."""
        bar = self._toolbar("Workspace", "workspaceToolbar")
        self.workspace_tabs = QTabBar()
        self.workspace_tabs.setObjectName("workspaceTabs")
        for i, name in enumerate(WORKSPACES):
            self.workspace_tabs.addTab(name.capitalize())
            self.workspace_tabs.setTabToolTip(i, {
                "geometry": "the lattice, the geometry ops, regions and the site selection",
                "hamiltonian": "the terms (or a classical model) and the mean field",
                "calculate": "the calculations and their results"}[name]
                + f"; selecting an entry shows its workspace "
                  f"({shortcuts.text('workspace_' + name)})")
        self.workspace_tabs.currentChanged.connect(lambda i: self.set_workspace(WORKSPACES[i]))
        bar.addWidget(self.workspace_tabs)
        self.palette_menus = {}
        self._opening = None           # the Add menu open_add_menu is showing
        for family in PALETTE_FAMILIES:
            menu = PaletteMenu(family, self)
            menu.aboutToShow.connect(lambda m=menu: self._palette_shown(m))
            menu.chosen.connect(lambda kind, m=menu: self._palette_chosen(m, kind))
            menu.not_found.connect(lambda text, f=family: self.message(
                f"no {f.replace('_', ' ')} matches {text!r}", error=True))
            self.palette_menus[family] = menu
        for kind, (lattice, n, label) in CLASSICAL_STARTS.items():
            self.palette_menus["lattice"].add_extra(
                "Classical systems", label, f"newClassical_{kind}",
                f"{label.lower()} on a {n}x{n} supercell of the "
                f"{registry.get('lattice', lattice).label.lower()} (decision 13.5)",
                lambda checked=False, k=kind: self.new_classical_system(k))
        self.palette_menus["term"].add_extra(
            "Interactions", "Mean field (interactions)", "addMeanfield",
            "interactions, the Hubbard U and the V and J between neighbours, solved "
            "self-consistently after the terms: turns on the mean-field block of the system and "
            "selects its row",
            lambda: self.add_meanfield(self.palette_menus["term"].system), kinds=("quantum",))
        bar.addSeparator()
        self.new_system_button = self._menu_button(
            bar, "New system", "newSystemButton", self.palette_menus["lattice"],
            "a new system: a quantum one on a lattice, or classical spins, a lattice gas or an "
            "Ising model (a document can hold several)")
        self.new_system_button.clicked.connect(lambda: self.open_add_menu("systems"))
        self.add_button = self._menu_button(bar, "Add", "addButton",
                                            self.palette_menus["geometry_op"],
                                            ADD_TIPS["geometry"], "find")
        self.add_button.clicked.connect(lambda: self.open_add_menu())
        self.regions_menu = QMenu(self)
        self.regions_menu.setObjectName("regionsMenu")
        self.regions_menu.setToolTipsVisible(True)
        self.regions_system = None     # the system the Regions menu adds to
        action = self.regions_menu.addAction("Region by expression")
        action.setObjectName("addRegion_expression")
        action.setToolTip("the sites where an expression of the position holds (x > 0 to "
                          "begin with, edited in its form)")
        action.triggered.connect(lambda: self.add_region(system=self.regions_system))
        self.region_selection_action = self.regions_menu.addAction("Region from selection")
        self.region_selection_action.setObjectName("addRegion_selection")
        self.region_selection_action.setToolTip("a region of the sites selected on the canvas")
        self.region_selection_action.triggered.connect(
            lambda: self._act("region_from_selection"))

        # Run acts on the calculation selected in the outliner, else the one whose tab is
        # shown, else the first: no third place to choose one (PLAN.md phase 8, package P4)
        run = self._toolbar("Run", "runToolbar")
        self.viewport.currentChanged.connect(self._calculation_chosen)
        self.viewport.tabBar().tabBarClicked.connect(
            lambda index: self._calculation_chosen(index, clicked=True))
        self.run_menu = QMenu(self)
        self.run_menu.setObjectName("runMenu")
        self.run_menu.setToolTipsVisible(True)
        self.run_menu.aboutToShow.connect(self._fill_run_menu)
        self.run_stale_action = QAction("Run every stale result", self)
        self.run_stale_action.setObjectName("runStaleAction")
        self.run_stale_action.setToolTip("run again every result the model has changed under "
                                         "since it was computed (a slow one after a question)")
        self.run_stale_action.triggered.connect(lambda: self._window_act("run_stale",
                                                                         self.run_stale))
        self.run_button = QToolButton()
        self.run_button.setText("Run")
        self.run_button.setObjectName("runButton")
        self.run_button.setMenu(self.run_menu)
        self.run_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.run_button.clicked.connect(self.run_selected)
        self._tip(self.run_button, "run the selected calculation in a worker; the arrow "
                                   "runs another one, or every stale result", "run")
        run.addWidget(self.run_button)
        self.cancel_button = QToolButton()
        self.cancel_button.setText("Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self.cancel_selected)
        self._tip(self.cancel_button, "Cancel: stop its job (the worker is restarted)", "cancel")
        run.addWidget(self.cancel_button)
        self.auto_rerun_button = QToolButton()
        self.auto_rerun_button.setText("Follow")
        self.auto_rerun_button.setObjectName("autoRerunButton")
        self.auto_rerun_button.setCheckable(True)
        self.auto_rerun_button.setToolTip(
            f"Follow: cheap results are computed again as the model changes: a stale result that "
            f"takes less than {AUTO_RERUN_SECONDS:g} s runs again by itself (Run > Re-run "
            f"cheap results automatically)")
        self.auto_rerun_button.clicked.connect(lambda checked: self._window_act(
            "auto_rerun", self.set_auto_rerun, enabled=checked))
        run.addWidget(self.auto_rerun_button)
        # the icons (PLAN.md phase 8, package P8, _set_icons): New system, Add and Run keep
        # their text beside, Cancel and Follow show the icon alone, their name in the tooltip
        for button in (self.new_system_button, self.add_button, self.run_button):
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # the selection tools sit on the canvas they act on, in its bar (PLAN.md phase 8,
        # package P3); the window acts on what they ask
        structure = self.structure
        self.tool_buttons = structure.tool_buttons
        self.region_button = structure.region_button
        self.calculate_button = structure.calculate_button
        self.remove_button = structure.remove_button
        structure.tool_chosen.connect(self.set_tool)
        structure.select_requested.connect(lambda args: self._act("select_sites", **args))
        structure.region_requested.connect(lambda: self._act("region_from_selection"))
        structure.calculate_requested.connect(self._selection_menu)
        structure.remove_requested.connect(lambda: self._act("remove_selected"))

    # ---- the Add menus (PLAN.md phase 8, package P2)
    def palette_menu(self, family, system=None):
        """The Add menu of a family (lattice, geometry_op, term,
        calculation) with its entries made for the kind of a system (the
        current one when left out), which an entry chosen in it is added
        to (the current one at that moment when left out)."""
        menu = self.palette_menus[family]
        menu.system = system
        target = system or self.current_system()
        kind = "quantum"                   # New system offers the lattices of quantum systems
        if family != "lattice" and target is not None and self.session is not None:
            kind = self.session.document.system(target).kind
        return menu.prepare(kind)

    def _palette_shown(self, menu):
        """A menu shown by Qt rather than by open_add_menu (a press held on
        its button): it lists for the current system, and adds to it."""
        if self._opening is not menu:
            self.palette_menu(menu.family)

    def _palette_chosen(self, menu, kind):
        """An entry chosen in an Add menu: added to the menu's system (the
        current one when it names none, or no longer exists) and selected."""
        if menu.family == "lattice":
            return self.new_system(kind)
        system = menu.system if menu.system and self._exists(menu.system) \
            else self._target_system()
        if system is None:
            return None
        command = {"geometry_op": "add_geometry_op", "term": "add_term",
                   "calculation": "add_calculation"}[menu.family]
        return self._do_and_select(command, system=system, kind=kind)

    def _add_target(self, section):
        """(menu, system) of an Add menu (open_add_menu's section)."""
        if not section:
            system = self.current_system()
            if system is None:
                return self.palette_menu("lattice"), None
            return self.palette_menu(WORKSPACE_FAMILIES[self.workspace], system), system
        if section == "systems":
            return self.palette_menu("lattice"), None
        if section == "calculations":
            system = self.current_system()
            if system is None:
                raise ValueError("add a system first (New system)")
            return self.palette_menu("calculation", system), system
        system, _, part = section.partition("/")
        if self.session is None or not any(s.id == system for s in
                                           self.session.document.systems):
            raise ValueError(f"no system {system!r} in the document")
        kind = self.session.document.system(system).kind
        if part == "geometry":
            return self.palette_menu("geometry_op", system), system
        if part == "regions":
            return self.regions_menu, system
        if part in ("hamiltonian", "model"):
            if (part == "model") == (kind == "quantum"):
                where = "model" if kind != "quantum" else "hamiltonian"
                raise ValueError(f"{system} is a {kind.replace('_', ' ')} system: its terms "
                                 f"are under {system}/{where}")
            return self.palette_menu("term", system), system
        raise ValueError(f"unknown section {section!r}; sections: <system>/geometry, "
                         f"<system>/regions, <system>/hamiltonian, <system>/model, "
                         f"calculations, systems")

    def open_add_menu(self, section=None, search="", position=None, anchor=None):
        """Open an Add menu with its search line focused (popup: it returns
        at once): the "+" of an outliner section, the toolbar's Add and New
        system, Ctrl+F. section: <system>/geometry, <system>/regions,
        <system>/hamiltonian, <system>/model, calculations, or systems (New
        system); left out, the family of the workspace on the current system,
        or New system while the document has none. search is typed into it.
        It opens below the anchor (the button clicked; the section's "+" or
        the toolbar button when left out) or at a global position [x, y].
        Returns what it lists: the menu, the system it adds to, the
        objectNames of its entries (best first after a search) and the best
        match, which Enter adds."""
        menu, system = self._add_target(section)
        if anchor is None:
            anchor = self.outliner.add_button(section) if section else None
            if anchor is None or not anchor.isVisible():
                anchor = self.new_system_button if menu is self.palette_menus["lattice"] \
                    else self.add_button
        if position is None:
            position = anchor.mapToGlobal(anchor.rect().bottomLeft())
        elif not isinstance(position, QPoint):
            position = QPoint(int(position[0]), int(position[1]))
        if menu is self.regions_menu:
            self.regions_system = system
            by_selection = self.region_selection_action
            selected = self.structure.system_id == system and len(self.structure.selected()) > 0
            by_selection.setEnabled(selected)
            by_selection.setToolTip(
                "a region of the sites selected on the canvas" if selected else
                f"select sites of {system} on the canvas first (Pick, Box, Lasso or Select)")
            menu.popup(position)
            return {"menu": menu.objectName(), "system": system, "best": None,
                    "entries": [a.objectName() for a in menu.actions() if a.isEnabled()]}
        self._opening = menu
        try:
            menu.show_at(position, search)
        finally:
            self._opening = None
        listed = menu.filter()
        return {"menu": menu.objectName(), "system": system, "entries": listed,
                "best": menu.best.objectName() if menu.best is not None else None}

    def open_regions_menu(self, system, position=None):
        """The Regions menu of a system (its "+" in the outliner, and the
        region link of a term's form): Region by expression, and Region from
        selection while sites of that system are selected. position: global,
        else below the "+"."""
        return self.open_add_menu(f"{system}/regions", position=position)

    def _section_add(self, path, button):
        """A "+" of the outliner was clicked."""
        try:
            self.open_add_menu(path, anchor=button)
        except ValueError as error:
            self.message(str(error), error=True)

    def _update_palettes(self):
        """Follow the current system: the Hamiltonian tab reads Model for a
        classical one, and Add waits for a first system."""
        system = self.current_system()
        kind = self.session.document.system(system).kind if system else "quantum"
        self.workspace_tabs.setTabText(1, "Hamiltonian" if kind == "quantum" else "Model")
        self.add_button.setEnabled(system is not None)

    # ---- the run controls of the first row (their behaviour is package P4's)
    def _stale_results(self):
        """The calculations whose result is stale, in the outliner's order."""
        if self.session is None:
            return []
        return [c.id for c in self.session.document.calculations
                if c.id in self.session.results and self.session.is_stale(c.id)]

    def _fill_run_menu(self):
        """The Run button's menu: the other calculations, then every stale
        result."""
        menu = self.run_menu
        menu.clear()
        chosen = self.selected_calculation()
        calculations = self.session.document.calculations if self.session is not None else []
        for calc in calculations:
            if calc.id == chosen:
                continue
            action = menu.addAction(icons.icon("run"), f"Run {calc.id} · {calc.kind}")
            action.setObjectName(f"runCalc_{calc.id}")
            action.setToolTip(f"{self._calculation_label(calc.id)} on {calc.system}, through "
                              f"the cost guard")
            action.triggered.connect(lambda checked=False, c=calc.id: self.run_guarded(c))
        if menu.actions():
            menu.addSeparator()
        self.run_stale_action.setEnabled(bool(self._stale_results()))
        self.run_stale_action.setIcon(icons.icon("run_stale"))     # in the active theme
        menu.addAction(self.run_stale_action)
        return [a.objectName() for a in menu.actions() if a.objectName()]

    def run_stale(self):
        """Run every calculation whose result is stale (the Run button's
        menu): the cheap ones at once, and those the cost guard would ask
        about after one question for all of them, in the cost bar. Returns
        the ids it ran or asked about."""
        if self.session is None:
            return []
        stale = self._stale_results()
        slow = []
        for calc in stale:
            estimate = self.session.estimate(calc)
            if estimate is not None and estimate["seconds"] > cost.SLOW:
                slow.append((calc, estimate["seconds"]))
            else:
                self._act("run_calculation", calculation=calc)
        if len(slow) == 1:
            self.run_guarded(slow[0][0])
        elif slow:
            names = [calc for calc, _ in slow]
            self.cost_bar.show_message(
                f"{', '.join(names[:-1])} and {names[-1]} will take "
                f"{cost.describe(sum(s for _, s in slow))} in all. Run them anyway?",
                [("Run anyway", lambda: [self.run_guarded(c, confirmed=True) for c in names],
                  "runAnywayButton"),
                 ("Cancel", self.cost_bar.dismiss, "costCancelButton")])
        return stale

    def _action(self, menu, text, slot, shortcut=None, name=None):
        """A menu entry; shortcut: an id of the shortcut table (ui/shortcuts.py)."""
        action = QAction(text, self)
        if shortcut:
            shortcuts.bind(action, shortcut)
        if name:
            action.setObjectName(name)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _widget_action(self, widget, text, slot, shortcut):
        """A shortcut that works while a widget has the focus (the canvas)."""
        action = shortcuts.bind(QAction(text, widget), shortcut)
        action.triggered.connect(slot)
        widget.addAction(action)
        return action

    def _build_menus(self):
        self._menu_icons = {}          # QAction -> the name of its icon (_set_menu_icons)
        file_menu = self.menuBar().addMenu("&File")
        self._menu_icons[self._action(file_menu, "&New", self.new_document, "new")] = "new"
        self._menu_icons[self._action(file_menu, "&Open...", self.open_dialog, "open")] = "open"
        self.recent_menu = file_menu.addMenu("Open &recent")
        self.recent_menu.setObjectName("recentMenu")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        self._action(file_menu, "Presets &gallery...", self.show_gallery, "gallery",
                     "galleryAction")
        presets = file_menu.addMenu("Open &preset")
        for name in project.presets():
            self._action(presets, name, lambda checked=False, n=name: self.open_document(n))
        self._menu_icons[self._action(file_menu, "&Save", self.save, "save")] = "save"
        self._action(file_menu, "Save &as...", self.save_as, "save_as")
        self._menu_icons[self._action(file_menu, "&Export pyqula script...", self.export_script,
                                      "export_script")] = "export"
        self._action(file_menu, "Export &figure, data and script...",
                     lambda: self.export_bundle_dialog(self.selected_calculation()),
                     "export_bundle", "exportBundleAction")
        self._action(file_menu, "&Recover unsaved work...", self.offer_recovery,
                     name="recoverAction")
        self.trust_action = self._action(
            file_menu, "&Trust the Python code", lambda: self._act(
                "trust", enabled=self.trust_action.isChecked()), name="trustAction")
        self.trust_action.setCheckable(True)
        self.trust_action.setToolTip("let the Python nodes of this document run in the "
                                     "worker (a file with Python code is not trusted when "
                                     "it is opened)")
        self.always_trust_action = self._action(
            file_menu, "Always trust Python code in &files",
            lambda: self.set_always_trust(self.always_trust_action.isChecked()),
            name="alwaysTrustAction")
        self.always_trust_action.setCheckable(True)
        self.always_trust_action.setToolTip("open every file with its Python nodes allowed to "
                                            "run (PLAN.md 13.7); off by default")
        self.remote_action = self._action(
            file_menu, "Allow re&mote control", lambda: self.set_remote(
                self.remote_action.isChecked()), name="remoteAction")
        self.remote_action.setCheckable(True)
        self.remote_action.setToolTip("let other programs on this computer drive this window "
                                      "through a localhost socket protected by a token (the "
                                      "Claude add-on: guiqula mcp); off by default")
        file_menu.addSeparator()
        self._action(file_menu, "&Quit", self.close, "quit")
        file_menu.setToolTipsVisible(True)
        edit = self.menuBar().addMenu("&Edit")
        self.undo_action = self._action(edit, "&Undo", lambda: self.undo(), "undo", "undoAction")
        self.redo_action = self._action(edit, "&Redo", lambda: self.redo(), "redo", "redoAction")
        self._menu_icons.update({self.undo_action: "undo", self.redo_action: "redo"})
        self.history_menu = edit.addMenu("Undo &history")
        self.history_menu.setObjectName("historyMenu")
        self.history_menu.aboutToShow.connect(self._fill_history)
        edit.addSeparator()
        self.unlock_action = self._action(edit, "Un&lock everything", lambda: self._do("unlock"),
                                          name="unlockAction")
        self.unlock_action.setToolTip("lift every lock of the document (a teaching preset "
                                      "locks what its exercise keeps fixed)")
        edit.setToolTipsVisible(True)
        view = self.menuBar().addMenu("&View")
        for name in WORKSPACES:
            self._action(view, f"{name.capitalize()} workspace",
                         lambda checked=False, n=name: self.set_workspace(n), f"workspace_{name}")
        self._action(view, "&Structure tab", lambda: self.viewport.setCurrentIndex(STRUCTURE_TAB),
                     "structure_tab")
        self._action(view, "&Close result tab", self.close_current_result, "close_result")
        self._menu_icons[self._action(view, "&Find in the Add menu", self.focus_search, "find")] = \
            "search"
        view.addSeparator()
        themes = view.addMenu("&Theme")
        self._menu_icons[themes.menuAction()] = "theme"
        themes.setObjectName("themeMenu")
        group = QActionGroup(self)
        self.theme_actions = {}
        for choice, text in (("system", "Follow the &desktop"), ("light", "&Light"),
                             ("dark", "&Dark")):
            action = self._action(themes, text, lambda checked=False, c=choice:
                                  self._act("theme", name=c), name=f"theme_{choice}")
            action.setCheckable(True)
            group.addAction(action)
            self.theme_actions[choice] = action
        sizes = view.addMenu("Plot &text")
        sizes.setObjectName("plotTextMenu")
        sizes.setToolTipsVisible(True)
        group = QActionGroup(self)
        self.text_actions = {}
        for choice, text in (("small", "&Small"), ("normal", "&Normal"), ("large", "&Large")):
            action = self._action(sizes, text, lambda checked=False, c=choice:
                                  self._act("plot_text", name=c), name=f"plot_text_{choice}")
            action.setCheckable(True)
            action.setToolTip(f"the labels, ticks and titles of every drawing at "
                              f"{theme.FONT_POINTS[choice]} points (the axis labels a fifth "
                              f"larger)")
            group.addAction(action)
            self.text_actions[choice] = action
        interface = view.addMenu("&Interface text")
        interface.setObjectName("uiTextMenu")
        interface.setToolTipsVisible(True)
        group = QActionGroup(self)
        self.ui_text_actions = {}
        normal, large = theme.UI_POINTS["normal"], theme.UI_POINTS["large"]
        for choice, text, tip in (
                ("normal", "&Normal", f"the menus, the panels and the forms at the desktop's "
                                      f"size, at least {normal} points"),
                ("large", "&Large", f"the menus, the panels and the forms {large - normal} "
                                    f"points larger, for a projector ({large} points on Qt's "
                                    f"default font)")):
            action = self._action(interface, text, lambda checked=False, c=choice:
                                  self._window_act("ui_text", self.set_ui_text, name=c),
                                  name=f"ui_text_{choice}")
            action.setCheckable(True)
            action.setToolTip(tip)
            group.addAction(action)
            self.ui_text_actions[choice] = action
        drawing = view.addMenu("3D &drawing")
        drawing.setObjectName("renderer3dMenu")
        group = QActionGroup(self)
        self.renderer_actions = {}
        for choice, text, tip in (
                ("matplotlib", "&matplotlib", "matplotlib's mplot3d: drag to turn the drawing"),
                ("pyvista", "&pyvista", "pyvista, moved as in Blender: the middle button "
                                        "orbits, with shift it pans, with ctrl it zooms, the "
                                        "wheel zooms, the numpad gives the views")):
            action = self._action(drawing, text, lambda checked=False, c=choice:
                                  self._act("renderer_3d", name=c), name=f"renderer_{choice}")
            action.setCheckable(True)
            action.setToolTip(tip)
            group.addAction(action)
            self.renderer_actions[choice] = action
        self.renderer_actions["matplotlib"].setChecked(True)
        if not pyvista_view.available():
            self.renderer_actions["pyvista"].setEnabled(False)
            self.renderer_actions["pyvista"].setToolTip(pyvista_view.unavailable_reason())
        drawing.setToolTipsVisible(True)
        view.addSeparator()
        panels = view.addMenu("&Panels")
        panels.setObjectName("panelsMenu")
        self._menu_icons[panels.menuAction()] = "panels"
        panels.setToolTipsVisible(True)
        for name, dock in self.docks.items():
            action = dock.toggleViewAction()
            action.setObjectName(f"panel_{name}")
            tip = PANEL_TIPS.get(name, "").format(help=shortcuts.text("help"))
            action.setToolTip(f"show or hide {dock.windowTitle()}" + (f": {tip}" if tip else ""))
            panels.addAction(action)
        reset = self._action(view, "&Reset layout", lambda: self._window_act(
            "reset_layout", self.reset_layout), name="resetLayoutAction")
        reset.setToolTip("the panels back where they start: Properties above Help, Sliders "
                         "and Jobs, the Log and the Console hidden (the window keeps its size)")
        view.setToolTipsVisible(True)
        run = self.menuBar().addMenu("&Run")
        self._menu_icons[self._action(run, "&Run calculation", self.run_selected, "run",
                                      "runAction")] = "run"
        self._menu_icons[self._action(run, "&Cancel", self.cancel_selected, "cancel",
                                      "cancelAction")] = "cancel"
        run.addSeparator()
        self.auto_rerun_action = self._action(
            run, "Re-run cheap results &automatically", lambda: self.set_auto_rerun(
                self.auto_rerun_action.isChecked()), name="autoRerunAction")
        # no icon here: a checkable entry with one loses its check box in the menu, and
        # its state would read only as a faint frame around the icon
        self.auto_rerun_action.setCheckable(True)
        self.auto_rerun_action.setToolTip(f"a stale result is computed again as soon as the "
                                          f"geometry is rebuilt, when it takes less than "
                                          f"{AUTO_RERUN_SECONDS:g} s")
        self.run_at_once_action = self._action(
            run, "Run calculations at &once", lambda: self._act(
                "run_at_once", enabled=self.run_at_once_action.isChecked()),
            name="runAtOnceAction")
        self.run_at_once_action.setCheckable(True)
        self.run_at_once_action.setToolTip("a calculation runs as soon as it is added or one of "
                                           "its parameters is set (its form, a pick on a plot, "
                                           "a command), through the cost guard; off, only Run "
                                           "(F5) runs it")
        run.setToolTipsVisible(True)
        help_menu = self.menuBar().addMenu("&Help")
        self._menu_icons[self._action(help_menu, "&Help on the selected entry",
                                      lambda: self.show_help(), "help", "helpAction")] = "help"
        for menu in (file_menu, edit, view, run, help_menu):
            icons.follow(menu, self._set_menu_icons)
        self._action(help_menu, "&pyqula user guide", lambda: self._act("help", guide="pyqula"),
                     name="pyqulaGuideAction")
        self._action(help_menu, "&guiqula user guide",
                     lambda: self._act("help", guide="guiqula"), name="guiqulaGuideAction")
        self._action(help_menu, "&Keyboard shortcuts", self.show_shortcuts, "shortcuts",
                     "shortcutsAction")
        self._action(help_menu, "P&lugins", lambda: self._act("help", guide="plugins"),
                     name="pluginsAction")
        self._action(help_menu, "&About", lambda: self.message(
            f"guiqula {guiqula.__version__}, {vendoring.describe()}"))
        self._action(help_menu, "Open &crash reports folder", lambda: self._open_folder(
            crashreport.reports_dir()))
        canvas = self.structure.canvas
        canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        actions = []
        for tool in structure_tools.TOOLS:
            actions.append(self._widget_action(canvas, f"{tool} tool", lambda checked=False,
                                               t=tool: self.set_tool(t), f"tool_{tool}"))
        for shortcut, args in (("select_all", {"all": True}), ("select_none", {"indices": []}),
                               ("select_invert", {"all": True, "mode": "toggle"})):
            actions.append(self._widget_action(
                canvas, shortcut.replace("_", " "), lambda checked=False, a=args:
                self._act("select_sites", **a), shortcut))
        actions.append(self._widget_action(canvas, "remove selected", lambda: self._act(
            "remove_selected") if self.structure.selected().size else None, "remove_selected"))
        actions.append(self._widget_action(canvas, "show everything", self.structure.fit,
                                           "fit"))
        self.structure.scene.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.structure.scene.canvas.addActions(actions)       # the same keys on pyvista's

    # ---- session
    def start_session(self, document=None, **options):
        """Create and attach a Session (starts the worker processes)."""
        from guiqula.session import Session
        options.setdefault("autosave", self.autosave)
        options.setdefault("always_trust", self.always_trust_action.isChecked())
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
        dispatcher.register_action("projection", lambda name: self.set_projection(name))
        dispatcher.register_action("overlay", self.overlay)
        dispatcher.register_action("paint", self.paint)
        dispatcher.register_action("slider", self.add_slider)
        dispatcher.register_action("set_slider", self.set_slider)
        dispatcher.register_action("remove_slider", self.remove_slider)
        dispatcher.register_action("theme", lambda name="system": self.set_theme(name))
        dispatcher.register_action("export_bundle", self.export_bundle)
        dispatcher.register_action("help", self.help)
        dispatcher.register_action("remote", lambda enabled=True: self.set_remote(
            enabled, remember=False))
        dispatcher.register_action("pick", self.pick)
        dispatcher.register_action("pick_to", self.pick_to)
        dispatcher.register_action("run_at_once", lambda enabled=True: self.set_run_at_once(
            enabled))
        dispatcher.register_action("renderer_3d", lambda name="matplotlib":
                                   self.set_renderer_3d(name))
        dispatcher.register_action("plot_text", lambda name="normal": self.set_plot_text(name))
        dispatcher.register_action("ui_text", lambda name="normal": self.set_ui_text(name))
        dispatcher.register_action("reset_layout", self.reset_layout)
        dispatcher.register_action("log", lambda enabled=True: self.set_log(enabled))
        dispatcher.register_action("panel", self.show_panel)
        dispatcher.register_action("view_3d", self.set_view_3d)
        dispatcher.register_action("add_menu", self.open_add_menu)
        dispatcher.register_action("run_stale", self.run_stale)
        dispatcher.register_action("start", self.start)
        dispatcher.register_action("run", self.run)
        self.help_panel.session = session
        session.view_state = self.view_state
        self.timer.start(POLL_MS)
        self._document_changed()
        self.apply_view_state(session.document.ui)
        self._update_trust()
        if self.remote_wanted and self.remote is None:
            self.set_remote(True, remember=False)
        self.offer_recovery(quiet=True)

    def closeEvent(self, event):
        if self.ask_before_close and self.session is not None and self.session.modified:
            if not self._confirm_discard():
                event.ignore()
                return
        if self.use_settings and self.isVisible():
            self._save_layout()           # the arrangement and the size, for the next start
        self.timer.stop()
        self.build_timer.stop()
        self._stop_remote()
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        if self.session is not None and self._owns_session:
            self.session.close()     # a clean close: the autosave is deleted
        super().closeEvent(event)

    def _confirm_discard(self, before="closing"):
        name = self.session.path.name if self.session.path else "this document"
        answer = QMessageBox.question(
            self, "Unsaved changes", f"Save the changes to {name} before {before}?",
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
        if self.remote is not None:
            try:
                self.remote.poll(0)
            except Exception:
                self.message("remote control failed and was turned off:\n"
                             + traceback.format_exc(), error=True)
                self._stop_remote()
                self._update_remote_label()
        self._update_autosave_label()

    def _on_session_event(self, kind, payload):
        if kind == "document":
            self._document_changed(payload)
        elif kind == "job":
            self._job_changed(payload)
        elif kind == "worker":
            self.jobs.update_workers(self.session.jobs.status())
            if payload.get("broken") and payload["pid"] is None:
                self.message(f"the {payload['role']} worker cannot start: {payload['broken']}",
                             error=True)
            elif payload["starts"] > 1 and payload["ready"] is False:
                self.message(f"{payload['role']} worker restarted (pid {payload['pid']})")

    def _document_changed(self, event=None):
        if event is not None and event["type"] == "action" and event.get("name") == "trust":
            event = None           # the plans change: refresh like after an edit
            self._update_trust()
        if event is not None and event["type"] == "action" and self.use_settings \
                and event.get("name") in ("load", "save") and event.get("result"):
            self._remember_file(event["result"])
            if self.central_stack.currentWidget() is self.start_page:   # saved while empty
                self.start_page.set_recent(settings.load()["recent"])
        if event is not None and self.remote is not None and event["type"] in ("action", "reset") \
                and event.get("name") in ("load", "save", "new", "recover", "reset"):
            self.remote.update(document=str(self.session.path) if self.session.path else None)
        if event is not None and event["type"] in ("undo", "redo"):
            self._follow_step(event)
        if event is not None and event["type"] == "action":
            # actions do not change the Document (new, load and recover reset it, and
            # region_from_selection and remove_selected announce their mutation): only
            # the title (save clears the asterisk) and the buttons can change
            self._update_title()
            self._update_actions()
            return
        if self.selected and not self._exists(self.selected):
            self.selected = ""
        self.show_start(not self.session.document.systems)   # before the canvas draws
        try:
            self._refresh_calculations()
            self.outliner.refresh(self.session)
            self.outliner.set_current(self.selected)
            if self.properties.session is None or self.properties.item_id != self.selected:
                self.properties.show_item(self.session, self.selected)
            else:
                self.properties.refresh()
            self._refresh_structure()
            self._refresh_results()
            self._prune_sliders()
            if self.sliders:
                self.sliders_panel.show_values([self._slider_value(sl) for sl in self.sliders])
            self._refresh_markers()
            self._update_status()
        finally:
            # a view that fails to draw must not stop the rebuild, Undo or the title
            self.build_timer.start(BUILD_DELAY_MS)
            self._update_actions()
            self._update_title()
        if event is not None and event["type"] == "reset":      # new, open, recover
            self.apply_view_state(self.session.document.ui)
            self._update_trust()
            for text in self.session.dropped_results:
                self.message(text, error=True)
        if event is not None and event["type"] == "mutation" \
                and not self.session.dispatcher.merging:        # a slider's drag: at its end
            calc = self._set_calculation(event)
            if calc is not None:
                self._ran_at_once(calc)

    def _update_title(self):
        path = self.session.path
        title = f"guiqula — {path.name}" if path else "guiqula"
        self.setWindowTitle(title + (" *" if self.session.modified else ""))

    def _exists(self, item_id):
        if item_id == "calculations":
            return True
        system = system_of(item_id)
        try:
            if system is not None:      # a row the outliner shows for a system of its kind
                return item_id in pseudo_ids(self.session.document.system(system))
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
            self.session.build_all(view=self.canvas_view == "hamiltonian")
        except Exception as error:
            self.message(f"could not ask for a build: {error}", error=True)

    def _job_changed(self, job):
        if job.kind == "console":
            self._console_job(job)
            return
        if job.kind == "build":
            system = job.payload["system"]
            if job.status == "done" and self.builds.get(system) is job.value:
                self.outliner.refresh(self.session)
                self.properties.refresh(values=False)
                if system == self.current_system():
                    self._refresh_structure()
                self._update_status()
                self._rerun_stale()
            elif job.status == "failed":
                self.message(f"{system} cannot be built: {job.error}", error=True)
                self.outliner.refresh(self.session)
                self._refresh_structure()
            elif job.status == "cancelled" and job.started:
                self.message(f"a build of {system} was stopped after "
                             f"{job.finished - job.started:.0f} s: a newer one was asked for "
                             f"(a Python node that never ends?)", error=True)
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
            self.properties.refresh(values=False)
            if job.status == "done" and job.kind == "run":
                if job.label in pipeline.result_references(self.session.document):
                    self.build_timer.start(0)      # the systems that read it change
                for calc, chosen in self.overlays.items():   # the views it is drawn over
                    if calc in self.plots and any(o[0] == job.label for o in chosen):
                        self._draw_result(calc)
                if job.value is not None and job.value.kind == "fermi_surface":
                    self._refresh_kspace()           # drawn under the zone
                if job.label in self.plots:
                    self._draw_result(job.label)
                if job.label == self.selected_calculation() and job.id not in self._auto_jobs:
                    self.show_result(job.label)      # an automatic re-run never steals the view
            if job.kind == "run":
                self._show_state(job.label)          # failed or cancelled: the tab and the row
            self._auto_jobs.discard(job.id)
        elif job.kind == "run":
            self.outliner.update_calculation(self.session, job.label, job)   # queued, progress
            self._show_state(job.label, job)         # the session may not hold it yet
        self.jobs.update_workers(self.session.jobs.status())
        self._update_run_controls()          # Cancel and the form's Run follow the job (P4)

    # ---- the Python console (decision 14.1)
    def run_console(self, code):
        """Run console code on the current system (the console widget)."""
        if self.session is None:
            return None
        system = self.current_system()
        self.console.set_system(system)
        try:
            job = self.session.console(code, system=system)
        except Exception as error:
            self.console.write(f"{type(error).__name__}: {error}", error=True)
            return None
        self.console.set_busy(True)
        return job.id

    def interrupt_console(self):
        self.session.interrupt_console()
        self.console.write("interrupted: the console starts afresh", error=True)

    def _console_job(self, job):
        """Write a console job's new output lines, and how it ended."""
        written = self._console_lines.get(job.id, 0)
        for line in job.log[written:]:
            self.console.write(line)
        self._console_lines[job.id] = len(job.log)
        if job.done:
            self._console_lines.pop(job.id, None)
            if job.status == "failed":
                self.console.write(f"the console stopped: {job.error}", error=True)
            busy = any(j.kind == "console" and not j.done
                       for j in self.session.jobs.jobs.values())
            self.console.set_busy(busy)

    # ---- selection and workspaces
    def select(self, entry=""):
        """Select an outliner item (an entry id, a system's pseudo id such
        as s1/base, or "" for nothing): properties, canvas overlays and the
        viewport tab follow, and so does the workspace: Geometry for a
        system, its lattice, an op or a region, Hamiltonian for a term, the
        mean field or a model, Calculate for a calculation (PLAN.md phase 8,
        package P2). Adding an entry selects it, so an add switches too."""
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
            self.select_calculation(entry)        # before the workspace, which shows it
        workspace = workspace_of(entry, family)
        if workspace is not None and workspace != self.workspace:
            self.set_workspace(workspace)         # only a change: a Field previewed stays
        if family == "calculation":
            self.show_result(entry)
        elif entry and entry != "calculations":
            self.viewport.setCurrentIndex(STRUCTURE_TAB)
        self._refresh_structure()
        self._update_status()
        self._update_palettes()
        self._help_follows(entry)
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
        self.add_button.setMenu(self.palette_menus[WORKSPACE_FAMILIES[name]])
        self._tip(self.add_button, ADD_TIPS[name], "find")
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
            if name == "hamiltonian" and any(not b.get("view") for b in self.builds.values()):
                self.build_timer.start(0)      # the builds so far left the view out
        return name

    def set_projection(self, name):
        """How the structure canvas and the results on the atoms draw the
        geometry: auto (3D when it is not flat), xy or 3d."""
        self.structure.set_projection(name)
        self._redraw_3d()
        return name

    def set_renderer_3d(self, name="matplotlib", remember=True):
        """What draws in 3D, the canvas and the results on the atoms:
        matplotlib (mplot3d) or pyvista (ui/pyvista_view.py); the
        interactive program keeps the choice in the settings file. Returns
        the choice."""
        if name == "pyvista" and not pyvista_view.available():
            reason = pyvista_view.unavailable_reason()
            self.renderer_actions["pyvista"].setEnabled(False)
            self.renderer_actions["pyvista"].setToolTip(reason)
            self.renderer_actions[self.structure.renderer_3d].setChecked(True)
            raise ValueError(reason)
        self.structure.set_renderer_3d(name)
        self.renderer_actions[name].setEnabled(True)
        self.renderer_actions[name].setChecked(True)
        if remember and self.use_settings:
            settings.put("renderer_3d", name)
        self._redraw_3d()
        return name

    def set_view_3d(self, name, calculation=None):
        """Move the pyvista view (SceneView.set_view: front, back, right,
        left, top, bottom, perspective, orthographic, flip, all, selected or
        reset) of the canvas, or of a result view when a calculation is
        given. Returns the name of the view shown."""
        if calculation:
            if calculation not in self.plots:
                raise ValueError(f"no result view of {calculation!r}")
            view = self.plots[calculation]
        else:
            view = self.structure
        if not view.in_scene:
            raise ValueError("nothing is drawn in 3D with pyvista there (View > 3D drawing, "
                             "and a geometry that is not flat or the 3D projection)")
        scene = view.scene
        scene.set_view(name)
        return scene.canvas.view.description()

    def _redraw_3d(self):
        """Draw again what the projection or the 3D drawing decide: the
        canvas, and the result views whose drawing they change (the others
        keep their zoom)."""
        def drawing(view):
            three_d = view.result is not None and plot_in_3d(view.result, view.projection)
            return three_d, view.renderer_3d if three_d else None
        changed = []
        for calc, view in self.plots.items():
            before = drawing(view)
            view.projection = self.structure.projection
            view.renderer_3d = self.structure.renderer_3d
            if drawing(view) != before:
                changed.append(calc)
        if self.session is None:
            return
        self._refresh_structure()
        for calc in changed:
            self._draw_result(calc, force=True)

    def preview_field(self, entry, param):
        """Draw a Field of a term (or of a mean field, <system>/meanfield) on
        the structure; the canvas switches to the field view."""
        self._field_entry(entry, param)          # raises for a wrong entry or parameter
        self.field_preview = (entry, param)
        self.viewport.setCurrentIndex(STRUCTURE_TAB)
        return self.set_canvas_view("field")

    def paint(self, value, indices=None, point=None, radius=0.6, entry=None, param=None,
              component=None, done=True):
        """Paint a Field (the one previewed, or entry and param): the sites
        at indices, or within radius of point [x, y], take value; the Field
        becomes a painted one. The strokes of one drag are one undo step
        (done ends it). Returns the number of sites painted."""
        if entry is None or param is None:
            if self.field_preview is None:
                raise ValueError("preview a Field first (Preview on the canvas, in the menu of "
                                 "its name in the form), or name entry and param")
            entry, param = self.field_preview
        system, spec, params, _ = self._field_entry(entry, param)
        declared = spec.param_map[param]
        vector = isinstance(declared, VectorFieldParam)
        if vector and component is None:
            raise ValueError(f"{param} is a vector: choose the component to paint (x, y, z)")
        if not getattr(declared, "native", True):
            raise ValueError(f"{param} is constant only: it cannot be painted")
        build = self.builds.get(system.id)
        if build is None:
            raise ValueError(f"{system.id} is not built yet")
        positions = np.asarray(build["positions"])
        if point is not None:
            indices = [int(i) for i in np.nonzero(np.hypot(
                positions[:, 0] - point[0], positions[:, 1] - point[1]) <= radius)[0]]
        indices = list(indices or [])
        if indices:
            current = params.get(param, declared.default)
            regions = {r.id: r.select for r in system.regions}
            if vector:
                new = list(current)
                new[component] = fields.paint(current[component], positions, indices, value,
                                              regions, self.session.result_refs())
            else:
                new = fields.paint(current, positions, indices, value, regions,
                                   self.session.result_refs())
            key = f"paint:{entry}:{param}:{component}"
            if entry.endswith("/meanfield"):
                self.session.do_merged(key, "set_meanfield", system=system.id,
                                       params={param: new})
            else:
                self.session.do_merged(key, "set_param", entry=entry, name=param, value=new)
        if done:
            self.session.dispatcher.end_merge()
        return len(indices)

    def _paint_stroke(self, indices, finished):
        """The canvas brush: indices are sites of the system drawn, which
        must be the one of the Field painted."""
        try:
            value, _, component = self.structure.brush()      # ValueError: not a number
            if self.field_preview is not None:
                system = self._field_entry(*self.field_preview)[0]
                if system.id != self.current_system():
                    raise ValueError(f"{self.field_preview[0]} belongs to {system.id}, not to "
                                     f"the system drawn")
            self.paint(value, indices=indices, component=component, done=finished)
        except (ValueError, KeyError, IndexError, registry.RegistryError) as error:
            self.message(f"paint: {error}", error=True)
            self.session.dispatcher.end_merge()

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
            if system.hamiltonian is None:
                raise ValueError(f"{system.id} is a classical system: it has no mean field")
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
            return {}, ("click into a Field of a term, or right-click its name in the form "
                        "and choose Preview on the canvas, to preview it here")
        entry, name = self.field_preview
        try:
            system, spec, params, region = self._field_entry(entry, name)
        except (ValueError, KeyError, registry.RegistryError) as error:
            return {}, str(error).strip("\"'")
        if system.id != system_id:
            return {}, f"{entry} belongs to {system.id}: select it to see or paint it"
        if not len(build["positions"]):
            return {}, f"{system_id} has no sites"
        param = spec.param_map[name]
        value = params.get(name, param.default)
        form = self.properties.form
        if form is not None and getattr(form, "item_id", None) == entry:
            live = form.live_value(name)
            value = live if live is not None else value
        positions = build["positions"]
        regions = {r.id: r.select for r in system.regions}
        results = self.session.result_refs()
        weight = np.ones(len(positions))
        label = f"{entry} {param.label}"
        try:
            if region is not None and param.native:
                weight = region_tools.evaluate_positions(region.select, positions).astype(float)
            if isinstance(param, VectorFieldParam):
                vectors = np.stack([fields.evaluate_positions(v, positions, regions, results)
                                    for v in value], axis=1) * weight[:, None]
                overlays = {"arrows": {"vectors": vectors, "label": label}}
                size = np.linalg.norm(vectors, axis=1)
                return overlays, f"{label}: |value| {structure_tools.value_range(size)}"
            values = fields.evaluate_positions(value, positions, regions, results) * weight
            text = f"{label}: {structure_tools.value_range(values)}"
        except Exception as error:
            return {}, f"{label}: {error}"
        return {"site_values": {"values": values, "label": label}}, text

    def _hamiltonian_overlay(self, build):
        view = build.get("hamiltonian")
        if build.get("kind", "quantum") != "quantum":
            return {}, "a classical system has no Hamiltonian to show (its terms are in the model)"
        if not build.get("view"):
            return {}, "computing the Hamiltonian view…"
        if view is None:
            return {}, (f"the Hamiltonian view is not computed for this size (dense "
                        f"dimension above {cost.DENSE_DIMENSION})")
        if not len(view["onsite"]):
            return {}, "the geometry has no sites"
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
        if self.structure.projection != "auto":
            state["projection"] = self.structure.projection
        if self.auto_rerun:
            state["auto_rerun"] = True
        if self.overlays:
            state["overlays"] = {calc: [list(o) for o in chosen]
                                 for calc, chosen in self.overlays.items()}
        if self.sliders:
            state["sliders"] = [dict(s) for s in self.sliders]
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
        if ui.get("tool") in structure_tools.TOOLS:
            self.set_tool(ui["tool"])
        self.set_projection(ui.get("projection") if ui.get("projection") in
                            structure_tools.PROJECTIONS else "auto")    # the result views too
        calculations = self._calculation_ids()    # what Run acts on follows from the rest
        selected = ui.get("selected", "")
        try:
            self.select(selected if isinstance(selected, str) and self._exists(selected) else "")
        except Exception:
            self.select("")
        # after the selection, which sets a workspace of its own, and the canvas view after
        # the workspace, which sets one too
        if ui.get("workspace") in WORKSPACES:
            self.set_workspace(ui["workspace"])
        if ui.get("canvas_view") in structure_tools.VIEWS:
            self.set_canvas_view(ui["canvas_view"])
        self.sliders = []
        for spec in ui.get("sliders", []) if isinstance(ui.get("sliders"), list) else []:
            try:
                if spec.get("on") is not None:        # a marker: kept as it was saved
                    if self._slider_kept(spec) and spec.get("axis") in ("x", "y", "xy",
                                                                         "sites"):
                        self.sliders.append({k: spec.get(k) for k in (
                            "entry", "param", "component", "min", "max", "on", "axis",
                            "quantity")})
                    continue
                self.add_slider(spec["entry"], spec["param"], spec.get("component"),
                                spec["min"], spec["max"])
            except Exception:
                pass
        self._show_sliders()
        self.overlays = {}
        overlays = ui.get("overlays") if isinstance(ui.get("overlays"), dict) else {}
        for calc, chosen in overlays.items():
            present = [tuple(o) for o in chosen if isinstance(o, list) and len(o) == 2
                       and o[0] in calculations and o[1] in ("overlay",
                                                             "difference")]
            if calc in calculations and present:
                self.overlays[calc] = present
        for calc in ui.get("results", []) if isinstance(ui.get("results"), list) else []:
            if isinstance(calc, str) and calc in calculations:
                self.result_view(calc)
        tab = ui.get("tab")
        if tab == "result" and self.selected_calculation():           # before phase 3
            tab = ui.get("calculation") or self.selected_calculation()
        if tab == "structure":
            self.viewport.setCurrentIndex(STRUCTURE_TAB)
        elif tab == "kspace":
            self.viewport.setCurrentIndex(KSPACE_TAB)
        elif isinstance(tab, str) and tab in calculations:
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

    def _navigation_changed(self, navigating):
        """While the canvas toolbar pans or zooms, a click on the canvas
        selects nothing: Pick, Box and Lasso show unchecked, and a click on
        one of them turns the pan or zoom off (StructureView.set_tool)."""
        self.tool_buttons.setExclusive(False)
        for button in self.tool_buttons.buttons():
            button.setChecked(not navigating
                              and button.objectName() == f"tool_{self.structure.tool}")
        self.tool_buttons.setExclusive(True)
        if navigating:
            self.message("the canvas pans or zooms, and selects nothing: click Pick, Box or "
                         "Lasso to select sites again")

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
            known = set(structure_tools.match_positions(positions, stored,        # one lookup
                                                        structure_tools.SAME_SITE).tolist())
            new = [p for i, p in enumerate(positions) if i not in known]
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
        self.calculate_button.setEnabled(count > 0)

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
            self.structure.clear("No system yet: add one with New system, next to the "
                                 "workspace tabs.")
            self._refresh_kspace()          # no system: no k-space tab either
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
            self.structure.set_paintable(bool(extra))     # the Field drawn is this system's
        else:
            extra, text = {}, ""
        overlays.update(extra)
        caption += f"\n{text}" if text else ""
        self.structure.show_structure(system, build, caption, **overlays)
        self._refresh_kspace()
        pending = self._pending_sites
        if pending is not None and pending[0] == system and self.session.build_is_current(system):
            self._pending_sites = None
            try:
                self.structure.select(structure_tools.match_positions(
                    build["positions"], pending[1], REGION_TOLERANCE))
            except (ValueError, TypeError):
                pass

    # ---- the k-space tab (13.9)
    def _kpath_calculations(self, system):
        """[(id, label)] of the calculations of a system that take a k-path."""
        out = []
        for calc in self.session.document.calculations:
            try:
                spec = registry.get("calculation", calc.kind)
            except registry.RegistryError:
                continue
            if calc.system == system and "kpath" in spec.param_map:
                out.append((calc.id, f"{calc.id} {calc.kind}"))
        return out

    def _kpath_calculation_chosen(self, calc):
        self.kpath_calc = calc or None
        self._refresh_kspace()

    def _refresh_kspace(self):
        """Draw the zone of the current system; the k-space tab is there only
        while that system has a periodic direction (PLAN.md phase 8, package
        P3), and stays as it was while it is being built."""
        system = self.current_system()
        build = self.builds.get(system) if system else None
        if system is None:
            self._show_kspace_tab(False)
            self.kspace_view.clear("No system yet.")
            return
        if build is None:
            self.kspace_view.clear(f"{system}: building…")
            return
        if build.get("kspace") is None:
            self._show_kspace_tab(False)
            self.kspace_view.clear(f"{system} is finite: it has no Brillouin zone.")
            return
        self._show_kspace_tab(True)
        kspace = dict(build["kspace"], dimensionality=build["dimensionality"])
        calculations = self._kpath_calculations(system)
        ids = [c for c, _ in calculations]
        calc = self.kpath_calc if self.kpath_calc in ids else \
            self.selected_calculation() if self.selected_calculation() in ids else \
            (ids[0] if ids else None)
        kpath = None
        if calc is not None:
            obj = self.session.document.calculation(calc)
            try:
                kpath = registry.get("calculation", obj.kind).normalize_params(
                    obj.params)["kpath"]
            except Exception:
                kpath = None
        surface = None
        for other in self.session.document.calculations:
            result = self.session.result(other.id)
            if other.system == system and other.kind == "fermi_surface" and result is not None \
                    and kspace.get("k2K") is not None:
                mesh = np.column_stack([result.arrays["kx"], result.arrays["ky"],
                                        np.zeros(len(result.arrays["kx"]))])
                reduced = mesh @ np.asarray(kspace["k2K"]).T
                surface = (reduced @ np.asarray(kspace["reciprocal"]))[:, :2], \
                    np.asarray(result.arrays["weight"])
        what = f"the path of {calc}" if calc else "no calculation with a k-path on " + system
        caption = (f"{system} · Brillouin zone · {what}"
                   + (" (pyqula's default: dashed)" if calc and kpath is None else "")
                   + (" · Fermi surface underneath" if surface is not None else ""))
        try:
            self.kspace_view.show_kspace(kspace, calculations, calc, kpath, surface, caption)
        except Exception as error:       # a path through a label this lattice lacks
            self.kspace_view.clear(f"{system}: cannot draw the path of {calc}: {error}")

    def _show_kspace_tab(self, shown):
        """Show or hide the k-space tab; hidden while it is in front, the
        Structure tab comes forward (not whichever tab is next to it)."""
        if not shown and self.viewport.currentIndex() == KSPACE_TAB:
            self.viewport.setCurrentIndex(STRUCTURE_TAB)
        self.viewport.setTabVisible(KSPACE_TAB, shown)

    def _update_status(self):
        """The status bar's summary of the current system, with the estimate
        of the calculation Run acts on, and the run controls, which name it."""
        if self.session is None:
            return
        self._update_run_controls()
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

    def new_classical_system(self, kind):
        """A classical system on its usual lattice, in a supercell."""
        lattice, n, label = CLASSICAL_STARTS[kind]
        ok, system = self._do("add_system", lattice=lattice, kind=kind, name=label)
        if not ok:
            return None
        self._do("add_geometry_op", system=system, kind="supercell", params={"n": [n, n, 1]})
        self.select(system)
        return system

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

    def add_region(self, select=None, name="", system=None):
        """A region of a system (the current one), by expression (x > 0
        unless select says otherwise), selected."""
        system = system if system and self._exists(system) else self._target_system()
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
        elif not ok and name in ("set_enabled", "set_meanfield"):
            # Qt ticked or unticked the box before the refusal (a lock): show the Document
            self.outliner.refresh(self.session)
            self.outliner.set_current(self.selected)

    # ---- calculations and results
    def _refresh_calculations(self):
        """The calculations changed (added, removed, renamed): Run names the
        one it acts on now (the menu of its arrow is filled when shown)."""
        self._update_run_controls()

    def _calculation_ids(self):
        return [c.id for c in self.session.document.calculations] \
            if self.session is not None else []

    def selected_calculation(self):
        """The calculation Run, F5 and Cancel act on: the one selected in
        the outliner, else the one whose result tab is shown, else the
        first; None without any (PLAN.md phase 8, package P4)."""
        ids = self._calculation_ids()
        if self.selected in ids:
            return self.selected
        tab = self.current_tab()
        if tab in ids:
            return tab
        return ids[0] if ids else None

    def select_calculation(self, calc_id):
        """Select a calculation in the outliner (tools/drive.py --run, the
        picks that add one): its form, its tab and Run follow it. A KeyError
        for an id that is not a calculation."""
        if calc_id not in self._calculation_ids():
            raise KeyError(calc_id)
        if self.selected != calc_id:          # select() calls this for a calculation
            self.select(calc_id)
        return calc_id

    def _calculation_chosen(self, index, clicked=False):
        """A tab of the viewport was shown (clicked: the user clicked it, even
        the one already shown): Run, Cancel and the status bar follow it. A
        result tab shown while another calculation is selected in the
        outliner selects the tab's (a click, Ctrl+Tab, the wheel on the tab
        bar, a pick's target, a result put back into its tab), so that the
        outliner and the tab never name two different calculations; a term
        or an op stays selected (its form is kept while its results are
        looked at). The neighbour Qt shows when the tab shown goes away
        (closed, detached, hidden) was chosen by nobody: it moves nothing."""
        previous = getattr(self, "_tab_shown", "structure")
        self._tab_shown = self.current_tab()
        if self.session is None:
            return
        widget = self.viewport.widget(index)
        calc = widget.calc_id if isinstance(widget, PlotView) else None
        ids = self._calculation_ids()
        chosen = clicked or self._tab_present(previous)
        if chosen and calc in ids and self.selected in ids and self.selected != calc:
            self.select(calc)
            return
        self._update_status()

    def _tab_present(self, tab):
        """Whether a tab ("structure", "kspace" or a calculation id) is still
        in the viewport's bar and visible."""
        if tab == "structure":
            return True
        widget = self.kspace_view if tab == "kspace" else self.plots.get(tab)
        index = self.viewport.indexOf(widget) if widget is not None else -1
        return index >= 0 and self.viewport.isTabVisible(index)

    def _calculation_label(self, calc):
        """A calculation's kind as the registry says it (its kind when no
        entry declares it, a plugin left out)."""
        kind = self.session.document.calculation(calc).kind
        try:
            return registry.get("calculation", kind).label
        except registry.RegistryError:
            return kind

    def _update_run_controls(self):
        """Run reads "Run c1 · bands", the calculation it acts on; Cancel is
        enabled while a job of that calculation is queued or running; the
        form of a calculation (its estimate and formRun) says the same
        (PLAN.md phase 8, package P4). Called after every change of the
        Document, the selection, the tab shown and a job."""
        calc = self.selected_calculation()
        job = self.session.calc_jobs.get(calc) if calc is not None else None
        running = job is not None and not job.done
        if calc is None:
            self.run_button.setText("Run")
            self._tip(self.run_button, "nothing to run yet: add a calculation with the + of "
                                       "the Calculations row of the outliner", "run")
        else:
            obj = self.session.document.calculation(calc)
            self.run_button.setText(f"Run {calc} · {obj.kind}")
            self._tip(self.run_button, f"run {calc}, {self._calculation_label(calc).lower()} "
                                       f"on {obj.system}, in a worker (a slow one asks first); "
                                       f"the arrow runs another one, or every stale result",
                      "run")
        self.run_button.setEnabled(calc is not None)
        self.cancel_button.setEnabled(running)
        self._tip(self.cancel_button, f"Cancel: stop the job of {calc} (its worker is "
                                      f"restarted)" if running else
                  "Cancel: stop the job of the selected calculation, while it runs", "cancel")
        update = getattr(self.properties.form, "update_run", None)
        if update is not None:
            update()

    # ---- result views: one tab (or window) per calculation
    @property
    def plot(self):
        """The result view of the selected calculation (made on first use)."""
        calc = self.selected_calculation()
        return self.result_view(calc) if calc is not None else None

    def current_tab(self):
        """"structure", "kspace", or the id of the calculation whose tab is shown."""
        widget = self.viewport.currentWidget()
        if widget is self.kspace_view:
            return "kspace"
        return widget.calc_id if isinstance(widget, PlotView) else "structure"

    def result_view(self, calc):
        """The PlotView of a calculation, made (as a tab) if needed."""
        view = self.plots.get(calc)
        if view is None:
            self.session.document.calculation(calc)
            view = PlotView(calc)
            view.projection = self.structure.projection
            view.renderer_3d = self.structure.renderer_3d
            view.save_requested.connect(self.save_result_dialog)
            view.export_requested.connect(self.export_bundle_dialog)
            view.detach_requested.connect(self.toggle_detached)
            view.overlay_menu_requested.connect(self._fill_overlay_menu)
            view.pick_requested.connect(self._pick_requested)
            view.marker_moved.connect(self._marker_moved)
            view.run_requested.connect(self.run_guarded)            # the status row
            view.cancel_requested.connect(self._cancel_result)
            self.plots[calc] = view
            self.viewport.addTab(view, calc)
            self._draw_result(calc)
        return view

    def show_result(self, calc):
        """Bring a calculation's result view forward (its tab, or its window)."""
        view = self.result_view(calc)
        window = self.plot_windows.get(calc)
        if window is not None:
            window.show()
            window.raise_()
        else:
            self.viewport.setCurrentWidget(view)
        return calc

    def close_result(self, calc):
        view = self.plots.pop(calc, None)
        window = self.plot_windows.pop(calc, None)
        if view is None:
            return
        index = self.viewport.indexOf(view)
        if index >= 0:
            shown = self.viewport.currentIndex() == index
            self.viewport.removeTab(index)
            if shown:                            # back to the structure, not to a neighbour
                self.viewport.setCurrentIndex(STRUCTURE_TAB)
        view.hide()
        view.deleteLater()               # may run inside a signal of its own tab bar
        if window is not None:
            window.hide()
            window.deleteLater()

    def _close_tab(self, index):
        widget = self.viewport.widget(index)
        if isinstance(widget, PlotView):
            self.close_result(widget.calc_id)

    def toggle_detached(self, calc):
        """Move a result view into a window of its own (a plain window, not a
        floating dock, so that it can be moved on Wayland too: see
        ResultWindow), or back into its tab."""
        view = self.plots[calc]
        window = self.plot_windows.pop(calc, None)
        if window is not None:
            window.release()
            window.hide()
            window.deleteLater()
            self.viewport.addTab(view, self._tab_text(calc))
            self.viewport.setCurrentWidget(view)
            view.set_detached(False)
            self._show_state(calc)          # the tab's mark, colour and tooltip
            return False
        self.viewport.removeTab(self.viewport.indexOf(view))
        window = ResultWindow(calc, view, self)
        window.setWindowTitle(f"Result {calc}")
        window.resize(640, 480)
        window.show()
        view.show()
        view.set_detached(True)
        self.plot_windows[calc] = window
        self._show_state(calc)              # the window's title carries the mark
        return True

    def _result_state(self, calc, job=None):
        """(state, progress, message) of a calculation's result, for the marks
        of its tab and the status row above its plot: queued or running while
        a job of it runs (job: the one an event is about, which the session
        may not hold yet), failed when its last run failed and no result is
        kept, else stale, done or none, as Session.status says: a run that
        failed over an earlier result reads stale, the failure being in the
        Jobs panel, and a current result has no row."""
        state, progress = calculation_state(self.session, calc, job)
        if job is None or job.done:
            job = self.session.calc_jobs.get(calc)
        if state in ("queued", "running"):
            return state, progress, job.text or ""
        if state == "failed":
            return state, None, (job.error or "") if job is not None else ""
        return (state if state in ("done", "stale") else "none"), None, ""

    def _tab_text(self, calc, state=None):
        """A result tab's title: the calculation, its kind and the mark of its
        state (ui/marks.py), none when it is done or not computed."""
        try:
            kind = self.session.document.calculation(calc).kind
        except Exception:
            return calc
        state, progress, _ = state or self._result_state(calc)
        sign = mark(state, progress) if state in ROW_STATES else ""
        return f"{calc} {kind}" + (f" {sign}" if sign else "")

    def _show_state(self, calc, job=None):
        """The state of a result where its view is: the tab's title and its
        colour, a detached window's title, the status row above the plot."""
        view = self.plots.get(calc)
        if view is None or self.session is None:
            return
        state = self._result_state(calc, job)
        text = self._tab_text(calc, state)
        index = self.viewport.indexOf(view)
        view.set_status(*state)
        if view.result is None:              # the empty plot says what comes next
            view.caption.setText(f"{calc}: no result yet; " + (
                "it is being computed." if state[0] in ("queued", "running")
                else "press Run (F5)."))
        if index >= 0:
            self.viewport.setTabText(index, text)
            self.viewport.tabBar().setTabTextColor(
                index, QColor(theme.ERROR) if state[0] in ERROR_STATES else QColor())
            self.viewport.setTabToolTip(index, view.status.text.full
                                        if state[0] in ROW_STATES else "")
        window = self.plot_windows.get(calc)
        if window is not None:
            window.setWindowTitle(f"Result {text}")

    def _cancel_result(self, calc):
        """The status row's Cancel: stop the job computing calc's result."""
        job = self.session.calc_jobs.get(calc) if self.session is not None else None
        if job is not None and not job.done:
            self.cancel_job(job.id)

    def _draw_result(self, calc, force=False):
        """Draw a calculation's latest result into its view, unless the view
        already shows exactly that (a redraw would lose the zoom) and force
        is false (a new theme, which also clears an empty view again).
        Whether it is stale goes to the tab's mark and the status row, not
        into the figure, so a result going stale keeps its zoom."""
        view = self.plots[calc]
        result = self.session.result(calc)
        stale = self.session.is_stale(calc) if result is not None else False
        if result is None:
            # an empty view is cleared again by a new theme too (force), so that its
            # figure takes the theme's colours rather than keeping the old one's
            if force or view.result is not None or not view.caption.text().startswith(calc):
                view.clear(f"{calc}: no result yet; press Run (F5).")
            self._show_state(calc)
            return
        self._show_state(calc)
        overlays = [(other, self.session.result(other), mode)
                    for other, mode in self.overlays.get(calc, [])
                    if self.session.result(other) is not None]
        if not force and view.result is result and \
                [(o, id(r), m) for o, r, m in overlays] == \
                [(o, id(r), m) for o, r, m in view.overlays]:
            view.stale = stale
            return
        title = f"{calc} · {result.kind} · {result.mode}"
        notes = [f"{result.meta.get('seconds', 0):.2f} s"]
        if result.meta.get("build_seconds", 0) >= 0.05:
            notes[0] += f" after {result.meta['build_seconds']:.2f} s of building"
        if result.meanfield:
            notes.append(f"mean-field total energy {result.meanfield.get('total_energy', 0):.6g}")
        if result.skipped:
            notes.append("skipped: " + ", ".join(f"{r['id']} ({r['message']})"
                                                 for r in result.skipped))
        view.markers = self._markers_of(calc, result)      # drawn with the plot
        view.show_result(result, title, " · ".join(notes), stale=stale, overlays=overlays)

    def overlay(self, calc, other=None, mode="overlay"):
        """Draw the result of other over calc's (mode overlay), or their
        difference (mode difference); other None clears them. Returns the
        overlays of calc."""
        from guiqula.ui import plots as plot_tools
        self.session.document.calculation(calc)
        if other is None:
            self.overlays.pop(calc, None)
        else:
            if mode not in plot_tools.OVERLAY_MODES:
                raise ValueError(f"mode is one of {list(plot_tools.OVERLAY_MODES)}")
            self.session.document.calculation(other)
            if other == calc:
                raise ValueError("a result cannot overlay itself")
            result, theirs = self.session.result(calc), self.session.result(other)
            if result is not None and theirs is not None and \
                    not plot_tools.can_overlay(result, theirs, mode):
                raise ValueError(f"{other} cannot be drawn over {calc} ({mode}): both must be "
                                 f"curves" + (" on the same x" if mode == "difference" else ""))
            current = [o for o in self.overlays.get(calc, []) if o[0] != other]
            self.overlays[calc] = [(other, mode)] if mode == "difference" else \
                [o for o in current if o[1] != "difference"] + [(other, mode)]
        self.show_result(calc)
        self._draw_result(calc)
        return [list(o) for o in self.overlays.get(calc, [])]

    # ---- sliders (13.10)
    def _slider_value(self, spec):
        """The number a slider's parameter holds now (a marker's: the
        k-point or the positions too), or None."""
        from guiqula.registry import sweeps
        try:
            _, params = sweeps.locate(self.session.document, spec["entry"])
            value = params.get(spec["param"])
            if spec["component"] is not None:
                value = value[spec["component"]]
            if spec.get("quantity") in ("kpoint", "sites") and isinstance(value, list):
                return value
            return float(value) if isinstance(value, (int, float)) else None
        except Exception:
            return None

    # ---- markers (part 3): sliders drawn on result views
    def _marker_axis(self, on, entry, param, component):
        """(axis, quantity) of a parameter drawn on the view of calculation
        on: the axis of its plot that carries what the parameter takes (x,
        y, "xy" for a k-point of a map, "sites" for a result on the atoms);
        ValueError when the plot carries none of it."""
        from guiqula.registry import sweeps
        calc = self.session.document.calculation(on)
        result = self.session.result(on)
        if result is None:
            raise ValueError(f"{on} has no result to draw a marker on: run it first")
        spec = pick_tools.spec_of(result)
        declared = sweeps.locate(self.session.document, entry)[0].param_map.get(param)
        if declared is None:
            raise ValueError(f"{entry} has no parameter {param!r}")
        quantity = declared.quantity
        if spec.get("sites"):
            if quantity == "sites":
                return "sites", quantity
        else:
            for axis in ("x", "y"):
                carrier = spec.get(axis)
                if carrier == "parameter" and [entry, param, component] == \
                        (result.plot.get("parameters") or {}).get(axis):
                    return axis, "parameter"
                if quantity is not None and carrier in pick_tools.AXES and \
                        pick_tools.AXES[carrier] == quantity:
                    return ("xy" if carrier == "kmesh" else axis), quantity
        raise ValueError(f"the plot of {on} ({calc.kind}) has no axis for {entry} {param}")

    def _range_of(self, on, axis):
        """The range of the drawn data on an axis of a view (a marker's
        slider range), or (0, 1)."""
        view = self.plots.get(on)
        if view is None or view.points is None or not len(view.points[0]):
            return 0.0, 1.0
        values = np.asarray(view.points[0 if axis == "x" else 1], dtype=float)
        values = values[np.isfinite(values)]
        if not len(values) or values.max() <= values.min():
            return 0.0, 1.0
        return float(values.min()), float(values.max())

    def _markers_of(self, calc, result):
        """What a view draws of the markers on it: [{index, kind, value,
        label}], a marker whose value is not on the plot left out (a k-point
        off the drawn path)."""
        out = []
        for index, spec in enumerate(self.sliders):
            if spec.get("on") != calc or result is None:
                continue
            value = self._slider_value(spec)
            if value is None:
                continue
            label = f"{spec['entry']} {spec['param']}" + (
                "" if spec["component"] is None else f"[{'xyz'[spec['component']]}]")
            drawn = self._marker_drawing(spec, value, result)
            if drawn is not None:
                out.append(dict(drawn, index=index, label=label))
        return out

    def _marker_drawing(self, spec, value, result):
        axis = spec.get("axis")
        try:
            if axis in ("x", "y") and spec.get("quantity") != "kpoint":
                return {"kind": "vline" if axis == "x" else "hline", "value": float(value)}
            if axis == "x":                          # a k-point along a k-path
                x = pick_tools.path_position(result, value)
                return None if x is None else {"kind": "vline", "value": x}
            if axis == "xy":                         # a k-point of a map: all its images
                points = pick_tools.mesh_positions(result, value)
                return {"kind": "dots", "value": points} if points else None
            if axis == "sites" and result.structure is not None:
                return {"kind": "rings", "value": [[float(p[0]), float(p[1])] for p in value]}
        except (TypeError, ValueError, KeyError, IndexError):
            return None
        return None

    def _refresh_markers(self):
        for calc, view in list(self.plots.items()):
            if view.result is not None:
                view.set_markers(self._markers_of(calc, view.result))

    def _marker_moved(self, index, x, y, dragging):
        """A marker dragged on its view: the value under it, as a slider's;
        a refusal (a lock) is reported and the marker goes back."""
        try:
            self.move_marker(index, x, y, dragging)
        except (ValueError, KeyError, IndexError) as error:
            self.message(f"marker: {error}", error=True)
            self.session.dispatcher.end_merge()
            self._refresh_markers()

    def move_marker(self, index, x, y, dragging=False):
        """Set a marker's parameter to the value at (x, y) of its view (its
        axis, or the k-point there); x and y not finite: the drag ended
        where it was. Returns the value set."""
        spec = self.sliders[index]
        if not (np.isfinite(x) and np.isfinite(y)):
            self.session.dispatcher.end_merge()
            if any(c.id == spec["entry"] for c in self.session.document.calculations):
                self._ran_at_once(spec["entry"])
            return None
        if spec.get("quantity") == "kpoint":
            view = self.plots[spec["on"]]
            value = pick_tools.pick(view.result, x, y)["values"].get("kpoint")
            if value is None:
                return None
        else:
            value = x if spec.get("axis") == "x" else y
        return self.set_slider(index, value, dragging)

    def _mark(self, source, target, done):
        """Keep the values a pick set drawn on the plot it was picked on:
        a marker for each parameter that an axis of that plot carries."""
        if source is None or source not in self.plots:
            return []
        entries = []
        if target["target"] in ("set", "add") and done.get("calculation"):
            entries = [(done["calculation"], name, None) for name in target["params"]]
        elif target["target"] == "parameter":
            entries = [(p["entry"], p["param"], p["component"]) for p in target["set"]]
        added = []
        for entry, param, component in entries:
            if any(s.get("on") == source and (s["entry"], s["param"], s["component"]) ==
                   (entry, param, component) for s in self.sliders):
                continue
            try:
                added.append(self.add_slider(entry, param, component, on=source))
            except (ValueError, KeyError):         # no axis of that plot carries it
                continue
        return added

    def _show_sliders(self):
        self.sliders_panel.set_sliders(self.sliders, [self._slider_value(s) for s in self.sliders])

    def add_slider(self, entry, param, component=None, minimum=None, maximum=None, on=None):
        """Attach a parameter to a slider; with on, a calculation whose
        view draws it as a marker, on the axis of its plot that carries the
        parameter (a k-point or sites: a marker without a slider's range).
        The range is the axis's drawn range when on is given and it is
        not; else 0 to 1. Returns its index."""
        from guiqula.core import locks
        from guiqula.registry import sweeps
        document = self.session.document
        axis = quantity = None
        if on is not None:
            axis, quantity = self._marker_axis(on, entry, param, component)
        if quantity in ("kpoint", "sites"):
            if sweeps.locate(document, entry)[0].param_map.get(param) is None:
                raise ValueError(f"{entry} has no parameter {param!r}")
            self.sliders.append({"entry": entry, "param": param, "component": None,
                                 "min": None, "max": None, "on": on, "axis": axis,
                                 "quantity": quantity})
            self._show_sliders()
            self._refresh_markers()
            return len(self.sliders) - 1
        problem = sweeps.check_target(document, entry, param, component)
        if problem:
            raise ValueError(problem)
        if minimum is None or maximum is None:
            low, high = self._range_of(on, axis) if on is not None else (0.0, 1.0)
            minimum = low if minimum is None else minimum
            maximum = high if maximum is None else maximum
        minimum, maximum = float(minimum), float(maximum)
        if not np.isfinite([minimum, maximum, maximum - minimum]).all():
            raise ValueError("the range needs finite numbers")
        if not maximum > minimum:
            raise ValueError("the range needs a maximum above its minimum")
        probe = sweeps.with_value(document, entry, param, component,
                                  float(maximum if self._slider_value(
                                      {"entry": entry, "param": param, "component": component})
                                        == minimum else minimum))
        broken = locks.violations(document, probe)
        if broken:
            raise ValueError(f"{', '.join(broken)} {'is' if len(broken) == 1 else 'are'} "
                             f"locked: unlock it to move {entry}.{param} with a slider")
        spec = {"entry": entry, "param": param, "component": component,
                "min": float(minimum), "max": float(maximum)}
        if on is not None:
            spec.update(on=on, axis=axis, quantity=quantity)
        self.sliders.append(spec)
        self._show_sliders()
        if on is None:
            self.docks["slidersDock"].raise_()
        self._refresh_markers()
        return len(self.sliders) - 1

    def remove_slider(self, index):
        del self.sliders[index]
        self._show_sliders()
        self._refresh_markers()

    def _slider_kept(self, spec):
        """Whether a slider still fits the Document: its entry and parameter,
        and the calculation a marker is drawn on."""
        from guiqula.registry import sweeps
        document = self.session.document
        if spec.get("on") is not None and not any(c.id == spec["on"]
                                                  for c in document.calculations):
            return False
        if spec.get("quantity") in ("kpoint", "sites"):
            try:
                return spec["param"] in sweeps.locate(document, spec["entry"])[0].param_map
            except Exception:
                return False
        return sweeps.check_target(document, spec["entry"], spec["param"],
                                   spec["component"]) is None

    def _prune_sliders(self):
        """Drop the sliders whose entry was removed, and the markers whose
        calculation was."""
        kept = [spec for spec in self.sliders if self._slider_kept(spec)]
        if len(kept) != len(self.sliders):
            self.sliders = kept
            self._show_sliders()

    def _slider_moved(self, index, value, dragging):
        """The Sliders dock: a refusal (a lock) is reported, not raised."""
        try:
            self.set_slider(index, value, dragging)
        except (ValueError, KeyError, IndexError) as error:     # CommandError is a ValueError
            self.message(f"slider: {error}", error=True)
            self.sliders_panel.show_values([self._slider_value(s) for s in self.sliders])

    def set_slider(self, index, value, dragging=False):
        """Set a slider's parameter; the steps of one drag are one undo step."""
        from guiqula.registry import sweeps
        spec = self.sliders[index]
        entry, param, component = spec["entry"], spec["param"], spec["component"]
        key = f"slider:{index}:{entry}:{param}:{component}"
        if spec.get("quantity") in ("kpoint", "sites"):          # a marker of a vector
            command = ("set_param", {"entry": entry, "name": param, "value": value})
        else:
            value = min(max(float(value), spec["min"]), spec["max"])
            command = sweeps.command(self.session.document, entry, param, component, value)
        try:
            self.session.do_merged(key, command[0], **command[1])
        finally:
            if not dragging:
                self.session.dispatcher.end_merge()
        self.sliders_panel.show_values([self._slider_value(s) for s in self.sliders])
        if not dragging and any(c.id == entry for c in self.session.document.calculations):
            self._ran_at_once(entry)           # released: the calculation it moved
        return value

    def _fill_overlay_menu(self, calc):
        """The Overlay menu of a result view: the other results that can be
        drawn over it, and their differences."""
        from guiqula.ui import plots as plot_tools
        menu = self.plots[calc].overlay.menu()
        menu.clear()
        result = self.session.result(calc)
        chosen = dict(self.overlays.get(calc, []))
        for other in self.session.document.calculations:
            theirs = self.session.result(other.id)
            if other.id == calc or not plot_tools.can_overlay(result, theirs):
                continue
            action = menu.addAction(f"{other.id} {other.kind} on {other.system}")
            action.setObjectName(f"overlayWith_{other.id}")
            action.setCheckable(True)
            action.setChecked(chosen.get(other.id) == "overlay")
            action.triggered.connect(lambda checked, o=other.id: self._act(
                "overlay", calc=calc, **({"other": o} if checked else {})))
            if plot_tools.can_overlay(result, theirs, "difference"):
                action = menu.addAction(f"{calc} − {other.id}")
                action.setObjectName(f"difference_{other.id}")
                action.triggered.connect(lambda checked=False, o=other.id: self._act(
                    "overlay", calc=calc, other=o, mode="difference"))
        if self.overlays.get(calc):
            menu.addSeparator()
            action = menu.addAction("None")
            action.setObjectName("overlayNone")
            action.triggered.connect(lambda: self._act("overlay", calc=calc))
        if menu.isEmpty():
            menu.addAction("no other result to draw here").setEnabled(False)

    def _refresh_results(self):
        """After a document change: close the views of removed calculations,
        mark stale results."""
        present = {c.id for c in self.session.document.calculations}
        self.overlays = {calc: [o for o in chosen if o[0] in present]
                         for calc, chosen in self.overlays.items() if calc in present}
        self.overlays = {calc: chosen for calc, chosen in self.overlays.items() if chosen}
        for calc in list(self.plots):
            if calc not in present:
                self.close_result(calc)
            else:
                self._draw_result(calc)

    def export_bundle_dialog(self, calc):
        """Choose a folder; the bundle goes into <calc>_<kind> inside it."""
        if not calc or self.session.result(calc) is None:
            self.message(f"{calc or 'no calculation'}: no result to export yet", error=True)
            return None
        parent = QFileDialog.getExistingDirectory(self, f"Export {calc}: choose a folder")
        if not parent:
            return None
        kind = self.session.document.calculation(calc).kind
        return self._act("export_bundle", calculation=calc, path=str(Path(parent) /
                                                                     f"{calc}_{kind}"))

    def export_bundle(self, calculation, path):
        """Write the figure (on white), the data and the script of a result
        into a folder (io/bundle.py); returns the files written."""
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        from guiqula.ui import plots as plot_tools
        result = self.session.result(calculation)
        if result is None:
            raise ValueError(f"{calculation} has no result yet")
        stale = self.session.is_stale(calculation)
        overlays = [(other, self.session.result(other), mode)
                    for other, mode in self.overlays.get(calculation, [])
                    if self.session.result(other) is not None]

        def figure(png, pdf):
            fig = Figure(figsize=(7, 4.5), dpi=100, layout="constrained")
            canvas = FigureCanvasAgg(fig)
            ax, _ = plot_tools.draw(fig, result, f"{calculation} · {result.kind} · "
                                    f"{result.mode}", overlays, theme_name="light",
                                    projection=self.structure.projection)
            canvas.draw()
            theme.centre(fig, ax)          # the axes in the middle, as in the window
            fig.savefig(png, dpi=200)
            fig.savefig(pdf)

        files = bundle.write(path, result, figure, trusted=self.session.trusted,
                             results=self.session.result_refs(), stale=stale)
        self.message(f"exported {calculation} to {path}")
        return [str(f) for f in files]

    def save_result_dialog(self, calc):
        path, _ = QFileDialog.getSaveFileName(self, f"Save the data of {calc}", f"{calc}.npz",
                                              "arrays and metadata (*.npz)")
        if path:
            self._act("save_result", calculation=calc, path=path)

    def run_selected(self):
        """Run the selected calculation (the Run button, F5): the one
        selected in the outliner, else the one whose tab is shown, else the
        first (selected_calculation)."""
        calc = self.selected_calculation()
        if calc is None:
            self.message("no calculation to run: add one with the + of the Calculations row",
                         error=True)
            return None
        return self.run_guarded(calc)

    def run(self, calculation=None):
        """The run action: a calculation (the selected one when left out)
        run as Run and the form's Run run it, through the cost guard;
        returns its job's summary, or None when the cost bar asks first."""
        if calculation is None:
            return self.run_selected()
        if calculation not in self._calculation_ids():
            raise ValueError(f"no calculation {calculation!r}; calculations: "
                             f"{self._calculation_ids()}")
        return self.run_guarded(calculation)

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
        self.auto_rerun_button.setChecked(self.auto_rerun)        # Follow, in the first row
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
                key = self.session.calculation_key(calc.id)
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

    # ---- run at once (PLAN.md phase 7, answer 48)
    def set_run_at_once(self, enabled=True, remember=True):
        """Run every calculation as soon as it is added or one of its
        parameters is set, through the cost guard (off: only when asked);
        the interactive program keeps the choice in the settings file.
        Returns whether it is on."""
        self.run_at_once = bool(enabled)
        self.run_at_once_action.setChecked(self.run_at_once)
        if remember and self.use_settings:
            settings.put("run_at_once", self.run_at_once)
        return self.run_at_once

    def _set_calculation(self, event):
        """The calculation a mutation added or set a parameter of, or None."""
        name, args = event.get("name"), event.get("args") or {}
        if name == "add_calculation":
            return event.get("result")
        if name in ("set_param", "set_params") and any(
                c.id == args.get("entry") for c in self.session.document.calculations):
            return args["entry"]
        return None

    def _ran_at_once(self, calc):
        """Run a calculation that was just added or set, when Run at once
        is on and it has no current result (an undo, or a value set back,
        brings an earlier result back, which needs no run). Returns the job
        id, or None."""
        if not self.run_at_once or self.session is None or \
                (self.session.result(calc) is not None and not self.session.is_stale(calc)):
            return None
        try:
            unset = self.session.plan_calculation(calc).problem
        except Exception:
            unset = True
        if unset:            # not set up yet (a sweep naming nothing, an untrusted Python
            return None      # node): the outliner says why, and nothing runs
        self.session.jobs.supersede("run", calc)
        job = self.run_guarded(calc)
        return job["id"] if isinstance(job, dict) else None

    # ---- picks (PLAN.md phase 7)
    def pick(self, calculation=None, x=None, y=None, box=None, polygon=None, system=None,
             values=None):
        """What a point of a calculation's result stands for, and what can
        be done with it: {"calculation", "system", "values", "label",
        "notes", "targets", "point", "sites"}. x, y: a position in the
        plot's data coordinates (snapped to the drawn point the readout
        names there); box [x0, y0, x1, y1] or polygon [[x, y], ...]: the
        atoms inside, on a result drawn on them. Or values without a
        calculation, {quantity: value} on a system (the current one by
        default): a k-point of the k-space tab, the sites of the canvas
        selection."""
        from guiqula.remote.api import jsonable
        if calculation is None:
            return jsonable(self._pick_values(system, values))
        view = self.plots.get(calculation)
        result = view.result if view is not None and view.result is not None else \
            self.session.result(calculation)
        system = self.session.document.calculation(calculation).system
        if result is None:
            raise ValueError(f"{calculation} has no result to pick from: run it first")
        index = sites = None
        if box is not None or polygon is not None:
            if view is None or view.points is None or not len(view.points[0]):
                raise ValueError(f"{calculation}: show its result drawn flat on the atoms to "
                                 f"pick them with a box or a lasso")
            xy = np.column_stack(view.points[:2])
            sites = structure_tools.indices_in_box(xy, *box) if box is not None else \
                structure_tools.indices_in_polygon(xy, polygon)
            sites = [int(i) for i in sites]
        elif x is None or y is None:
            raise ValueError("give x and y, a box or a polygon")
        elif view is not None:
            index, x, y = view.snap(float(x), float(y))
        picks_y = view is None or view.picks_y()
        picked = pick_tools.pick(result, x, y if picks_y else None, index=index, sites=sites)
        build = self.builds.get(system)
        try:
            mode = self.session.plan_system(system).mode
        except Exception:
            mode = None
        picked["targets"] = pick_targets.targets(
            self.session.document, system, picked["values"], source=calculation, mode=mode,
            dimensionality=build["dimensionality"] if build else None,
            snapshot=pick_targets.snapshot_of(result))
        picked.update(calculation=calculation, system=system, sites=sites)
        return jsonable(picked)

    def _pick_values(self, system, values):
        """pick() of values given as they are, on a system."""
        system = system or self.current_system()
        if system is None:
            raise ValueError("there is no system to pick on")
        self.session.document.system(system)
        if not isinstance(values, dict) or not values or \
                not set(values) <= set(pick_tools.QUANTITIES):
            raise ValueError(f"values is a dict of quantities: {list(pick_tools.QUANTITIES)}")
        build = self.builds.get(system)
        try:
            mode = self.session.plan_system(system).mode
        except Exception:
            mode = None
        targets = pick_targets.targets(self.session.document, system, values, mode=mode,
                                       dimensionality=build["dimensionality"] if build else None)
        return {"calculation": None, "system": system, "values": values,
                "label": pick_tools.describe(values), "notes": [], "targets": targets,
                "point": None, "sites": None}

    def pick_to(self, calculation=None, target=None, x=None, y=None, box=None, polygon=None,
                system=None, values=None):
        """Do one target of a pick: its index in the list pick() gives for
        the same position (or values), or the target dict itself. Returns
        what was done: {"target", and "calculation", "term", "region" or
        "sites"}."""
        if not isinstance(target, dict):
            targets = self.pick(calculation, x, y, box, polygon, system, values)["targets"]
            if isinstance(target, bool) or not isinstance(target, int) \
                    or not 0 <= target < len(targets):
                raise ValueError(f"target is a dict or an index from 0 to {len(targets) - 1}")
            target = targets[target]
        done = self._do_target(target)
        self._mark(calculation, target, done)
        return done

    def _do_target(self, target):
        from guiqula.registry import sweeps
        kind = target.get("target")
        session = self.session
        if kind == "set":
            session.do("set_params", entry=target["calculation"], params=target["params"])
            self.show_result(target["calculation"])
            return {"target": kind, "calculation": target["calculation"]}
        if kind == "add":
            calc = session.do("add_calculation", system=target["system"], kind=target["kind"],
                              params=target["params"], name=target.get("name", ""))
            self.select_calculation(calc)
            self.show_result(calc)
            return {"target": kind, "calculation": calc}
        if kind == "kpath":
            session.do("set_param", entry=target["calculation"], name=target["param"],
                       value=target["kpath"])
            self.show_result(target["calculation"])
            return {"target": kind, "calculation": target["calculation"]}
        if kind == "parameter":
            key = f"pick:{time.time()}"                   # several parameters: one undo step
            try:
                for point in target["set"]:
                    name, args = sweeps.command(session.document, point["entry"], point["param"],
                                                point["component"], point["value"])
                    session.do_merged(key, name, **args)
            finally:
                session.dispatcher.end_merge()
            run = target.get("run")
            if run and any(c.id == run for c in session.document.calculations):
                self._ran_at_once(run)
                self.show_result(run)
            return {"target": kind, "calculation": run}
        if kind == "fermi_level":
            if target.get("term"):
                term = target["term"]
                key = f"pick:{time.time()}"            # set, and on again if it was off: one step
                try:
                    session.do_merged(key, "set_param", entry=term, name="mu", value=target["mu"])
                    if not session.document.find(term)[4].enabled:
                        session.do_merged(key, "set_enabled", entry=term, enabled=True)
                finally:
                    session.dispatcher.end_merge()
            else:
                term = session.do("add_term", system=target["system"], kind="onsite",
                                  params={"mu": target["mu"]}, name=pick_targets.FERMI_LEVEL)
            return {"target": kind, "term": term}
        if kind == "region":
            region = session.do("add_region", system=target["system"], select={
                "kind": "positions", "positions": target["positions"], "tol": REGION_TOLERANCE})
            self.select(region)
            return {"target": kind, "region": region}
        if kind == "select_sites":
            if self.current_system() != target["system"]:
                self.select(target["system"])
                self._refresh_structure()
            count = self.select_sites(positions=target["positions"])
            self.viewport.setCurrentIndex(STRUCTURE_TAB)
            return {"target": kind, "sites": count}
        raise ValueError(f"unknown target {kind!r}")

    def pick_menu(self, calculation=None, x=None, y=None, box=None, polygon=None, system=None,
                  values=None, leave=()):
        """The menu of a pick (built, not shown: the view pops it up, a test
        reads its actions): the picked values, why something could not be
        picked, then the targets, but those of the kinds in leave (the
        canvas has its own buttons for a region of the selection)."""
        menu = QMenu(self)
        menu.setObjectName("pickMenu")
        menu.setToolTipsVisible(True)
        try:
            picked = self.pick(calculation, x, y, box, polygon, system, values)
        except Exception as error:
            menu.addAction(str(error)).setEnabled(False)
            return menu
        picked["targets"] = [t for t in picked["targets"] if t["target"] not in leave]
        title = menu.addAction(picked["label"] or "nothing to pick here")
        title.setObjectName("pickTitle")
        title.setEnabled(False)
        for note in picked["notes"]:
            menu.addAction(note).setEnabled(False)
        menu.addSeparator()
        for i, target in enumerate(picked["targets"]):
            action = menu.addAction(target["label"])
            action.setObjectName(f"pickTarget_{i}")
            action.triggered.connect(lambda checked=False, t=target: self._act(
                "pick_to", calculation=calculation, target=t))
        if not picked["targets"] and picked["label"]:
            menu.addAction("no calculation takes these values").setEnabled(False)
        return menu

    def _pick_requested(self, calculation, where, position):
        """A result view asks for the pick menu at a point."""
        self._popup_pick(position, calculation=calculation, **where)

    def _popup_pick(self, position, **where):
        if self._pick_menu is not None:
            self._pick_menu.deleteLater()
        self._pick_menu = self.pick_menu(**where)
        self._pick_menu.popup(position)
        return self._pick_menu

    def _kpoint_picked(self, k, position):
        """A click in the k-space tab: what takes that k-point."""
        self._popup_pick(position, system=self.current_system(), values={"kpoint": k})

    def _selection_menu(self):
        """Calculate on selection: what takes the selected sites."""
        try:
            system, positions = self._selection_positions()
        except ValueError as error:
            self.message(str(error), error=True)
            return None
        button = self.calculate_button
        return self._popup_pick(button.mapToGlobal(button.rect().bottomLeft()), system=system,
                                values={"sites": positions}, leave=("select_sites", "region"))

    def add_meanfield(self, system=None):
        """Mean field (interactions), the last item of the terms' Add menu:
        turn on the mean-field block of a system (the current one) and
        select its row. Returns the row's id, or None."""
        system = system if system and self._exists(system) else self._target_system()
        if system is None:
            return None
        if self.session.document.system(system).kind != "quantum":
            self.message(f"{system} is a classical system: it has no mean field", error=True)
            return None
        if not self.session.document.system(system).hamiltonian.meanfield.enabled:
            self._do("set_meanfield", system=system, enabled=True)     # refused when locked
        return self.select(f"{system}/meanfield")

    def cancel_selected(self):
        calc = self.selected_calculation()
        job = self.session.calc_jobs.get(calc) if calc else None
        if job is not None and not job.done:
            self.cancel_job(job.id)

    def cancel_job(self, job_id):
        self._act("cancel", target=job_id)

    # ---- files, recovery and undo
    def _may_replace(self, before):
        """New, Open and Recover replace the document: the interactive
        program first asks what closing it asks, Save, Discard or Cancel
        (False: cancelled, the document stays)."""
        if not (self.ask_before_close and self.session is not None and self.session.modified):
            return True
        return self._confirm_discard(before)

    def new_document(self):
        """File > New: an empty document, so the start page shows again
        (without a session there is no document to replace: the page only)."""
        if self.session is None:
            self.show_start(True)
            return
        if self._may_replace("starting a new document"):
            self._act("new")

    def show_start(self, shown=True):
        """The start page in the viewport's place (shown), or the viewport;
        the window shows the page while the document has no system. The
        recent files are read again when the page comes back."""
        page = self.start_page
        if shown and self.central_stack.currentWidget() is not page:
            recent = settings.load()["recent"] if self.use_settings else []
            page.set_recent(recent)
        self.central_stack.setCurrentWidget(page if shown else self.viewport)
        return shown

    def start(self, search=""):
        """The start page's filter (the start action): every band narrowed
        to the cards matching the text; returns the object names of the
        cards in sight (the page shows while the document has no system)."""
        return self.start_page.filter(search)

    def open_document(self, path_or_name):
        if self._may_replace(f"opening {Path(str(path_or_name)).name}"):
            self._act("load", path=str(path_or_name))

    def show_gallery(self):
        """The presets gallery (non-modal); Open loads the preset chosen."""
        from guiqula.ui.gallery import Gallery
        gallery = Gallery(self)
        gallery.opened.connect(self.open_document)
        gallery.show()
        self.gallery = gallery
        return gallery

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

    def _update_trust(self):
        """The trust bar: shown while the document holds Python code that
        does not run (PLAN.md 13.7); non-modal, like the other bars."""
        session = self.session
        self.trust_action.setChecked(session.trusted)
        code = session.code_entries()
        if session.trusted or not code:
            self.trust_bar.dismiss()
            return
        shown = ", ".join(code[:6]) + (f" and {len(code) - 6} more" if len(code) > 6 else "")
        self.trust_bar.show_message(
            f"This document holds Python code ({shown}). It came from a file, so the code "
            f"does not run until you trust it; until then those entries are skipped.",
            [("Trust and run", lambda: self._act("trust"), "trustButton"),
             ("Show the code", lambda: self.select(code[0]), "showCodeButton")])

    def recover(self, path=None):
        if not self._may_replace("recovering the unsaved work"):
            return None
        info = self._act("recover", **({"path": path} if path else {}))
        if info is not None:
            self.recovery_bar.dismiss()
            self.message(f"recovered {info['path']}")
        return info

    def _discard_recovery(self, path):
        self._act("discard_recovery", path=path)
        self.offer_recovery(quiet=True)

    def undo(self, steps=1):
        if self.session.dispatcher.can_undo():
            self.session.undo(steps)

    def redo(self, steps=1):
        if self.session.dispatcher.can_redo():
            self.session.redo(steps)

    def _follow_step(self, event):
        """After an undo or a redo, select the entry the step touched (or its
        system, when the entry is gone); the viewport stays where it is."""
        for candidate in (event.get("entry"), event.get("system")):
            if candidate and self._exists(candidate):
                self.selected = candidate
                return

    def _fill_history(self):
        """Undo history: the steps undo would take back (newest first) and
        those redo would take again; choosing one goes back or forth to it."""
        menu = self.history_menu
        menu.clear()
        history = self.session.dispatcher.history() if self.session else {"undo": [], "redo": []}
        for i, text in reversed(list(enumerate(history["redo"][:15], 1))):
            action = menu.addAction(f"redo: {text}")
            action.triggered.connect(lambda checked=False, n=i: self.redo(n))
        if history["redo"] and history["undo"]:
            menu.addSeparator()
        for i, text in enumerate(history["undo"][:25], 1):
            action = menu.addAction(f"undo: {text}")
            action.triggered.connect(lambda checked=False, n=i: self.undo(n))
        if menu.isEmpty():
            menu.addAction("nothing to undo").setEnabled(False)

    # ---- help (decision 13.13)
    def show_help(self, item=None):
        """F1, a form's ?: the help of an item (the selected one) in the Help dock."""
        return self._act("help", entry=self.selected if item is None else item)

    def help(self, entry=None, guide=None, anchor=None):
        """Show help in the Help dock: an outliner item's (entry, by default
        the selected one; "" for guiqula's guide), a section
        of a guide (guide "pyqula" or "guiqula" and anchor), a guide's
        contents (guide alone), or the plugins (guide "plugins"); returns
        the title shown."""
        dock = self.docks["helpDock"]
        dock.show()
        dock.raise_()
        if guide == "plugins":
            return self.help_panel.show_plugins()
        if guide is not None and anchor is not None:
            return self.help_panel.show_section(guide, anchor)
        if guide is not None:
            if guide not in ("pyqula", "guiqula"):
                raise ValueError(f"guide is pyqula or guiqula, not {guide!r}")
            return self.help_panel.show_contents(guide)
        return self.help_panel.show_item(self.selected if entry is None else entry)

    def _help_follows(self, entry):
        """While the Help dock shows an item's help, it follows the selection."""
        dock = self.docks["helpDock"]
        page = self.help_panel.page
        if dock.isVisible() and not dock.visibleRegion().isEmpty() and page and \
                page[0] == "item" and page[1] != entry:
            self.help_panel.show_item(entry, remember=False)

    # ---- theme, settings, shortcuts
    def set_theme(self, name="system"):
        """Light, dark, or following the desktop ("system"); what is drawn
        in colours is drawn again. The interactive program keeps the choice
        in the settings file. Returns the theme applied."""
        applied = theme.apply(QApplication.instance(), name)
        self.theme_choice = name
        self.theme_actions[name].setChecked(True)
        if self.use_settings:
            settings.put("theme", name)
        if self.session is not None:
            self.outliner.refresh(self.session)
            self.properties.show_item(self.session, self.selected)   # its formula images
            self._refresh_structure()
            for calc in list(self.plots):
                self._draw_result(calc, force=True)
        self._show_help_again()                      # its equations, in the new text colour
        return applied

    def _show_help_again(self):
        """Draw the help page shown again (its equations follow the theme's
        text colour and the interface text's size)."""
        page = self.help_panel.page
        if page is not None:
            {"item": lambda: self.help_panel.show_item(page[1], remember=False),
             "section": lambda: self.help_panel.show_section(*page[1:], remember=False),
             "contents": lambda: self.help_panel.show_contents(page[1], remember=False),
             "plugins": lambda: self.help_panel.show_plugins(remember=False)
             }[page[0]]()

    def set_plot_text(self, name="normal", remember=True):
        """The size of the text of every drawing (ui/theme.py: small,
        normal or large); what is drawn is drawn again. The interactive
        program keeps the choice in the settings file. Returns the size."""
        theme.set_text_size(name)
        self.text_actions[name].setChecked(True)
        if remember and self.use_settings:
            settings.put("plot_text", name)
        if self.session is not None:
            self._refresh_structure()             # the k-space tab with it
            for calc in list(self.plots):
                self._draw_result(calc, force=True)
        return name

    def set_ui_text(self, name="normal", remember=True):
        """The size of the text of the menus, the panels and the forms
        (ui/theme.py: normal or large, for a projector); the outliner and
        the form are built again in it. The interactive program keeps the
        choice in the settings file. Returns the size."""
        theme.set_ui_text(name)
        theme.apply_text(QApplication.instance())
        self.ui_text_actions[name].setChecked(True)
        if remember and self.use_settings:
            settings.put("ui_text", name)
        if self.session is not None:
            self.outliner.refresh(self.session)
            self.properties.show_item(self.session, self.selected)   # its formula images
        self._show_help_again()                      # its equations at the new size
        return name

    # ---- the panels (PLAN.md phase 8, package P5)
    def _window_act(self, command, method, /, **args):
        """A control of the window: through the dispatcher when there is a
        session (journaled, as a driver's would be), else the method."""
        return self._act(command, **args) if self.session is not None else method(**args)

    def reset_layout(self):
        """View > Reset layout: the panels in their default arrangement
        (_arrange_docks); the window keeps its size. Returns the panels shown."""
        self._arrange_docks()
        return [name for name, dock in self.docks.items() if not dock.isHidden()]

    def set_log(self, enabled=True):
        """The status bar's Log toggle: show the bottom area, the Log (raised)
        and the Console, or hide it. Returns whether it is shown."""
        log, console = (self.docks[name] for name in BOTTOM_DOCKS)
        if enabled:
            first = log.isHidden() and console.isHidden()
            log.show()
            console.show()
            log.raise_()
            if first and self.dockWidgetArea(log) == Qt.DockWidgetArea.BottomDockWidgetArea:
                self.resizeDocks([log], [LOG_HEIGHT], Qt.Orientation.Vertical)
        else:
            log.hide()
            console.hide()
        self._sync_log_toggle()
        return self.log_toggle.isChecked()

    def _sync_log_toggle(self, *args):
        """The Log toggle shows whether the bottom area is, however it was
        shown or closed (the toggle, View > Panels, a dock's close button)."""
        shown = not all(self.docks[name].isHidden() for name in BOTTOM_DOCKS)
        if self.log_toggle.isChecked() != shown:
            self.log_toggle.setChecked(shown)

    def show_panel(self, name, shown=True):
        """Show and raise a panel, or hide it (shown false): its objectName
        (helpDock) or its title (Help). Returns the objectName."""
        dock = self.docks.get(name) or next(
            (d for d in self.docks.values() if d.windowTitle().lower() == str(name).lower()),
            None)
        if dock is None:
            raise ValueError(f"unknown panel {name!r}; panels: "
                             f"{[d.windowTitle() for d in self.docks.values()]}")
        if shown:
            dock.show()
            dock.raise_()
        else:
            dock.hide()
        self._sync_log_toggle()
        return dock.objectName()

    def _in_front(self, name):
        """Whether a panel is shown and in front of the tabs it shares."""
        dock = self.docks[name]
        return not dock.isHidden() and not dock.visibleRegion().isEmpty()

    def _job_added(self, job_id):
        """A new row of the Jobs panel: Jobs comes forward, unless Help is
        in front showing an item's help (Run at once starts a job at every
        edit of the form that help explains) or Sliders is in front (a
        slider's release, or the automatic re-run at every step of a drag,
        starts one under the mouse that moves it)."""
        page = self.help_panel.page
        if self._in_front("helpDock") and page is not None and page[0] == "item":
            return
        if self._in_front("slidersDock"):
            return
        self.docks["jobsDock"].raise_()

    def _restore_layout(self, layout):
        """The arrangement and the size the window had when it was last
        closed (the setting layout); the default when there is none or it is
        of another LAYOUT_VERSION. Returns whether it was restored."""
        if not layout:
            return False
        try:
            geometry = QByteArray.fromBase64(layout["geometry"].encode("ascii"))
            state = QByteArray.fromBase64(layout["state"].encode("ascii"))
        except (KeyError, AttributeError, UnicodeEncodeError):
            return False
        self.restoreGeometry(geometry)
        if not self.restoreState(state, LAYOUT_VERSION):
            self._arrange_docks()
            return False
        for name, dock in self.docks.items():         # floating ones from elsewhere come back
            if dock.isFloating():
                dock.setFloating(False)
        self.set_workspace(self.workspace)           # the palette rows follow the workspace
        self._sync_log_toggle()
        return True

    def _save_layout(self):
        """Keep the arrangement and the size in the settings (closeEvent)."""
        layout = {"state": bytes(self.saveState(LAYOUT_VERSION).toBase64()).decode("ascii"),
                  "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii")}
        try:
            settings.put("layout", layout)
        except OSError as error:
            self.message(f"could not write the settings: {error}", error=True)
        return layout

    def set_always_trust(self, enabled):
        """Open every file with its Python nodes allowed to run (13.7's
        global switch, kept in the settings file)."""
        self.always_trust_action.setChecked(bool(enabled))
        if self.session is not None:
            self.session.always_trust = bool(enabled)
        if self.use_settings:
            settings.put("always_trust", bool(enabled))

    def set_remote(self, enabled, remember=True):
        """Let other programs drive this window (PLAN.md 3.7): a JSON-RPC
        server on a localhost port, whose port and token are in a connection
        file only the user can read (remote/connection.py); guiqula mcp, the
        Claude add-on, finds it there. Off by default; the menu's choice is
        kept in the settings file (remember), guiqula --remote turns it on
        for one run. Returns the port, or None when off."""
        enabled = bool(enabled)
        self.remote_wanted = enabled
        self.remote_action.setChecked(enabled)
        if remember and self.use_settings:
            settings.put("remote", enabled)
        if enabled and self.remote is None and self.session is not None:
            from guiqula.remote import window as remote_window
            try:
                self.remote = remote_window.start(self)
            except OSError as error:
                self.message(f"could not start remote control: {error}", error=True)
            else:
                self.message(f"remote control on: port {self.remote.port}, connection file "
                             f"{self.remote.file}")
        elif not enabled and self.remote is not None:
            self._stop_remote()
            self.message("remote control off")
        self._update_remote_label()
        return self.remote.port if self.remote is not None else None

    def _stop_remote(self):
        if self.remote is not None:
            server, self.remote = self.remote, None
            server.close()

    def _update_remote_label(self):
        if self.remote is None:
            self.remote_label.setText("")
            self.remote_label.setToolTip("")
        else:
            self.remote_label.setText(f"remote :{self.remote.port}")
            self.remote_label.setToolTip(f"remote control is on (File > Allow remote control); "
                                         f"connection file {self.remote.file}")

    def _remember_file(self, path):
        path = Path(path)
        if path.parent != project.PRESETS:
            try:
                settings.add_recent(path.resolve())
            except OSError as error:
                self.message(f"could not write the settings: {error}", error=True)

    def _fill_recent(self):
        self.recent_menu.clear()
        recent = settings.load()["recent"] if self.use_settings else []
        for path in recent:
            action = self.recent_menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self.open_document(p))
        if not recent:
            self.recent_menu.addAction("no recent files").setEnabled(False)

    def focus_search(self):
        """Ctrl+F: the Add menu of the workspace with its search line
        focused, or New system while the document has no system. Returns
        the family it lists."""
        return self.open_add_menu()["menu"].removeprefix("paletteMenu_")

    def close_current_result(self):
        tab = self.current_tab()
        if tab not in ("structure", "kspace"):
            self.close_result(tab)

    def show_shortcuts(self):
        """The shortcut table (non-modal)."""
        dialog = QDialog(self)
        dialog.setObjectName("shortcutsDialog")
        dialog.setWindowTitle("Keyboard shortcuts")
        rows = shortcuts.rows()
        table = QTableWidget(len(rows), 3, dialog)
        table.setObjectName("shortcutsTable")
        table.setHorizontalHeaderLabels(["where", "keys", "what"])
        table.verticalHeader().hide()
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, row in enumerate(rows):
            for j, text in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(text))
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.resizeColumnsToContents()
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("The canvas and outliner keys work while that widget has "
                                "the focus (click it first)."))
        layout.addWidget(table)
        dialog.resize(640, 560)
        dialog.show()
        self.shortcuts_dialog = dialog
        return dialog

    def _update_actions(self):
        has = self.session is not None
        undo = self.session.dispatcher.undo_text() if has else None
        redo = self.session.dispatcher.redo_text() if has else None
        self.undo_action.setEnabled(undo is not None)
        self.redo_action.setEnabled(redo is not None)
        self.undo_action.setText(f"&Undo {undo}" if undo else "&Undo")
        self.redo_action.setText(f"&Redo {redo}" if redo else "&Redo")
        self.unlock_action.setEnabled(has and bool(self.session.document.locks))
        self._update_run_controls()
        if has:
            self._update_palettes()
        else:
            self.add_button.setEnabled(False)
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
        """A message: in the Log, and its first line in the status bar after
        the system summary (the error colour for an error), where it stays
        until the next one."""
        self.log.appendPlainText(("ERROR: " if error else "") + text)
        self.status_message.show_message(text, error)

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
