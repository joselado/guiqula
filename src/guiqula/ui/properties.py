"""The properties panel (PLAN.md section 4): the form of whatever the
outliner has selected, generated from its registry declaration (PLAN.md
3.2). Every edit is sent as a command through the window's ``run``
(name, **args) -> (ok, result or message); a refusal is shown under the
form and the editor goes back to the stored value.

After a document change the panel refreshes: if the selected entry still
has the same shape (same kind, same regions to choose from) the values are
updated in place, so an editor in use is never destroyed under the mouse;
otherwise the form is rebuilt.

A form reads as physics (PLAN.md phase 8, package P6): its head is the
title with the enabled switch in its row, the group and the doc line, the
formula, then the parameters; a term says where it acts (its region, or
"acts everywhere" with a link to the Regions menu of its system). The
labels speak the physics and the tooltips the engine (the parameter's
name, has_spin, is_sparse).

Locks (core/locks.py): what a lock covers is shown disabled, its label
saying so. Right-clicking a parameter's label opens its menu: Lock or
Unlock, Attach a slider (the window's slider action, over a range from the
value, sliders.range_from), Sweep this parameter (a sweep calculation of
SWEEP_POINTS values over that range, selected) and, for a Field, Preview on
the canvas.

When the user looks at a Field (focus, typing, its panel), the panel emits
preview(entry, parameter); the window draws that Field on the structure,
with live_value(parameter) while it is being typed.
"""
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QScrollArea,
                               QToolButton, QVBoxLayout, QWidget)

from guiqula.core import regions as region_tools
from guiqula.core.document import DocumentError
from guiqula.registry import base as registry
from guiqula.registry import cost
from guiqula.registry.params import FieldParam, VectorFieldParam
from guiqula.ui import formulas, icons, marks, theme
from guiqula.ui.forms import format_number, line_up, make_editor, result_sources
from guiqula.ui.outliner import system_of
from guiqula.ui.sliders import range_from

EVERYWHERE = "(everywhere)"
FAMILY = {"op": "geometry_op", "term": "term", "calculation": "calculation"}
SWEEP_POINTS = 11
# the interactions beyond the first neighbours, folded in the mean-field form
FURTHER_NEIGHBOURS = ("V2", "V3", "J2", "J3")
SPIN_TIP = ("spinful: both spin species, even without a term that needs them (has_spin). The "
            "terms decide by themselves: a Zeeman field, a spin-orbit coupling or an exchange "
            "field makes the Hamiltonian spinful whatever is chosen here, so spinless holds "
            "only while no term needs the spin.")
NAMBU_TIP = ("the Bogoliubov-de Gennes (Nambu) Hamiltonian, electrons and holes, even without "
             "a pairing term (nambu). A pairing term makes it Nambu by itself; checking this "
             "asks for it without one.")
TIJ_TIP = ("the hoppings to the first, second, ... neighbours, comma separated (tij): as many "
           "numbers as neighbour shells the hopping reaches, so 1, 0.1 is a first-neighbour "
           "hopping 1 and a second-neighbour hopping 0.1")
SPARSE_TIP = ("store the Hamiltonian as a sparse matrix (is_sparse), for large systems: the "
              "calculations then use sparse solvers, with the few states near an energy "
              "rather than the full spectrum")


def _regions(system):
    """[(id, name)] of a system's regions, for piecewise Fields."""
    return tuple((r.id, r.name) for r in system.regions)


def _quiet(widget, setter, value):
    widget.blockSignals(True)
    try:
        setter(value)
    finally:
        widget.blockSignals(False)


def sweep_target(session, system_id, entry_id):
    """The calculation a sweep of a parameter of entry_id runs at every
    value: the calculation itself when it is one; else one of the system's
    (a sweep runs no sweep), the first that gives numbers to collect (a
    gap, a Chern number, an energy: gives_numbers), or the first; "" when
    the system has none, and the label menu then says to add one."""
    document = session.document
    own = [c for c in document.calculations if c.system == system_id
           and not getattr(_spec_of(c), "document_level", True)]
    if any(c.id == entry_id for c in own):
        return entry_id
    return next((c.id for c in own if gives_numbers(session, c.id)),
                own[0].id if own else "")


def gives_numbers(session, calc_id):
    """Whether a calculation is known to give numbers a sweep collects: its
    result has numbers among its arrays, or it is declared as one that
    draws numbers (registry/calculations.py's scalar(): a gap, a Chern
    number). A Python calculation is known only once it has run."""
    import numpy as np
    result = session.result(calc_id)
    if result is not None and any(np.ndim(v) == 0 for v in result.arrays.values()):
        return True
    try:
        plot = _spec_of(session.document.calculation(calc_id)).plot
    except (AttributeError, DocumentError, KeyError):
        return False
    return isinstance(plot, dict) and plot.get("kind") == "scalar"


def _spec_of(calc):
    try:
        return registry.get("calculation", calc.kind)
    except registry.RegistryError:
        return None


