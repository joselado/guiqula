"""The outliner (PLAN.md section 4): the whole Document as one tree. One
node per system with its Geometry stack (the base lattice, then the ops),
its Regions and its Hamiltonian (the terms, each with the Hilbert space
after it), then the Calculations with their result status.

Ops and terms carry a checkbox (enabled); an invalid entry is marked ✗ in
red with the planner's or pyqula's message (decision 14.3). Everything the
outliner changes goes out as a command (name, args) for the window to run
through the dispatcher; it never touches the Document itself.

Items carry the id of what they show: an entry id (s1, op2, t3, r1, c2),
or ``<system>/base``, ``<system>/geometry``, ``<system>/regions``,
``<system>/hamiltonian`` for the rows of a system that are not entries, and
``calculations``.
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence
from PySide6.QtWidgets import QInputDialog, QMenu, QTreeWidget, QTreeWidgetItem

from guiqula.core import regions as region_tools
from guiqula.registry import base as registry
from guiqula.registry import pipeline
from guiqula.ui import theme

ID_ROLE = Qt.ItemDataRole.UserRole
INVALID = "✗ "


def system_of(item_id):
    """The system part of a pseudo id (s1/base -> s1), else None."""
    return item_id.split("/", 1)[0] if "/" in item_id else None


def _label(family, kind):
    try:
        return registry.get(family, kind).label
    except registry.RegistryError:
        return kind


def _summary(params, limit=40):
    parts = []
    for name, value in params.items():
        if isinstance(value, list) and value and isinstance(value[0], list):
            parts.append(f"{len(value)} positions")
        elif isinstance(value, bool):
            parts.append(name if value else f"no {name}")
        else:
            parts.append(f"{name} {value}")
    text = ", ".join(parts)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _selection_text(select):
    if select.get("kind") == "expression":
        return select["expr"]
    if select.get("kind") == "positions":
        return f"{len(select.get('positions', []))} positions"
    return str(select.get("kind"))


class Outliner(QTreeWidget):
    selected = Signal(str)              # item id ("" for none)
    command = Signal(str, object)       # mutation or action name, args dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("outliner")
        self.setHeaderLabels(["entry", "status"])
        self.setColumnWidth(0, 230)
        self.setUniformRowHeights(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.currentItemChanged.connect(self._current_changed)
        self.itemChanged.connect(self._item_changed)
        self._session = None
        self._items = {}
        self._refreshing = False
        for text, shortcut, slot in (("Delete", QKeySequence.StandardKey.Delete, self.delete_current),
                                     ("Duplicate", "Ctrl+D", self.duplicate_current),
                                     ("Move up", "Alt+Up", lambda: self.move_current(-1)),
                                     ("Move down", "Alt+Down", lambda: self.move_current(1))):
            action = QAction(text, self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
            action.triggered.connect(slot)
            self.addAction(action)

    # ---- state
    def current_id(self):
        item = self.currentItem()
        return item.data(0, ID_ROLE) if item is not None else ""

    def item(self, item_id):
        return self._items.get(item_id)

    def set_current(self, item_id):
        """Select a row without emitting selected (the window drives this)."""
        item = self._items.get(item_id)
        self.blockSignals(True)
        try:
            self.setCurrentItem(item) if item is not None else self.setCurrentItem(None)
        finally:
            self.blockSignals(False)

    def _add(self, parent, item_id, texts, tooltip=None):
        item = QTreeWidgetItem(parent, list(texts)) if parent is not None \
            else QTreeWidgetItem(list(texts))
        if parent is None:
            self.addTopLevelItem(item)
        item.setData(0, ID_ROLE, item_id)
        if tooltip:
            item.setToolTip(0, tooltip)
            item.setToolTip(1, tooltip)
        self._items[item_id] = item
        return item

    # ---- building
    def refresh(self, session):
        self._session = session
        current = self.current_id()
        collapsed = {i for i, item in self._items.items() if not item.isExpanded()}
        scroll = self.verticalScrollBar().value()
        self._refreshing = True
        self.blockSignals(True)
        try:
            self.clear()
            self._items = {}
            document = session.document
            for system in document.systems:
                self._add_system(session, system)
            calcs = self._add(None, "calculations", ["Calculations", ""])
            for calc in document.calculations:
                self._add_calculation(session, calcs, calc)
            self.expandAll()
            for item_id in collapsed & set(self._items):
                self._items[item_id].setExpanded(False)
            if current in self._items:
                self.setCurrentItem(self._items[current])
        finally:
            self.blockSignals(False)
            self._refreshing = False
        self.verticalScrollBar().setValue(scroll)

    def _add_system(self, session, system):
        document = session.document
        build = session.builds.get(system.id)
        current = session.build_is_current(system.id)
        runtime = {r["id"]: r for r in build["reports"]} if build and current else {}
        info = [system.kind]
        if build:
            info += [f"{build['dimensionality']}D", f"{build['sites']} sites"]
        top = self._add(None, system.id, [f"{system.id}  {system.name}", " · ".join(info)])
        font = top.font(0)
        font.setBold(True)
        top.setFont(0, font)
        try:
            plan = pipeline.plan_system(document, system.id)
        except Exception as error:     # a broken document still displays
            self._add(top, f"{system.id}/problem", [INVALID + "cannot plan", str(error)])
            return
        if build is not None and not current:
            top.setText(1, top.text(1) + " · building…")
        if system.id in session.build_errors:
            top.setText(1, INVALID + session.build_errors[system.id])
            top.setToolTip(1, session.build_errors[system.id])
        stages = {s.id: s for s in plan.stages if s.id}

        geometry = self._add(top, f"{system.id}/geometry", ["Geometry", ""])
        base = plan.stages[0]
        base_item = self._add(geometry, f"{system.id}/base",
                              [_label("lattice", base.kind), "base lattice"])
        if base.problem:
            self._mark_invalid(base_item, base.problem)
        for op in system.geometry.ops:
            self._add_entry(geometry, op, "geometry_op", stages[op.id], runtime.get(op.id),
                            _summary(op.params))

        positions = build["positions"] if build is not None and current else None
        regions = self._add(top, f"{system.id}/regions", ["Regions", str(len(system.regions))])
        for region in system.regions:
            text = _selection_text(region.select)
            if positions is not None:
                try:
                    count = int(region_tools.evaluate_positions(region.select, positions).sum())
                    text += f" · {count} sites"
                except Exception as error:
                    text = INVALID + str(error)
            self._add(regions, region.id, [f"{region.id}  {region.name}", text])

        if system.hamiltonian is None:
            return
        mode = plan.mode + (f" (upgraded by {', '.join(plan.upgraded_by)})"
                            if plan.upgraded_by else "")
        hamiltonian = self._add(top, f"{system.id}/hamiltonian", ["Hamiltonian", mode])
        for term in system.hamiltonian.terms:
            report = runtime.get(term.id)
            status = "→ " + report["mode"] if report and report.get("mode") else ""
            if term.region:
                status += f" · in {term.region}"
            self._add_entry(hamiltonian, term, "term", stages[term.id], report, status.strip())

    def _add_entry(self, parent, entry, family, stage, report, status):
        item = self._add(parent, entry.id, [f"{entry.id}  {_label(family, entry.kind)}", status])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked if entry.enabled else Qt.CheckState.Unchecked)
        message = stage.problem
        if report is not None and report["status"] == "invalid":
            message = report["message"]
        if not entry.enabled:
            for column in (0, 1):
                item.setForeground(column, QBrush(QColor(theme.DISABLED)))
            item.setText(1, "disabled")
        elif message:
            self._mark_invalid(item, message)
        return item

    def _mark_invalid(self, item, message):
        item.setText(0, INVALID + item.text(0))
        item.setText(1, message)
        for column in (0, 1):
            item.setForeground(column, QBrush(QColor(theme.ERROR)))
            item.setToolTip(column, message)

    def _add_calculation(self, session, parent, calc):
        status = session.status(calc.id)
        job = session.calc_jobs.get(calc.id)
        if job is not None and status == "running":
            status = f"running {job.progress:.0%}"
        elif job is not None and status == "failed":
            status = f"failed: {job.error}"
        item = self._add(parent, calc.id,
                         [f"{calc.id}  {_label('calculation', calc.kind)} on {calc.system}", status],
                         tooltip=job.error if job is not None and job.error else None)
        if status.startswith("failed"):
            item.setForeground(1, QBrush(QColor(theme.ERROR)))
        elif status == "stale":
            item.setForeground(1, QBrush(QColor(theme.DISABLED)))

    # ---- interaction
    def _current_changed(self, current, previous):
        self.selected.emit(current.data(0, ID_ROLE) if current is not None else "")

    def _item_changed(self, item, column):
        if self._refreshing or column != 0 or not item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            return
        args = {"entry": item.data(0, ID_ROLE),
                "enabled": item.checkState(0) == Qt.CheckState.Checked}
        # the command rebuilds the tree, which deletes this item: not inside its own signal
        QTimer.singleShot(0, lambda: self.command.emit("set_enabled", args))

    def _family(self, item_id):
        if self._session is None or not item_id or "/" in item_id or item_id == "calculations":
            return None
        try:
            return self._session.document.find(item_id)
        except Exception:
            return None

    def delete_current(self):
        if self._family(self.current_id()):
            self.command.emit("remove", {"entry": self.current_id()})

    def duplicate_current(self):
        if self._family(self.current_id()):
            self.command.emit("duplicate", {"entry": self.current_id()})

    def move_current(self, step):
        found = self._family(self.current_id())
        if found is None or found[0] == "system":
            return
        _, _, items, index, _ = found
        if 0 <= index + step < len(items):
            self.command.emit("move", {"entry": self.current_id(), "index": index + step})

    def rename_current(self):
        found = self._family(self.current_id())
        if found is None or found[0] not in ("system", "region"):
            return
        name, ok = QInputDialog.getText(self, "Rename", "Name:", text=found[-1].name)
        if ok and name.strip():
            self.command.emit("rename", {"entry": self.current_id(), "name": name.strip()})

    def _context_menu(self, point):
        item = self.itemAt(point)
        if item is None:
            return
        self.setCurrentItem(item)
        found = self._family(item.data(0, ID_ROLE))
        if found is None:
            return
        family, obj = found[0], found[-1]
        menu = QMenu(self)
        if family in ("op", "term"):
            menu.addAction("Disable" if obj.enabled else "Enable", lambda: self.command.emit(
                "set_enabled", {"entry": obj.id, "enabled": not obj.enabled}))
        if family == "calculation":
            menu.addAction("Run", lambda: self.command.emit("run_calculation",
                                                            {"calculation": obj.id}))
        if family in ("system", "region"):
            menu.addAction("Rename...", self.rename_current)
        menu.addAction("Duplicate", self.duplicate_current)
        if family != "system":
            menu.addAction("Move up", lambda: self.move_current(-1))
            menu.addAction("Move down", lambda: self.move_current(1))
        menu.addSeparator()
        menu.addAction("Delete", self.delete_current)
        menu.popup(self.viewport().mapToGlobal(point))
