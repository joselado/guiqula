"""The properties panel (PLAN.md section 4): the form of whatever the
outliner has selected, generated from its registry declaration (PLAN.md
3.2). Every edit is sent as a command through the window's ``run``
(name, **args) -> (ok, result or message); a refusal is shown under the
form and the editor goes back to the stored value.

After a document change the panel refreshes: if the selected entry still
has the same shape (same kind, same regions to choose from) the values are
updated in place, so an editor in use is never destroyed under the mouse;
otherwise the form is rebuilt.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from guiqula.core import regions as region_tools
from guiqula.core.document import DocumentError
from guiqula.registry import base as registry
from guiqula.registry import pipeline
from guiqula.ui import formulas
from guiqula.ui.forms import format_number, make_editor
from guiqula.ui.outliner import system_of

EVERYWHERE = "(everywhere)"
FAMILY = {"op": "geometry_op", "term": "term", "calculation": "calculation"}


def _quiet(widget, setter, value):
    widget.blockSignals(True)
    try:
        setter(value)
    finally:
        widget.blockSignals(False)


class Form(QWidget):
    def __init__(self, panel, item_id, title, doc=""):
        super().__init__()
        self.panel = panel
        self.item_id = item_id
        layout = QVBoxLayout(self)
        self.title = QLabel(title)
        self.title.setObjectName("formTitle")
        self.doc = QLabel(doc)
        self.doc.setObjectName("formDoc")
        self.doc.setWordWrap(True)
        self.doc.setVisible(bool(doc))
        self.rows = QFormLayout()
        self.rows.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.error = QLabel("")
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.title)
        layout.addWidget(self.doc)
        layout.addLayout(self.rows)
        layout.addWidget(self.error)
        layout.addStretch(1)
        self.editors = {}

    @property
    def session(self):
        return self.panel.session

    def signature(self):
        return (self.item_id,)

    def update_values(self):
        pass

    def commit(self, command, /, **args):
        ok, out = self.panel.run(command, **args)
        self.error.setText("" if ok else str(out))
        if not ok:
            self.update_values()
        return ok

    def add_editors(self, params, values, send):
        """One editor per parameter; send(name, value) commits it."""
        for param in params:
            editor = make_editor(param, getattr(self.session.jobs, "names", {}))
            editor.set_value(values[param.name])
            editor.committed.connect(lambda p=param, e=editor: self._send(e, p, send))
            self.rows.addRow(param.label, editor)
            self.editors[param.name] = editor

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
            self.add_editors(spec.params, system.geometry.base.params, lambda name, value:
                             self.commit("set_param", entry=system_id, name=name, value=value))
        except registry.RegistryError:
            pass
        if system.hamiltonian is not None:
            box = QGroupBox("Hamiltonian construction")
            form = QFormLayout(box)
            self.has_spin, self.nambu, self.sparse = QCheckBox(), QCheckBox(), QCheckBox()
            self.tij = QLineEdit()
            for widget, name in ((self.has_spin, "has_spin"), (self.nambu, "nambu"),
                                 (self.sparse, "is_sparse"), (self.tij, "tij")):
                widget.setObjectName(f"construction_{name}")
            self.has_spin.toggled.connect(lambda v: self.commit(
                "set_construction", system=system_id, has_spin=v))
            self.nambu.toggled.connect(lambda v: self.commit(
                "set_construction", system=system_id, nambu=v))
            self.sparse.toggled.connect(lambda v: self.commit(
                "set_construction", system=system_id, is_sparse=v))
            self.tij.editingFinished.connect(self._set_tij)
            self.tij.setToolTip("hoppings to first, second, ... neighbours, comma separated")
            form.addRow("spinful (requested)", self.has_spin)
            form.addRow("Nambu (requested)", self.nambu)
            form.addRow("neighbour hoppings", self.tij)
            form.addRow("sparse", self.sparse)
            self.layout().insertWidget(3, box)
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
            editor.set_value(system.geometry.base.params[name])
        if system.hamiltonian is not None:
            c = system.hamiltonian.construction
            _quiet(self.has_spin, self.has_spin.setChecked, c.has_spin)
            _quiet(self.nambu, self.nambu.setChecked, c.nambu)
            _quiet(self.sparse, self.sparse.setChecked, c.is_sparse)
            _quiet(self.tij, self.tij.setText, ", ".join(format_number(t) for t in c.tij))
        self.info.setText(self._info())

    def _info(self):
        session, system_id = self.session, self.system_id
        if system_id in session.build_errors:
            return f"cannot be built: {session.build_errors[system_id]}"
        build = session.builds.get(system_id)
        if build is None:
            return "building…"
        plan = pipeline.plan_system(session.document, system_id)
        text = (f"{build['dimensionality']}D · {build['sites']} sites · {plan.mode} · "
                f"Hilbert dimension {build['dimension']}")
        if plan.upgraded_by:
            text += f"\n{plan.mode} because of {', '.join(plan.upgraded_by)}"
        return text + ("" if session.build_is_current(system_id) else "\n(updating…)")

    def _rename(self):
        name = self.name.text().strip()
        if name and name != self.session.document.system(self.system_id).name:
            self.commit("rename", entry=self.system_id, name=name)

    def _set_lattice(self, index):
        kind = self.lattice.itemData(index)
        if kind != self.session.document.system(self.system_id).geometry.base.kind:
            self.commit("set_lattice", system=self.system_id, lattice=kind)

    def _set_tij(self):
        try:
            tij = [float(t) for t in self.tij.text().replace(";", ",").split(",") if t.strip()]
        except ValueError:
            self.error.setText("neighbour hoppings: a comma separated list of numbers")
            self.update_values()
            return
        if tij != self.session.document.system(self.system_id).hamiltonian.construction.tij:
            self.commit("set_construction", system=self.system_id, tij=tij)


class EntryForm(Form):
    """A geometry op, a term or a calculation."""

    def __init__(self, panel, entry_id):
        family, owner, _, _, obj = panel.session.document.find(entry_id)
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
        self.enabled = None
        if family in ("op", "term"):
            self.enabled = QCheckBox("enabled")
            self.enabled.setObjectName("check_enabled")
            self.enabled.toggled.connect(lambda v: self.commit("set_enabled", entry=entry_id,
                                                               enabled=v))
            self.rows.addRow("", self.enabled)
        self.region = None
        self.region_ids = ()
        if family == "term":
            self.region = QComboBox()
            self.region.setObjectName("regionBox")
            self.region.addItem(EVERYWHERE, None)
            for region in owner.regions:
                self.region.addItem(f"{region.id}  {region.name}", region.id)
            self.region_ids = tuple(r.id for r in owner.regions)
            self.region.activated.connect(self._set_region)
            self.rows.addRow("region", self.region)
        if family == "calculation":
            self.rows.addRow("system", QLabel(obj.system))
        if spec is not None:
            self.add_editors(spec.params, spec.normalize_params({}) | obj.params,
                             lambda name, value: self.commit("set_param", entry=entry_id,
                                                             name=name, value=value))
        self.status = QLabel()
        self.status.setObjectName("entryStatus")
        self.status.setWordWrap(True)
        self.layout().insertWidget(self.layout().count() - 2, self.status)
        self.update_values()

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

    def signature(self):
        found = self.session.document.find(self.item_id)
        regions = tuple(r.id for r in found[1].regions) if found[0] == "term" else ()
        return (self.family, self.item_id, found[-1].kind, regions)

    def update_values(self):
        obj = self.session.document.find(self.item_id)[-1]
        if self.enabled is not None:
            _quiet(self.enabled, self.enabled.setChecked, obj.enabled)
        if self.region is not None:
            _quiet(self.region, self.region.setCurrentIndex, self.region.findData(obj.region))
        for name, editor in self.editors.items():
            if name in obj.params:
                editor.set_value(obj.params[name])
        self.status.setText(self._status())

    def _status(self):
        session = self.session
        if self.family == "calculation":
            return f"result: {session.status(self.item_id)}"
        try:
            stage = pipeline.plan_system(session.document, self.system_id).stage(self.item_id)
        except (KeyError, DocumentError):
            return ""
        if stage.problem:
            return f"invalid, skipped: {stage.problem}"
        build = session.builds.get(self.system_id)
        if build is not None and session.build_is_current(self.system_id):
            for report in build["reports"]:
                if report["id"] == self.item_id:
                    if report["status"] == "invalid":
                        return f"pyqula refused it, skipped: {report['message']}"
                    if report.get("mode"):
                        return f"Hilbert space after it: {report['mode']}"
        return ""

    def _set_region(self, index):
        region = self.region.itemData(index)
        self.commit("set_region", entry=self.item_id, region=region)


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
        self.update_values()

    def _select_sites(self):
        region = self.session.document.find(self.item_id)[-1]
        build = self.session.builds.get(self.system_id)
        if build is None:
            self.error.setText("the geometry is not built yet")
            return
        mask = region_tools.evaluate_positions(region.select, build["positions"])
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


class PropertiesPanel(QScrollArea):
    def __init__(self, run, parent=None):
        super().__init__(parent)
        self.setObjectName("properties")
        self.setWidgetResizable(True)
        self.setMinimumWidth(280)
        self.run = run
        self.session = None
        self.item_id = ""
        self.form = None
        self._signature = None
        self._set_form(EmptyForm(self))

    def _set_form(self, form):
        """Replace the form; the old one is deleted later, since this may
        run inside a signal of one of its own editors."""
        old = self.takeWidget()
        self.form = form
        self.setWidget(form)
        if old is not None:
            old.hide()
            old.deleteLater()

    def _make(self, item_id):
        document = self.session.document
        if not item_id or item_id == "calculations":
            return EmptyForm(self)
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

    def _current_signature(self):
        try:
            return self.form.signature()
        except (DocumentError, KeyError):
            return None

    def refresh(self):
        """After a document change or a finished build."""
        if self.session is None:
            return
        signature = self._current_signature()
        if signature is None or signature != self._signature:
            self.show_item(self.session, self.item_id if signature is not None else "")
            return
        self.form.update_values()