class Form(QWidget):
    lock_owner = None       # what a parameter lock names: "t1" in "t1.m", "s1" in "s1.n"
    previews = False        # whether its Fields can be drawn on the canvas (terms, mean field)

    def __init__(self, panel, item_id, title, doc=""):
        super().__init__()
        self.panel = panel
        self.item_id = item_id
        self.labels = {}
        self.guarded = []   # widgets a lock of the whole form disables (enabled, region, ...)
        self.menu = None    # the label menu shown last
        self.enabled = None  # the enabled switch of the title's row (add_enabled)
        layout = QVBoxLayout(self)
        self.title = QLabel(title)
        self.title.setObjectName("formTitle")
        self.title.setWordWrap(True)
        # parented from the start: a parentless widget made visible is a window of its own,
        # which flashes on the desktop and takes the activation from the main window
        self.help_button = QToolButton(self)
        self.help_button.setText("?")
        self.help_button.setObjectName("formHelp")
        self.help_button.setToolTip("the help of this entry: pyqula's documentation of it (F1)")
        self.help_button.setVisible(bool(item_id))
        self.help_button.clicked.connect(lambda: panel.help_requested.emit(self.item_id))
        icons.follow(self.help_button, self._set_icons)     # never, for the empty form
        self.doc = QLabel(doc, self)
        self.doc.setObjectName("formDoc")
        self.doc.setWordWrap(True)
        self.doc.setVisible(bool(doc))
        self.rows = QFormLayout()
        self.rows.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.error = QLabel("")
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.heading = QHBoxLayout()
        self.heading.addWidget(self.title, 1)
        self.heading.addWidget(self.help_button)
        layout.addLayout(self.heading)
        layout.addWidget(self.doc)
        layout.addLayout(self.rows)
        layout.addWidget(self.error)
        layout.addStretch(1)
        self.editors = {}

    @property
    def session(self):
        return self.panel.session

    def _set_icons(self):
        """The ? as the help icon, and the run row's button (icons.follow:
        at the first show of the ? and after every change of theme)."""
        self.help_button.setIcon(icons.icon("help"))
        self.help_button.setIconSize(icons.size())
        update = getattr(self, "update_run", None)
        if update is not None and self.session is not None:     # not after the session closed
            update()

    def signature(self):
        return (self.item_id,)

    def update_values(self):
        """Show the Document's values (and update_reports)."""
        self.update_reports()

    def update_reports(self):
        """Show what the builds and results say; the editors are left as
        they are (a build finishing while the user types)."""

    def commit(self, command, /, **args):
        ok, out = self.panel.run(command, **args)
        self.error.setText("" if ok else str(out))
        if not ok:
            self.update_values()
        return ok

    def add_editors(self, params, values, send, regions=(), sources=(), rows=None):
        """One editor per parameter; send(name, value) commits it. regions:
        [(id, name)] the piecewise Fields can use; sources: the results a
        from_result Field can read (forms.result_sources); rows: the form
        layout they go in (the form's own rows by default)."""
        rows = self.rows if rows is None else rows
        for param in params:
            editor = make_editor(param, getattr(self.session.jobs, "names", {}), regions,
                                 sources)
            editor.set_value(values[param.name])
            editor.committed.connect(lambda p=param, e=editor: self._send(e, p, send))
            if hasattr(editor, "preview"):
                editor.preview.connect(lambda p=param: self.panel.preview.emit(self.item_id,
                                                                               p.name))
            label = QLabel(param.label)
            label.setObjectName(f"label_{param.name}")
            label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            label.customContextMenuRequested.connect(
                lambda point, name=param.name: self.label_menu(name, point))
            rows.addRow(label, editor)
            self.labels[param.name] = label
            self.editors[param.name] = editor
            self._label_says(param.name, [])
        line_up(self.editors.values())        # the kind buttons of all rows, one width

    def add_enabled(self, send):
        """The enabled switch, in the title's row (check_enabled); send(bool)
        commits it."""
        self.enabled = QCheckBox("enabled")
        self.enabled.setObjectName("check_enabled")
        self.enabled.setToolTip("unchecked, the entry stays in the document and is left out "
                                "of the builds (enabled)")
        self.enabled.toggled.connect(send)
        self.heading.insertWidget(1, self.enabled)
        return self.enabled

    # ---- the labels' menu: lock, slider, sweep, preview
    def _label_says(self, name, locked_by):
        """A label's text and tooltip: the physics on the label, and in the
        tooltip the doc, the parameter's name in the engine, the locks and
        what its menu offers."""
        label, param = self.labels[name], self.editors[name].param
        sweepable = self._sweepable(name)
        offers = [what for what, ok in (("attach a slider", sweepable), ("sweep it", sweepable),
                                        ("preview it on the canvas", self._previewable(name)),
                                        ("unlock it" if locked_by else "lock it",
                                         self.lock_owner is not None)) if ok]
        tip = param.doc + ("\n\n" if param.doc else "") + f"parameter {param.name}"
        if locked_by:
            tip += f"; locked by {', '.join(locked_by)}"
        if offers:
            tip += "; right-click to " + ", ".join(offers[:-1]) + \
                (" or " if len(offers) > 1 else "") + offers[-1]
        label.setText(param.label + (" (locked)" if locked_by else ""))
        label.setToolTip(tip)

    def _sweepable(self, name):
        """Whether a slider or a sweep can move this parameter (a number of
        a Field, of an op, of a calculation, of the lattice, of the mean
        field or of a model; sweeps.check_target)."""
        return not self._not_sweepable(name)

    def _not_sweepable(self, name, component=None):
        """Why a slider or a sweep cannot move this parameter, or "": it
        holds no number (sweeps.check_target), or it is a number of a sweep,
        which no calculation reads, so moving it would change no result."""
        from guiqula.registry import sweeps
        if self._runs_others():
            return (f"{name} is a number of {self.item_id}, a sweep, which no calculation "
                    f"reads: sweep or slide a parameter of a term, an op or a calculation")
        param = self.editors[name].param
        if isinstance(param, VectorFieldParam) and component is None:
            component = 0
        try:
            return sweeps.check_target(self.session.document, self.item_id, name,
                                       component) or ""
        except Exception as error:
            return str(error)

    def _runs_others(self):
        """Whether this form's entry is a calculation that runs others (a
        sweep: registry document_level)."""
        try:
            family, *_, obj = self.session.document.find(self.item_id)
        except Exception:
            return False
        return family == "calculation" and getattr(_spec_of(obj), "document_level", False)

    def _previewable(self, name):
        return self.previews and isinstance(self.editors[name].param, FieldParam)

    def _number_of(self, name, component=None):
        """The finite number a parameter (or a component of it) holds, or
        None: an expression, a structured Field, an empty optional."""
        from guiqula.registry import sweeps
        try:
            value = sweeps.locate(self.session.document, self.item_id)[1].get(
                name, self.editors[name].param.default)
            if component is not None:
                value = value[component]
        except Exception:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(value):
            return None
        return float(value)

    def label_menu(self, name, point=None):
        """The menu of a parameter's label (paramMenu_<name>), shown at point
        of the label (its middle when left out): Lock or Unlock, Attach a
        slider, Sweep this parameter (one item per component of a vector)
        and Preview on the canvas, those that apply. Returns it, or None
        when nothing applies."""
        label, param = self.labels[name], self.editors[name].param
        menu = QMenu(label)
        menu.setObjectName(f"paramMenu_{name}")
        menu.setToolTipsVisible(True)
        if self.lock_owner is not None:
            target = f"{self.lock_owner}.{name}"
            if target in self.session.document.locks:
                action = menu.addAction("Unlock this parameter",
                                        lambda: self.commit("unlock", target=target))
                action.setObjectName(f"unlockParam_{name}")
                action.setToolTip(f"let {target} be changed again")
            else:
                action = menu.addAction("Lock this parameter",
                                        lambda: self.commit("lock", target=target))
                action.setObjectName(f"lockParam_{name}")
                action.setToolTip(f"keep {target} as it is: its editor is disabled until it is "
                                  f"unlocked (a teaching preset's lock)")
        if self._sweepable(name):
            vector = isinstance(param, VectorFieldParam)
            components = list(enumerate("xyz"[:param.length])) if vector else [(None, "")]
            for what, verb in (("slider", "Attach a slider"), ("sweep", "Sweep this parameter")):
                where = menu.addMenu(verb) if vector else menu
                if vector:
                    where.setObjectName(f"{'attachSlider' if what == 'slider' else 'sweepParam'}"
                                        f"Menu_{name}")
                    where.setToolTipsVisible(True)
                for component, axis in components:
                    self._range_action(where, what, verb, name, component, axis)
        if self._previewable(name):
            action = menu.addAction("Preview on the canvas", lambda: self.commit(
                "preview", entry=self.item_id, param=name))
            action.setObjectName(f"previewField_{name}")
            action.setToolTip(f"draw {param.label} on the sites of the Structure tab (the "
                              f"Field view), where it can be painted")
        if menu.isEmpty():
            menu.deleteLater()
            return None
        self.menu = menu
        menu.popup(label.mapToGlobal(point if point is not None else label.rect().center()))
        return menu

    def _range_action(self, menu, what, verb, name, component, axis):
        """One item of the label menu: a slider or a sweep of a parameter
        (or of one component), over the range of its value, disabled when
        it holds no number to take the range from (or, for a slider, when
        it is locked)."""
        param = self.editors[name].param
        value = self._number_of(name, component)
        text = (f"{axis} component" if axis else verb)
        span = None if value is None else range_from(value, getattr(param, "minimum", None),
                                                     getattr(param, "maximum", None))
        action = menu.addAction(text)
        prefix = "attachSlider" if what == "slider" else "sweepParam"
        action.setObjectName(f"{prefix}_{name}" + (f"_{axis}" if axis else ""))
        label = param.label + (f" {axis}" if axis else "")
        if span is None:
            action.setEnabled(False)
            action.setToolTip(f"{label} holds no number to take a range from: make it a number "
                              f"first")
        elif what == "slider":
            action.setToolTip(f"a slider in the Sliders panel moving {label} from {span[0]:g} "
                              f"to {span[1]:g}; the cheap results follow it with Follow on")
            action.setEnabled(self.editors[name].isEnabled())
            if not action.isEnabled():
                action.setToolTip(f"{label} is locked: unlock it to move it with a slider")
            action.triggered.connect(lambda: self.attach_slider(name, component))
        else:
            target = sweep_target(self.session, self.sweep_system(), self.item_id)
            what = f"a sweep calculation: {SWEEP_POINTS} values of {label} from {span[0]:g} " \
                f"to {span[1]:g}, each running {target}"
            action.setToolTip(
                self._no_calculation() if not target else
                f"{what} and collecting the numbers it gives (a gap, a Chern number, an "
                f"energy)" if gives_numbers(self.session, target) else
                f"{what}, which has given no number to collect so far (a sweep collects a "
                f"gap, a Chern number, an energy): if it gives none, name another in the "
                f"calculation box of the sweep's form")
            action.setEnabled(bool(target))
            action.triggered.connect(lambda: self.sweep(name, component))
        return action

    def slider_range(self, name, component=None):
        """(low, high) of a slider or a sweep of a parameter, from its value
        (sliders.range_from); ValueError when it holds no number, or when no
        slider or sweep can move it (_not_sweepable)."""
        why = self._not_sweepable(name, component)
        if why:
            raise ValueError(why)
        value = self._number_of(name, component)
        if value is None:
            raise ValueError(f"{name} holds no number to take a range from")
        param = self.editors[name].param
        return range_from(value, getattr(param, "minimum", None), getattr(param, "maximum", None))

    def attach_slider(self, name, component=None):
        """Attach a slider to a parameter (the window's slider action) over
        slider_range; returns its index, or None when refused."""
        try:
            low, high = self.slider_range(name, component)
        except ValueError as error:
            self.error.setText(str(error))
            return None
        ok, out = self.panel.run("slider", entry=self.item_id, param=name, component=component,
                                 minimum=low, maximum=high)
        self.error.setText("" if ok else str(out))
        return out if ok else None

    def sweep(self, name, component=None):
        """Add a sweep of a parameter over slider_range, SWEEP_POINTS
        values, running a calculation of the same system (sweep_target), and
        select it; returns its id, or None when refused."""
        try:
            low, high = self.slider_range(name, component)
        except ValueError as error:
            self.error.setText(str(error))
            return None
        system = self.sweep_system()
        target = sweep_target(self.session, system, self.item_id)
        if not target:
            self.error.setText(self._no_calculation())
            return None
        params = {"calculation": target, "entry": self.item_id, "param": name,
                  "component": component, "start": low, "stop": high, "steps": SWEEP_POINTS}
        run = self.panel.run
        ok, out = run("add_calculation", system=system, kind="sweep", params=params)
        if not ok:
            self.error.setText(str(out))
            return None
        run("select", entry=out)             # the form is replaced: nothing of it after this
        return out

    def sweep_system(self):
        """The system a sweep of this form's parameters runs on."""
        return self.system_id

    def _no_calculation(self):
        return (f"{self.sweep_system()} has no calculation for a sweep to run at every value: "
                f"add one first (the + of the Calculations row)")

    # ---- locks
    def whole_locks(self):
        """Lock targets that cover every parameter of this form."""
        return []

    def apply_locks(self):
        """Disable what the Document's locks cover; say so on the labels."""
        locks = set(self.session.document.locks)
        whole = [t for t in self.whole_locks() if t in locks]
        for name, editor in self.editors.items():
            own = f"{self.lock_owner}.{name}" if self.lock_owner else None
            by = whole + ([own] if own in locks else [])
            editor.setEnabled(not by)
            if name in self.labels:
                self._label_says(name, by)
        for widget in self.guarded:
            widget.setEnabled(not whole)

    def live_value(self, name):
        editor = self.editors.get(name)
        return editor.live_value() if editor is not None and hasattr(editor, "live_value") \
            else None

    def _formula(self, tex):
        label = QLabel()
        label.setObjectName("formulaImage")
        label.setToolTip(tex)
        label.setContentsMargins(0, 6, 0, 6)
        color = self.palette().color(QPalette.ColorRole.WindowText).name()
        try:
            label.setPixmap(formulas.pixmap(tex, color, self.devicePixelRatioF()))
        except formulas.FormulaError as error:
            label.setText(f"formula: {tex}")
            label.setToolTip(str(error))
        return label

    def _send(self, editor, param, send):
        try:
            value = editor.value()
        except ValueError as error:
            self.error.setText(f"{param.name}: {error}")
            self.update_values()
            return
        send(param.name, value)


class EmptyForm(Form):
    def __init__(self, panel, text="Select an entry in the outliner."):
        super().__init__(panel, "", "Properties", text)


class SystemForm(Form):
    """Name, base lattice, Hamiltonian construction, what the build found."""

    def __init__(self, panel, system_id):
        system = panel.session.document.system(system_id)
        self.lock_owner = system_id
        super().__init__(panel, system_id, f"System {system_id}", "")
        self.system_id = system_id
        self.name = QLineEdit()
        self.name.setObjectName("systemName")
        self.name.editingFinished.connect(self._rename)
        self.rows.addRow("name", self.name)
        self.lattice = QComboBox()
        self.lattice.setObjectName("latticeBox")
        for spec in sorted(registry.entries("lattice"), key=lambda s: (s.group, s.label)):
            self.lattice.addItem(f"{spec.label} ({spec.group})", spec.kind)
        self.lattice.activated.connect(self._set_lattice)
        self.rows.addRow("lattice", self.lattice)
        self.base_kind = system.geometry.base.kind
        try:
            spec = registry.get("lattice", self.base_kind)
            self.add_editors(spec.params, spec.normalize_params({}) | system.geometry.base.params,
                             lambda name, value: self.commit("set_param", entry=system_id,
                                                             name=name, value=value))
        except registry.RegistryError:
            pass
        if system.hamiltonian is not None:
            box = QGroupBox("Hamiltonian construction")
            box.setObjectName("constructionBox")
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            self.has_spin, self.nambu, self.sparse = QComboBox(), QCheckBox(), QCheckBox()
            self.has_spin.addItem("spinless", False)
            self.has_spin.addItem("spinful", True)
            self.tij = QLineEdit()
            for widget, name in ((self.has_spin, "has_spin"), (self.nambu, "nambu"),
                                 (self.sparse, "is_sparse"), (self.tij, "tij")):
                widget.setObjectName(f"construction_{name}")
            self.has_spin.activated.connect(lambda index: self._set_spin(index))
            self.nambu.toggled.connect(lambda v: self.commit(
                "set_construction", system=system_id, nambu=v))
            self.sparse.toggled.connect(lambda v: self.commit(
                "set_construction", system=system_id, is_sparse=v))
            self.tij.editingFinished.connect(self._set_tij)
            for widget, tip, text in ((self.has_spin, SPIN_TIP, "spin"),
                                      (self.nambu, NAMBU_TIP, "superconducting (Nambu)"),
                                      (self.tij, TIJ_TIP, "hopping range (neighbours)"),
                                      (self.sparse, SPARSE_TIP, "sparse matrices (large systems)")):
                widget.setToolTip(tip)
                label = QLabel(text)
                label.setToolTip(tip)
                label.setObjectName(f"constructionLabel_{widget.objectName().split('_', 1)[1]}")
                form.addRow(label, widget)
            self.layout().insertWidget(3, box)
        self.guarded = [self.name] + ([self.has_spin, self.nambu, self.sparse, self.tij]
                                      if system.hamiltonian is not None else [])
        self.info = QLabel()
        self.info.setObjectName("systemInfo")
        self.info.setWordWrap(True)
        self.layout().insertWidget(self.layout().count() - 2, self.info)
        self.update_values()

    def signature(self):
        system = self.session.document.system(self.system_id)
        return ("system", self.system_id, system.geometry.base.kind)

    def update_values(self):
        system = self.session.document.system(self.system_id)
        _quiet(self.name, self.name.setText, system.name)
        _quiet(self.lattice, self.lattice.setCurrentIndex,
               self.lattice.findData(system.geometry.base.kind))
        for name, editor in self.editors.items():
            param = editor.param
            editor.set_value(system.geometry.base.params.get(name, param.default))
        line_up(self.editors.values())
        if system.hamiltonian is not None:
            c = system.hamiltonian.construction
            _quiet(self.has_spin, self.has_spin.setCurrentIndex,
                   self.has_spin.findData(bool(c.has_spin)))
            _quiet(self.nambu, self.nambu.setChecked, c.nambu)
            _quiet(self.sparse, self.sparse.setChecked, c.is_sparse)
            _quiet(self.tij, self.tij.setText, ", ".join(format_number(t) for t in c.tij))
        self.update_reports()

    def update_reports(self):
        self.info.setText(self._info())

    def whole_locks(self):
        return [self.system_id, f"{self.system_id}/geometry"]

    def apply_locks(self):
        """The geometry lock covers the lattice; the system's lock everything."""
        super().apply_locks()
        locks = self.session.document.locks
        self.lattice.setEnabled(not any(t in locks for t in self.whole_locks()))
        for widget in self.guarded:
            widget.setEnabled(self.system_id not in locks)

    def _info(self):
        session, system_id = self.session, self.system_id
        if system_id in session.build_errors:
            return f"cannot be built: {session.build_errors[system_id]}"
        build = session.builds.get(system_id)
        if build is None:
            return "building…"
        plan = session.plan_system(system_id)
        text = (f"{build['dimensionality']}D · {build['sites']} sites · {plan.mode} · "
                f"Hilbert dimension {build['dimension']}")
        if plan.upgraded_by:
            text += f"\n{plan.mode} because of {', '.join(plan.upgraded_by)}"
        if build["dimension"] > cost.DENSE_DIMENSION:
            text += (f"\nabove pyqula's dense limit ({cost.DENSE_DIMENSION}): full "
                     f"diagonalizations will be slow; consider sparse matrices (large "
                     f"systems), above")
        return text + ("" if session.build_is_current(system_id) else "\n(updating…)")

    def _rename(self):
        name = self.name.text().strip()
        if name and name != self.session.document.system(self.system_id).name:
            self.commit("rename", entry=self.system_id, name=name)

    def _set_lattice(self, index):
        kind = self.lattice.itemData(index)
        if kind != self.session.document.system(self.system_id).geometry.base.kind:
            self.commit("set_lattice", system=self.system_id, lattice=kind)

    def _set_spin(self, index):
        has_spin = self.has_spin.itemData(index)
        if has_spin != self.session.document.system(self.system_id).hamiltonian.construction \
                .has_spin:
            self.commit("set_construction", system=self.system_id, has_spin=has_spin)

    def _set_tij(self):
        try:
            tij = [float(t) for t in self.tij.text().replace(";", ",").split(",") if t.strip()]
        except ValueError:
            self.error.setText("hopping range: a comma separated list of numbers, one per "
                               "neighbour shell")
            self.update_values()
            return
        if tij != self.session.document.system(self.system_id).hamiltonian.construction.tij:
            self.commit("set_construction", system=self.system_id, tij=tij)


class EntryForm(Form):
    """A geometry op, a term or a calculation."""

    def __init__(self, panel, entry_id):
        family, owner, _, _, obj = panel.session.document.find(entry_id)
        self.lock_owner = entry_id
        try:
            spec = registry.get(FAMILY[family], obj.kind)
        except registry.RegistryError as error:
            spec = None
            super().__init__(panel, entry_id, f"{entry_id}  {obj.kind}", str(error).strip("\"'"))
        if spec is not None:
            super().__init__(panel, entry_id, f"{spec.label}",
                             f"{entry_id} · {spec.group}\n{spec.doc}".strip())
            if spec.formula:
                self.layout().insertWidget(2, self._formula(spec.formula))
        self.family, self.kind, self.spec = family, obj.kind, spec
        self.system_id = owner.id if owner is not None else obj.system
        self.previews = family == "term"
        self.enabled = None
        if family in ("op", "term"):
            self.add_enabled(lambda v: self.commit("set_enabled", entry=entry_id, enabled=v))
        self.region = self.region_link = None
        self.region_ids = ()
        if family == "term" and owner.regions:
            self.region = QComboBox()
            self.region.setObjectName("regionBox")
            self.region.setToolTip("where the term acts: everywhere, or on the sites of one "
                                   "region of the system (set_region)")
            self.region.addItem(EVERYWHERE, None)
            for region in owner.regions:
                self.region.addItem(f"{region.id}  {region.name}", region.id)
            self.region_ids = tuple(r.id for r in owner.regions)
            self.region.activated.connect(self._set_region)
            self.rows.addRow("region", self.region)
        elif family == "term":
            self.region_link = QLabel(f'<span style="color: {theme.DOC}">acts everywhere · '
                                      f'</span><a href="#regions">restrict to a region</a>')
            self.region_link.setObjectName("regionLink")
            self.region_link.setWordWrap(True)
            self.region_link.setToolTip(f"{owner.id} has no region yet: the link opens the "
                                        f"Regions menu of {owner.id} (a region by expression, "
                                        f"or from the sites selected on the canvas); a term "
                                        f"can then be restricted to it")
            self.region_link.setTextInteractionFlags(
                Qt.TextInteractionFlag.LinksAccessibleByMouse)
            self.region_link.linkActivated.connect(lambda _: self.restrict_to_region())
            self.rows.addRow(self.region_link)
        if family == "calculation":
            self.rows.addRow("system", QLabel(obj.system))
        if spec is not None:
            self.sources = result_sources(panel.session, owner.id) if family == "term" else []
            self.add_editors(spec.params, spec.normalize_params({}) | obj.params,
                             lambda name, value: self.commit("set_param", entry=entry_id,
                                                             name=name, value=value),
                             _regions(owner) if family == "term" else (), self.sources)
        self.guarded = [w for w in (self.enabled, self.region, self.region_link) if w is not None]
        self.status = QLabel()
        self.status.setObjectName("entryStatus")
        self.status.setWordWrap(True)
        self.layout().insertWidget(self.layout().count() - 2, self.status)
        self._add_run_row()
        self.update_values()

    def whole_locks(self):
        out = [self.item_id]
        if self.family == "op":
            out += [self.system_id, f"{self.system_id}/geometry"]
        elif self.family == "term":
            out.append(self.system_id)
        return out

    def signature(self):
        found = self.session.document.find(self.item_id)
        regions = _regions(found[1]) if found[0] == "term" else ()
        sources = tuple((calc, tuple(arrays)) for calc, _, arrays in
                        result_sources(self.session, found[1].id)) if found[0] == "term" else ()
        return (self.family, self.item_id, found[-1].kind, regions, sources)

    def update_values(self):
        obj = self.session.document.find(self.item_id)[-1]
        if self.enabled is not None:
            _quiet(self.enabled, self.enabled.setChecked, obj.enabled)
        if self.region is not None:
            _quiet(self.region, self.region.setCurrentIndex, self.region.findData(obj.region))
        for name, editor in self.editors.items():
            if name in obj.params:
                editor.set_value(obj.params[name])
        line_up(self.editors.values())            # the kind buttons of all rows, one width
        self.update_reports()

    def update_reports(self):
        self.status.setText(self._status())

    def _status(self):
        session = self.session
        if self.family == "calculation":
            # the state the tab, the plot's status row and the outliner read (ui/marks.py)
            state, _ = marks.calculation_state(session, self.item_id)
            job = session.calc_jobs.get(self.item_id)
            if state == "failed" and job is not None and job.error:
                return f"result: failed, {marks.failure_line(job.error)}"
            return f"result: {state}"
        try:
            stage = session.plan_system(self.system_id).stage(self.item_id)
        except (KeyError, DocumentError):
            return ""
        if stage.problem:
            return f"invalid, skipped: {stage.problem}"
        notes = list(stage.warnings)
        build = session.builds.get(self.system_id)
        if build is not None and session.build_is_current(self.system_id):
            for report in build["reports"]:
                if report["id"] == self.item_id:
                    if report["status"] == "invalid":
                        return f"pyqula refused it, skipped: {report['message']}"
                    if report.get("mode"):
                        notes.append(f"Hilbert space after it: {report['mode']}")
        return "\n".join(notes)

    def _set_region(self, index):
        region = self.region.itemData(index)
        self.commit("set_region", entry=self.item_id, region=region)

    def restrict_to_region(self):
        """The region link: the Regions menu of the term's system (P2's "+"
        menu of its Regions row), below the link."""
        link = self.region_link
        where = link.mapToGlobal(link.rect().bottomLeft()) if link is not None else None
        self.panel.regions_requested.emit(self.system_id, where)

    def _add_run_row(self):
        """A calculation's form has its estimate and a button, formRun,
        which reads Run, Run again when the result is stale and Cancel while
        it runs (PLAN.md phase 8, package P4), in a row (run_row) that the
        panel shows under the form, so that it stays in sight however long
        the form is (package P8). Run is the window's run action, through
        the cost guard, and Cancel the session's cancel; the window calls
        update_run() as the Document, the builds and the jobs change."""
        if self.family != "calculation":
            return
        from guiqula.ui import marks, shortcuts
        row = QWidget(self)
        row.setObjectName("formRunRow")
        row.hide()                               # until the panel puts it in its footer
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        estimate = QLabel(row)
        estimate.setObjectName("formEstimate")
        estimate.setWordWrap(True)
        button = QPushButton(row)
        button.setObjectName("formRun")
        button.setIconSize(icons.size())
        line.addWidget(estimate, 1)
        line.addWidget(button)
        self.run_row, self.run_button, self.run_estimate = row, button, estimate

        def running():
            return marks.calculation_state(self.session, self.item_id)[0] in ("queued",
                                                                              "running")

        def update():
            session, calc = self.session, self.item_id
            try:
                system = session.document.calculation(calc).system
            except (DocumentError, KeyError):    # removed: the form goes with the refresh
                return
            self.update_reports()                # its result line: queued, running, done
            # the state the tab, the plot's status row and the outliner read (ui/marks.py)
            state, progress = marks.calculation_state(session, calc)
            if state in ("queued", "running"):
                text = "queued, waiting for a worker" if state == "queued" else \
                    f"running, {marks.mark('running', progress)}" if progress else \
                    "running in a worker, no progress reported yet"
                button.setText("Cancel")
                button.setIcon(icons.icon("cancel"))
                button.setIconSize(icons.size())
                button.setToolTip(("take this job out of the queue" if state == "queued" else
                                   "stop this job; its worker is restarted")
                                  + f" ({shortcuts.text('cancel')})")
            else:
                cost_of = session.estimate(calc)
                problem = session.plan_calculation(calc).problem if cost_of is None else None
                if problem:                      # untrusted code, a parameter pyqula refuses
                    text = f"invalid: {problem}"
                elif cost_of is None and session.builds.get(system) is None:
                    text = f"estimate: once {system} is built"
                elif cost_of is None:            # a Python calculation declares no cost
                    text = "no estimate, so Run does not ask first"
                else:
                    text = "estimate: " + cost.describe(cost_of["seconds"]) + \
                        (" with the mean field" if cost_of["meanfield"] else "") + \
                        (", so Run asks first" if cost_of["seconds"] > cost.SLOW else "")
                button.setText("Run again" if state == "stale" else "Run")
                button.setIcon(icons.icon("run"))
                button.setIconSize(icons.size())
                button.setToolTip(
                    ("the model changed since this was computed: compute it again"
                     if state == "stale" else "compute it in a worker")
                    + f"; one that takes longer than {cost.SLOW:g} s asks first "
                      f"({shortcuts.text('run')})")
            estimate.setText(text)

        button.clicked.connect(lambda: self.commit("cancel", target=self.item_id)
                               if running() else self.commit("run", calculation=self.item_id))
        self.update_run = update
        update()


class RegionForm(Form):
    def __init__(self, panel, region_id):
        _, system, _, _, region = panel.session.document.find(region_id)
        super().__init__(panel, region_id, f"Region {region_id}",
                         "A named site selection; any term whose parameters take a function "
                         "of position can be restricted to it.")
        self.system_id = system.id
        self.select_kind = region.select.get("kind")
        self.name = QLineEdit()
        self.name.setObjectName("regionName")
        self.name.editingFinished.connect(self._rename)
        self.rows.addRow("name", self.name)
        self.rows.addRow("selection", QLabel(self.select_kind))
        self.expr = self.tol = None
        if self.select_kind == "expression":
            self.expr = QLineEdit()
            self.expr.setObjectName("edit_expr")
            self.expr.setToolTip("sites where this expression of x, y, z, r is true")
            self.expr.editingFinished.connect(self._set_expr)
            self.rows.addRow("sites where", self.expr)
        else:
            self.count = QLabel()
            self.rows.addRow("stored", self.count)
            self.tol = QLineEdit()
            self.tol.setObjectName("edit_tol")
            self.tol.editingFinished.connect(self._set_tol)
            self.rows.addRow("tolerance", self.tol)
        self.sites = QLabel()
        self.sites.setObjectName("regionSites")
        self.rows.addRow("sites now", self.sites)
        self.users = QLabel()
        self.rows.addRow("used by", self.users)
        self.show_sites = QPushButton("Select on canvas")
        self.show_sites.setObjectName("selectRegionSites")
        self.show_sites.setToolTip("select these sites on the Structure tab (e.g. to remove "
                                   "them, or to make a region by position from them)")
        self.show_sites.clicked.connect(self._select_sites)
        self.rows.addRow("", self.show_sites)
        self.guarded = [w for w in (self.name, self.expr, self.tol) if w is not None]
        self.update_values()

    def whole_locks(self):
        return [self.item_id, self.system_id]

    def _select_sites(self):
        region = self.session.document.find(self.item_id)[-1]
        build = self.session.builds.get(self.system_id)
        if build is None:
            self.error.setText("the geometry is not built yet")
            return
        try:
            mask = region_tools.evaluate_positions(region.select, build["positions"])
        except ValueError as error:          # RegionError, ExpressionError
            self.error.setText(str(error))
            return
        self.commit("select_sites", indices=[int(i) for i in mask.nonzero()[0]])

    def signature(self):
        region = self.session.document.find(self.item_id)[-1]
        return ("region", self.item_id, region.select.get("kind"))

    def update_values(self):
        _, system, _, _, region = self.session.document.find(self.item_id)
        _quiet(self.name, self.name.setText, region.name)
        if self.expr is not None:
            _quiet(self.expr, self.expr.setText, region.select["expr"])
        else:
            self.count.setText(f"{len(region.select['positions'])} positions")
            _quiet(self.tol, self.tol.setText, format_number(region.select["tol"]))
        self.update_reports()

    def update_reports(self):
        _, system, _, _, region = self.session.document.find(self.item_id)
        build = self.session.builds.get(self.system_id)
        if build is not None:
            try:
                n = int(region_tools.evaluate_positions(region.select, build["positions"]).sum())
                self.sites.setText(f"{n} of {build['sites']}")
            except Exception as error:
                self.sites.setText(str(error))
        users = [t.id for t in system.hamiltonian.terms if t.region == self.item_id] \
            if system.hamiltonian else []
        self.users.setText(", ".join(users) or "no term")

    def _rename(self):
        name = self.name.text().strip()
        if name and name != self.session.document.find(self.item_id)[-1].name:
            self.commit("rename", entry=self.item_id, name=name)

    def _set_expr(self):
        region = self.session.document.find(self.item_id)[-1]
        if self.expr.text().strip() != region.select["expr"]:
            self.commit("set_selection", entry=self.item_id,
                        select={"kind": "expression", "expr": self.expr.text()})

    def _set_tol(self):
        region = self.session.document.find(self.item_id)[-1]
        try:
            tol = float(self.tol.text())
        except ValueError:
            self.error.setText("tolerance: not a number")
            self.update_values()
            return
        if tol != region.select["tol"]:
            self.commit("set_selection", entry=self.item_id,
                        select=dict(region.select, tol=tol))


class MeanFieldForm(Form):
    """The mean-field block of a system (PLAN.md section 5), shown for the
    outliner row <system>/meanfield. The interactions beyond the first
    neighbours (FURTHER_NEIGHBOURS) are folded under the check box "further
    neighbours" (furtherNeighbours, over the frame of their rows,
    furtherNeighboursRows), checked whenever one of them is not zero:
    checking it shows them, and unchecking it sets them to zero (one undo
    step) and folds them."""
    previews = True

    def __init__(self, panel, item_id):
        self.system_id = system_of(item_id)
        system = panel.session.document.system(self.system_id)
        block = system.hamiltonian.meanfield
        self.kind = block.kind
        try:
            spec = registry.get("meanfield", block.kind)
        except registry.RegistryError as error:
            spec = None
            super().__init__(panel, item_id, f"Mean field {block.kind}", str(error).strip("\"'"))
        if spec is not None:
            super().__init__(panel, item_id, spec.label,
                             f"{self.system_id} · {spec.group}\n{spec.doc}")
            if spec.formula:
                self.layout().insertWidget(2, self._formula(spec.formula))
        self.add_enabled(lambda v: self.commit("set_meanfield", system=self.system_id,
                                               enabled=v))
        self.further = None
        if spec is not None:
            values = spec.normalize_params({}) | block.params

            def send(name, value):
                self.commit("set_meanfield", system=self.system_id, params={name: value})
            further = [p for p in spec.params if p.name in FURTHER_NEIGHBOURS]
            rest = [p for p in spec.params if p.name not in FURTHER_NEIGHBOURS]
            # the first neighbours' V and J right after U, then the folded ones
            first = [p for p in rest if p.name in ("U", "V1", "J1")] if further else []
            self.add_editors(first or rest, values, send, _regions(system))
            if further:
                # a check box over a framed group of rows: a checkable QGroupBox keeps its
                # empty frame when its rows are hidden
                self.further = QCheckBox("further neighbours")
                self.further.setObjectName("furtherNeighbours")
                self.further.setToolTip("V and J between second and third neighbours "
                                        f"({', '.join(p.name for p in further)}): checked, "
                                        f"they are shown; unchecked, they are zero")
                inner = QFrame()
                inner.setObjectName("furtherNeighboursRows")
                inner.setFrameShape(QFrame.Shape.StyledPanel)
                rows = QFormLayout(inner)
                rows.setContentsMargins(6, 4, 6, 4)
                rows.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                self.further_rows = inner
                self.add_editors(further, values, send, _regions(system), rows=rows)
                self.rows.addRow(self.further)
                self.rows.addRow(inner)
                self.further.toggled.connect(self._fold_further)
                self.add_editors([p for p in rest if p not in first], values, send,
                                 _regions(system))
                self._show_further(self._further_set(block.params))
            self.guarded = [self.further] if self.further is not None else []
        self.status = QLabel()
        self.status.setObjectName("meanfieldStatus")
        self.status.setWordWrap(True)
        self.layout().insertWidget(self.layout().count() - 2, self.status)
        self.update_values()

    def signature(self):
        system = self.session.document.system(self.system_id)
        return ("meanfield", self.system_id, system.hamiltonian.meanfield.kind, _regions(system))

    def update_values(self):
        block = self.session.document.system(self.system_id).hamiltonian.meanfield
        _quiet(self.enabled, self.enabled.setChecked, block.enabled)
        for name, editor in self.editors.items():
            if name in block.params:
                editor.set_value(block.params[name])
        line_up(self.editors.values())
        if self.further is not None and self._further_set(block.params):
            self._show_further(True)          # a value is never hidden
        self.update_reports()

    @staticmethod
    def _further_set(params):
        """Whether an interaction beyond the first neighbours is not zero."""
        return any(params.get(name, 0.0) != 0.0 for name in FURTHER_NEIGHBOURS)

    def _show_further(self, shown):
        _quiet(self.further, self.further.setChecked, shown)
        self._unfold(shown)

    def _unfold(self, shown):
        self.further_rows.setVisible(shown)

    def _fold_further(self, shown):
        """The group's check box: shown, the rows unfold; hidden, the further
        neighbours are set to zero in one step (refused under a lock, when
        the group shows them again)."""
        block = self.session.document.system(self.system_id).hamiltonian.meanfield
        if not shown and self._further_set(block.params):
            zero = {p: 0.0 for p in FURTHER_NEIGHBOURS if p in self.editors}
            if not self.commit("set_meanfield", system=self.system_id, params=zero):
                self._show_further(True)
                return
        self._unfold(shown)

    def update_reports(self):
        self.status.setText(self._status())

    def _status(self):
        session = self.session
        try:
            stage = session.plan_system(self.system_id).meanfield
        except (KeyError, DocumentError):
            return ""
        if not stage.enabled:
            return "off: the calculations use the Hamiltonian of the terms"
        if stage.problem:
            return f"invalid, skipped: {stage.problem}"
        text = (f"runs with every calculation on {self.system_id}, not while editing (the "
                f"structure shows the Hamiltonian before it)")
        for calc in session.document.calculations:
            result = session.result(calc.id)
            if calc.system == self.system_id and result is not None and result.meanfield \
                    and not session.is_stale(calc.id):
                energy = result.meanfield.get("total_energy")
                text += f"\nconverged for {calc.id}: total energy {energy:.6g}"
                break
        return text


class ModelForm(Form):
    """A classical system's model (decision 13.5), shown for the outliner
    row <system>/model: its set-up parameters."""

    def __init__(self, panel, item_id):
        self.system_id = system_of(item_id)
        model = panel.session.document.system(self.system_id).model
        self.kind = model.kind
        try:
            spec = registry.get("model", model.kind)
        except registry.RegistryError as error:
            spec = None
            super().__init__(panel, item_id, f"Model {model.kind}", str(error).strip("\"'"))
        if spec is not None:
            super().__init__(panel, item_id, spec.label,
                             f"{self.system_id} · {spec.group}\n{spec.doc}")
            self.add_editors(spec.params, spec.normalize_params({}) | model.params,
                             lambda name, value: self.commit(
                                 "set_model", system=self.system_id, params={name: value}))
        self.update_values()

    def signature(self):
        return ("model", self.system_id, self.session.document.system(self.system_id).model.kind)

    def update_values(self):
        model = self.session.document.system(self.system_id).model
        for name, editor in self.editors.items():
            if name in model.params:
                editor.set_value(model.params[name])
        line_up(self.editors.values())


class PropertiesPanel(QWidget):
    """The Properties panel: the form of the selected item in a scrolled
    area and, under it, the footer, where a calculation's form puts its
    estimate and its Run (the form's run_row), so that Run stays in sight
    however long the form is (PLAN.md phase 8, package P8)."""
    preview = Signal(str, str)        # entry (or <system>/meanfield), parameter name
    help_requested = Signal(str)      # the ? of a form: the item whose help to show
    regions_requested = Signal(str, object)   # a term's region link: system, global QPoint

    def __init__(self, run, parent=None):
        super().__init__(parent)
        self.setObjectName("properties")
        self.setMinimumWidth(280)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("propertiesScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.footer = QFrame()
        self.footer.setObjectName("propertiesFooter")
        self.footer.setFrameShape(QFrame.Shape.NoFrame)
        line = QVBoxLayout(self.footer)
        line.setContentsMargins(9, 4, 9, 6)
        self.footer.hide()                         # shown with a run row
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.footer)
        self.run = run
        self.session = None
        self.item_id = ""
        self.form = None
        self._signature = None
        self._set_form(EmptyForm(self))

    def verticalScrollBar(self):
        """The scroll bar of the form (shown when it is taller than the panel)."""
        return self.scroll.verticalScrollBar()

    def _set_form(self, form):
        """Replace the form; the old one is deleted later, since this may
        run inside a signal of one of its own editors. A form's run_row goes
        in the footer."""
        shown = self.form
        old = self.scroll.takeWidget()
        if old is not None:
            old.hide()
            old.deleteLater()
        if self.form is not shown:
            # taking the old form out took the focus from its editor, which sent what
            # was typed there: that edit already set a form built after it, and this
            # one, built before, would show the value it replaced
            form.deleteLater()
            return
        self.form = form
        footer = self.footer.layout()
        while footer.count():
            row = footer.takeAt(0).widget()
            if row is not None:
                row.hide()
                row.setParent(None)         # gone from findChild at once
                row.deleteLater()
        row = getattr(form, "run_row", None)
        if row is not None:
            footer.addWidget(row)
            row.show()
        self.footer.setVisible(row is not None)
        self.scroll.setWidget(form)

    def _make(self, item_id):
        document = self.session.document
        if not item_id or item_id == "calculations":
            return EmptyForm(self)
        if item_id.endswith("/meanfield"):
            return MeanFieldForm(self, item_id)
        if item_id.endswith("/model"):
            return ModelForm(self, item_id)
        system = system_of(item_id)
        if system is not None:
            return SystemForm(self, system)
        family = document.find(item_id)[0]
        if family == "system":
            return SystemForm(self, item_id)
        if family == "region":
            return RegionForm(self, item_id)
        return EntryForm(self, item_id)

    def show_item(self, session, item_id):
        self.session = session
        self.item_id = item_id
        try:
            form = self._make(item_id)
        except DocumentError:
            self.item_id = ""
            form = EmptyForm(self)
        self._set_form(form)
        self._signature = self._current_signature()
        self._apply_locks()

    def _apply_locks(self):
        try:
            self.form.apply_locks()
        except (DocumentError, KeyError, AttributeError):
            pass

    def _current_signature(self):
        try:
            return self.form.signature()
        except (DocumentError, KeyError):
            return None

    def refresh(self, values=True):
        """After a document change (values: the editors show the Document
        again), or a finished build or run (values false: only what they
        report changes, and text being typed must stay)."""
        if self.session is None:
            return
        signature = self._current_signature()
        if signature is None or signature != self._signature:
            self.show_item(self.session, self.item_id if signature is not None else "")
            return
        if values:
            self.form.update_values()
        else:
            self.form.update_reports()
        self._apply_locks()
