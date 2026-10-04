"""The outliner (PLAN.md section 4): the whole Document as one tree. One
node per system with its Geometry stack (the base lattice, then the ops),
its Regions and its Hamiltonian (the terms, each with the Hilbert space
after it), then the Calculations with their result status.

Ops and terms carry a checkbox (enabled). Ops, terms, regions and
calculations are reordered by dragging them within their own list (or with
Alt+arrows). Everything the outliner changes goes out as a command (name,
args) for the window to run through the dispatcher; it never touches the
Document itself, and Qt never moves an item: the tree is rebuilt from the
Document after the move command.

Items carry the id of what they show: an entry id (s1, op2, t3, r1, c2),
or ``<system>/base``, ``<system>/geometry``, ``<system>/regions``,
``<system>/hamiltonian``, ``<system>/meanfield`` (``<system>/model_stack``,
``<system>/model`` for a classical system) for the rows of a system that
are not entries (pseudo_ids), and ``calculations``. The mean-field row
closes the Hamiltonian's list, with its own checkbox (set_meanfield).

The section rows (a system's Geometry, Regions, Hamiltonian or Model, and
Calculations) carry a "+" at the right of their status cell (PLAN.md phase
8, package P2): add_requested says which section, and the window opens the
Add menu of that family for that system there (add_button(path) gives the
button; outlinerAdd_<system>_geometry, _regions, _hamiltonian, _model and
outlinerAdd_calculations). The rest of the cell is left to the row, so a
click there selects it as before.

What a row is and in what state (package P7). The Entry column says what
the row is: the id and the kind, then the name, an op's parameters, a
region's selection or the region a term is restricted to, which an
elision cuts first. The Status column holds the state only, in the marks
of ui/marks.py that the result tabs and the plots' status row share: done,
stale, a running job's progress, failed and invalid in the error colour,
disabled, locked, and a warning; besides them the Hilbert space after a
term, a region's number of sites and a scalar result's value. It is sized
to its longest text (status_width) and the Entry column takes the rest,
so no status is ever cut and every "+" stays in sight. Two rows say more
than a state: a system's summary ("2D · 8 sites · spinful") and the mean
field's interactions when it is on ("U = 3, runs with the calculations").
They are detail rows (DETAIL_ROLE): they span both columns and read their
status after the label when both fit, and under it, wrapped, when they do
not, so that they are never cut either. Every row's tooltip is its full
label and its state in words, with the messages (why an entry is invalid,
why a job failed, what a warning means).
"""
import math

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QFontMetrics, QFontMetricsF, QPalette,
                           QRegion)
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QInputDialog, QMenu, QStyle,
                               QStyledItemDelegate, QStyleOptionViewItem, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QWidget)

from guiqula.core import regions as region_tools
from guiqula.registry import base as registry
from guiqula.ui import marks, shortcuts, theme
from guiqula.ui.plots import scalar_rows

ID_ROLE = Qt.ItemDataRole.UserRole
ADD_ROLE = Qt.ItemDataRole.UserRole + 1      # the path of a section row's "+", in its status
# a row whose status reads after or under its label, across both columns (in its column 0)
DETAIL_ROLE = Qt.ItemDataRole.UserRole + 2
MOVABLE = ("op", "term", "region", "calculation")
# the rows of a system that carry a "+", and the name of their section in a path
ADD_SECTIONS = {"geometry": "geometry", "regions": "regions", "hamiltonian": "hamiltonian",
                "model_stack": "model"}
ADD_TIPS = {"geometry": "add a geometry op to {system} (a supercell, a ribbon, an island, "
                        "cuts, strain...), applied after the others",
            "regions": "add a region to {system}: the sites where an expression of the "
                       "position holds, or the sites selected on the canvas",
            "hamiltonian": "add a term to the Hamiltonian of {system}, applied after the "
                           "others, or turn on its mean field",
            "model": "add a term to the model of {system}, applied after the others",
            "calculations": "add a calculation on the current system ({run} runs the selected "
                            "one)"}
ADD_ROOM = 26                # the least room of a "+" in its status cell, in pixels
TEXT_GAP = 12                # pixels between a detail row's label and its status on one line
DETAIL_PAD = 3               # pixels below the status of a detail row read under its label
SCALAR_CHARS = 16            # characters of a scalar result's value shown in its status
MODE_WORDS = {"nambu": "Nambu"}       # the Hilbert space as the tree says it
LOCK_TIP = "locked ({lock}): unlock it from the context menu or with Edit > Unlock everything"
CALCULATION_WORDS = {
    "none": "not run yet: Run computes it",
    "queued": "queued: it starts when a worker is free",
    "done": "done: the result is up to date",
    "stale": "stale: the document changed since it ran, run it again",
    "cancelled": "cancelled before it ended",
}


def drop_index(old, target, below):
    """The index to give move() so that the entry at old lands just above
    (or below) the entry at target, both indices of the same list."""
    before = target + (1 if below else 0)
    return before - 1 if old < before else before


def list_heads(family, system):
    """Rows a drop onto means "to the top of the list" for this family."""
    return {"op": {f"{system}/geometry", f"{system}/base"},
            "term": {f"{system}/hamiltonian", f"{system}/model_stack", f"{system}/model"},
            "region": {f"{system}/regions"}, "calculation": {"calculations"}}[family]


def system_of(item_id):
    """The system part of a pseudo id (s1/base -> s1), else None."""
    return item_id.split("/", 1)[0] if "/" in item_id else None


def pseudo_ids(system):
    """The rows of a system that are not entries: a quantum system has a
    Hamiltonian and its mean field, a classical one a model."""
    rows = ["geometry", "base", "regions", "problem"]
    if system.hamiltonian is not None:
        rows += ["hamiltonian", "meanfield"]
    if system.model is not None:
        rows += ["model_stack", "model"]
    return {f"{system.id}/{row}" for row in rows}


def _label(family, kind):
    try:
        return registry.get(family, kind).label
    except registry.RegistryError:
        return kind


def _code_summary(code):
    """The first line of code that is not a comment, or "(comments only)"."""
    lines = [line.strip() for line in code.splitlines()]
    return next((line for line in lines if line and not line.startswith("#")),
                "(comments only)")


def _short(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _number(value):
    """A parameter's value as the tree prints it: 0.333333, not 0.3333333333333333."""
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list) and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                       for v in value):
        return "[" + ", ".join(_number(v) for v in value) + "]"
    return str(value)


def _summary(params, limit=40):
    parts = []
    for name, value in params.items():
        if name == "code" and isinstance(value, str):
            parts.append(_code_summary(value))
        elif isinstance(value, list) and value and isinstance(value[0], list):
            parts.append(f"{len(value)} positions")
        elif isinstance(value, bool):
            parts.append(name if value else f"no {name}")
        else:
            parts.append(f"{name} {_number(value)}")
    return _short(", ".join(parts), limit)


def _selection_text(select):
    if select.get("kind") == "expression":
        return select["expr"]
    if select.get("kind") == "positions":
        return f"{len(select.get('positions', []))} positions"
    return str(select.get("kind"))


def _entry_text(entry_id, label, *more):
    """ "t1  Zeeman / exchange field · name · in r1": the id and the kind first,
    so that an elision cuts the rest."""
    head = f"{entry_id}  {label}" if label else entry_id
    return " · ".join([head] + [part for part in more if part])


def _sites(count):
    return f"{count} site" if count == 1 else f"{count} sites"


def _mode(mode):
    return MODE_WORDS.get(mode, mode)


def _interactions(params):
    """ "U = 3" or "U = 3, J1 = 0.5": the interactions of a mean-field block
    that are on (a Field of position reads f(r)); "" for another kind."""
    from guiqula.registry.meanfield import INTERACTIONS   # registry loaded: no cost
    parts = []
    for name in INTERACTIONS:
        value = params.get(name)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            if value != 0:
                parts.append(f"{name} = {value:g}")
        else:
            parts.append(f"{name} = f(r)")
    if not parts and "U" in params:
        parts.append("U = 0")
    return ", ".join(parts)


def text_margin(widget):
    """The pixels an item view leaves on each side of a cell's text."""
    return widget.style().pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, widget) + 1


def text_width(font, text):
    """The pixels a text takes, rounded up as Qt's item views lay it out
    (they elide a text a fraction of a pixel too wide)."""
    return math.ceil(QFontMetricsF(font).horizontalAdvance(text)) + 1 if text else 0


def wrapped(font, text, width):
    """A detail row's status broken into lines of at most width pixels: at
    the spaces, and inside a word only when the word alone is wider than the
    line (large text in a narrow outliner), so that no word is cut at the
    edge. The lines are joined by newlines, drawn and measured as they are."""
    lines, line = [], ""
    for word in text.split():
        joined = f"{line} {word}" if line else word
        if text_width(font, joined) <= width:
            line = joined
            continue
        if line:
            lines.append(line)
        while len(word) > 1 and text_width(font, word) > width:
            n = len(word) - 1
            while n > 1 and text_width(font, word[:n]) > width:
                n -= 1
            lines.append(word[:n])
            word = word[n:]
        line = word
    return "\n".join(lines + ([line] if line else []))


def add_room(height):
    """The pixels the "+" of a section row takes at the right of its status
    cell: the button is as wide as the row is high, plus 4."""
    return max(ADD_ROOM, height + 4)


class AddCell(QWidget):
    """The status cell of a section row: its "+" at the right, and a mask
    that leaves the rest of the cell's clicks to the row."""

    def __init__(self, button):
        super().__init__()
        self.button = button
        button.setParent(self)

    def resizeEvent(self, event):
        side = max(self.height(), 1)
        self.button.setGeometry(self.width() - side - 4, 0, side + 4, side)
        self.setMask(QRegion(self.button.geometry()))
        super().resizeEvent(event)


class StatusDelegate(QStyledItemDelegate):
    """The status column: the text of a row with a "+" stops short of it.
    The column is as wide as its longest text (Outliner.status_width), so
    this elision is a safety net that the tests check never cuts."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(ADD_ROLE):
            room = add_room(option.rect.height()) + text_margin(option.widget or self.parent())
            option.text = option.fontMetrics.elidedText(
                option.text, Qt.TextElideMode.ElideRight, max(0, option.rect.width() - room))


class EntryDelegate(QStyledItemDelegate):
    """The Entry column, and the whole row of a detail row: its label (and
    the mean field's checkbox) on the first line, its status after the label
    when both fit, else under it, wrapped, so that it is never cut."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def line_height(self, option, index):
        """The height of the row's first line: a row of one line."""
        return super().sizeHint(option, index).height()

    def layout(self, option, index):
        """(rect of the first line, rect of the status, on one line) of a
        detail row whose span is option.rect: the status at the right of the
        first line when it fits after the label, else under the row's first
        line from its left, wrapped."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        rect = option.rect
        first = QRect(rect.x(), rect.y(), rect.width(), self.line_height(option, index))
        opt.rect = first
        text = self.view.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt,
                                                self.view)
        margin = text_margin(self.view)
        right = first.right() - margin
        status = index.siblingAtColumn(1).data() or ""
        font = self.view.font()
        width = text_width(font, status)
        if text_width(opt.font, opt.text) + TEXT_GAP + width <= right - (text.left() + margin):
            return first, QRect(right - width, first.y(), width + 1, first.height()), True
        left = first.left() + margin
        width = max(1, right - left)
        flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        bound = QFontMetrics(font).boundingRect(QRect(0, 0, width, 1 << 16), int(flags),
                                                wrapped(font, status, width))
        return first, QRect(left, first.bottom() + 1, width, bound.height()), False

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        if not index.data(DETAIL_ROLE):
            return hint
        opt = QStyleOptionViewItem(option)
        opt.rect = self.view.span_rect(index, hint.height())
        _, status, one_line = self.layout(opt, index)
        return hint if one_line else QSize(hint.width(), hint.height() + status.height()
                                           + DETAIL_PAD)

    def paint(self, painter, option, index):
        if not index.data(DETAIL_ROLE):
            super().paint(painter, option, index)
            return
        first, status_rect, one_line = self.layout(option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = self.view.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, self.view)
        opt.rect = first.adjusted(0, 0, -(status_rect.width() + TEXT_GAP), 0) if one_line \
            else first
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, self.view)
        group = QPalette.ColorGroup.Disabled if not opt.state & QStyle.StateFlag.State_Enabled \
            else QPalette.ColorGroup.Active if opt.state & QStyle.StateFlag.State_Active \
            else QPalette.ColorGroup.Inactive
        brush = index.siblingAtColumn(1).data(Qt.ItemDataRole.ForegroundRole)
        if opt.state & QStyle.StateFlag.State_Selected:
            color = opt.palette.color(group, QPalette.ColorRole.HighlightedText)
        else:
            color = brush.color() if isinstance(brush, QBrush) else \
                opt.palette.color(group, QPalette.ColorRole.Text)
        status = index.siblingAtColumn(1).data() or ""
        painter.save()
        painter.setFont(self.view.font())
        painter.setPen(color)
        if one_line:
            flags = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        else:
            flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            status = wrapped(self.view.font(), status, status_rect.width())
        painter.drawText(status_rect, int(flags), status)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if index.data(DETAIL_ROLE):         # the checkbox is on the first line
            option = QStyleOptionViewItem(option)
            option.rect = QRect(option.rect.x(), option.rect.y(), option.rect.width(),
                                self.line_height(option, index))
        return super().editorEvent(event, model, option, index)


class Outliner(QTreeWidget):
    selected = Signal(str)              # item id ("" for none)
    command = Signal(str, object)       # mutation or action name, args dict
    add_requested = Signal(str, object)  # a section's "+": its path (s1/regions...), the button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("outliner")
        self.setHeaderLabels(["Entry", "Status"])
        # the Status column is as wide as its longest text (status_width, after every
        # refresh) and the Entry column takes the rest, so that no status and no "+" of
        # the sections is out of sight to the right, and nothing scrolls sideways
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setUniformRowHeights(False)          # a detail row may read on two lines
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.currentItemChanged.connect(self._current_changed)
        self.itemChanged.connect(self._item_changed)
        self._session = None
        self._items = {}
        self._add_buttons = {}          # section path -> its "+" (rebuilt with the tree)
        self._details = {}              # item id -> its state and messages in words
        self._locks = {}                # item id -> (status text, tooltip line) of its locks
        self._refreshing = False
        self._viewport_width = -1
        self._entry_delegate = EntryDelegate(self)
        self.setItemDelegateForColumn(0, self._entry_delegate)
        self._status_delegate = StatusDelegate(self)
        self.setItemDelegateForColumn(1, self._status_delegate)
        for text, shortcut, slot in (("Delete", "delete", self.delete_current),
                                     ("Rename", "rename", self.rename_current),
                                     ("Duplicate", "duplicate", self.duplicate_current),
                                     ("Move up", "move_up", lambda: self.move_current(-1)),
                                     ("Move down", "move_down", lambda: self.move_current(1))):
            action = shortcuts.bind(QAction(text, self), shortcut)
            action.triggered.connect(slot)
            self.addAction(action)

    # ---- state
    def current_id(self):
        item = self.currentItem()
        return item.data(0, ID_ROLE) if item is not None else ""

    def item(self, item_id):
        return self._items.get(item_id)

    def add_button(self, path):
        """The "+" of a section row: path is <system>/geometry,
        <system>/regions, <system>/hamiltonian, <system>/model or
        calculations; None when the tree has no such row."""
        return self._add_buttons.get(path)

    def is_detail(self, item_id):
        """Whether a row reads its status across both columns (a system,
        the mean field when on) rather than in the Status column."""
        item = self._items.get(item_id)
        return bool(item is not None and item.data(0, DETAIL_ROLE))

    def _add_plus(self, item, path, tooltip, enabled=True):
        """Put a "+" at the right of a section row's status cell."""
        button = QToolButton()
        button.setText("+")
        button.setObjectName("outlinerAdd_" + path.replace("/", "_"))
        font = button.font()
        font.setBold(True)
        button.setFont(font)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(tooltip)
        button.setEnabled(enabled)
        button.clicked.connect(lambda checked=False: self.add_requested.emit(path, button))
        item.setData(1, ADD_ROLE, path)
        self.setItemWidget(item, 1, AddCell(button))
        self._add_buttons[path] = button
        return button

    def set_current(self, item_id):
        """Select a row without emitting selected (the window drives this)."""
        item = self._items.get(item_id)
        self.blockSignals(True)
        try:
            self.setCurrentItem(item) if item is not None else self.setCurrentItem(None)
        finally:
            self.blockSignals(False)

    def _add(self, parent, item_id, label, status="", details=(), movable=False):
        """A row: what it is (label), its state (status), and the state and
        the messages in words (details), which close its tooltip."""
        item = QTreeWidgetItem(parent, [label, status]) if parent is not None \
            else QTreeWidgetItem([label, status])
        if parent is None:
            self.addTopLevelItem(item)
        item.setData(0, ID_ROLE, item_id)
        if not movable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        self._items[item_id] = item
        self._details[item_id] = [line for line in details if line]
        return item

    def item_font(self, item, column):
        """The font a cell is drawn in: its own, else the view's."""
        font = item.data(column, Qt.ItemDataRole.FontRole)
        return font if font is not None else self.font()

    def _detail_row(self, item):
        """Make a row read its status across both columns (DETAIL_ROLE)."""
        item.setData(0, DETAIL_ROLE, True)
        item.setFirstColumnSpanned(True)

    def _paint(self, item, color, columns=(0, 1)):
        for column in columns:
            item.setForeground(column, QBrush(QColor(color)))

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
            self._add_buttons = {}
            self._details = {}
            self._locks = {}
            document = session.document
            for system in document.systems:
                self._add_system(session, system)
            calcs = self._add(None, "calculations", "Calculations")
            several = len(document.systems) > 1
            for calc in document.calculations:
                self._add_calculation(session, calcs, calc, several)
            self._mark_locks(document)
            self._add_pluses(document)
            for item_id in self._items:
                self._set_tooltip(item_id)
            self.expandAll()
            for item_id in collapsed & set(self._items):
                self._items[item_id].setExpanded(False)
            if current in self._items:
                self.setCurrentItem(self._items[current])
        finally:
            self.blockSignals(False)
            self._refreshing = False
        self.fit_status()
        self.verticalScrollBar().setValue(scroll)

    def _set_tooltip(self, item_id):
        """The row's tooltip, on both columns: its full label, then its
        state and messages in words."""
        item = self._items[item_id]
        lines = [item.text(0)] + self._details.get(item_id, [])
        lock = self._locks.get(item_id)
        if lock is not None:
            lines.append(lock[1])
        tip = "\n".join(lines)
        item.setToolTip(0, tip)
        item.setToolTip(1, tip)

    def _add_system(self, session, system):
        build = session.builds.get(system.id)
        current = session.build_is_current(system.id)
        runtime = {r["id"]: r for r in build["reports"]} if build and current else {}
        kind = "a quantum system" if system.hamiltonian is not None else "a classical system"
        if build is None:
            status, details = "building…", [f"{kind}, being built"]
        else:
            words = [f"{build['dimensionality']}D", _sites(build["sites"]), _mode(build["mode"])]
            status = " · ".join(words)
            if build.get("dimension") is not None and system.hamiltonian is not None:
                words.append(f"dimension {build['dimension']}")
            details = [f"{kind}: " + ", ".join(words)]
            if not current:
                details.append("being built again after the last change: this is the "
                               "previous build")
        error = session.build_errors.get(system.id)
        if error:
            line = next((line for line in error.splitlines() if line.strip()), error)
            status = f"{marks.mark('failed')} {line}"
            details = [f"{kind}, which cannot be built: {error}"]
        top = self._add(None, system.id, _entry_text(system.id, system.name), status, details)
        font = self.font()
        font.setBold(True)
        top.setFont(0, font)
        self._detail_row(top)
        if error:
            self._paint(top, theme.ERROR, (1,))
        elif build is None or not current:
            self._paint(top, theme.DISABLED, (1,))        # an old summary, or none yet
        try:
            plan = session.plan_system(system.id)
        except Exception as error:     # a broken document still displays
            item = self._add(top, f"{system.id}/problem", "cannot plan", marks.mark("invalid"),
                             [f"invalid: {error}"])
            self._paint(item, theme.ERROR)
            return
        stages = {s.id: s for s in plan.stages if s.id}

        geometry = self._add(top, f"{system.id}/geometry", "Geometry",
                             details=["the base lattice, then the ops in their order"])
        base = plan.stages[0]
        base_item = self._add(geometry, f"{system.id}/base", _label("lattice", base.kind),
                              details=["the base lattice"])
        if base.problem:
            self._mark_invalid(base_item, base.problem)
        for op in system.geometry.ops:
            self._add_entry(geometry, op, "geometry_op", stages[op.id], runtime.get(op.id),
                            summary=_summary(op.params))

        positions = build["positions"] if build is not None and current else None
        count = len(system.regions)
        regions = self._add(top, f"{system.id}/regions", "Regions",
                            details=[f"{count} region{'s' if count != 1 else ''}"
                                     if count else "no region yet: the + makes one"])
        for region in system.regions:
            selection = _selection_text(region.select)
            name = region.name if region.name != region.id else ""
            item = self._add(regions, region.id, _entry_text(region.id, name, selection),
                             details=[f"the sites of {selection}"], movable=True)
            if positions is not None:
                try:
                    inside = int(region_tools.evaluate_positions(region.select,
                                                                 positions).sum())
                    item.setText(1, _sites(inside))
                    self._details[region.id].append(f"{_sites(inside)} of the current build")
                except Exception as error:
                    self._mark_invalid(item, str(error))

        if system.model is not None:
            self._add_model(top, system, stages, runtime, plan)
            return
        if system.hamiltonian is None:
            return
        upgraded = f" (upgraded by {', '.join(plan.upgraded_by)})" if plan.upgraded_by else ""
        hamiltonian = self._add(top, f"{system.id}/hamiltonian", "Hamiltonian",
                                details=[f"the Hilbert space: {_mode(plan.mode)}{upgraded}"])
        for term in system.hamiltonian.terms:
            report = runtime.get(term.id)
            self._add_entry(hamiltonian, term, "term", stages[term.id], report,
                            mode=report.get("mode") if report else None)
        self._add_meanfield(session, hamiltonian, system, stages[f"{system.id}/meanfield"])

    def _add_model(self, top, system, stages, runtime, plan):
        """A classical system's Model branch: its set-up row and its terms."""
        model = system.model
        branch = self._add(top, f"{system.id}/model_stack", "Model",
                           details=[f"the model: {plan.mode}"])
        stage = stages.get(f"{system.id}/model")
        setup = _summary(model.params)
        item = self._add(branch, f"{system.id}/model", " · ".join(
            part for part in (_label("model", model.kind), setup) if part),
            details=["the model's set-up" + (f": {_summary(model.params, 400)}" if setup
                                             else "")])
        if stage is not None and stage.problem:
            self._mark_invalid(item, stage.problem)
        for term in model.terms:
            self._add_entry(branch, term, "term", stages[term.id], runtime.get(term.id))

    def _add_meanfield(self, session, parent, system, stage):
        """The mean field: "off", or its interactions and when it runs, read
        across the row (a detail row) so that they are never cut."""
        block = system.hamiltonian.meanfield
        item = self._add(parent, f"{system.id}/meanfield", "Mean field",
                         details=[_label("meanfield", block.kind)])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked if block.enabled else Qt.CheckState.Unchecked)
        if not block.enabled:
            item.setText(1, "off")
            self._details[item.data(0, ID_ROLE)].append("off: its checkbox turns it on")
            self._paint(item, theme.DISABLED)
            return item
        if stage.problem:
            self._mark_invalid(item, stage.problem)
            return item
        interactions = _interactions(stage.params if stage.params is not None
                                     else block.params)
        status = "runs with the calculations"
        words = ("runs with the calculations, not while editing: the canvas and the "
                 "Hamiltonian view show the Hamiltonian before it")
        for calc in session.document.calculations:
            result = session.result(calc.id)
            if calc.system == system.id and result is not None and result.meanfield \
                    and not session.is_stale(calc.id):
                energy = result.meanfield.get("total_energy", float("nan"))
                status = f"E = {energy:.6g}"
                words = f"E = {energy:.6g}: the total energy of the converged mean field, " \
                        f"from the run of {calc.id}"
                break
        item.setText(1, ", ".join(part for part in (interactions, status) if part))
        self._details[item.data(0, ID_ROLE)].append(words)
        self._detail_row(item)
        return item

    def _add_entry(self, parent, entry, family, stage, report, mode=None, summary=""):
        """An op or a term: what it is in the label (with an op's parameters
        and the region a term is restricted to), its state in the status."""
        region = getattr(entry, "region", None)
        item = self._add(parent, entry.id, _entry_text(
            entry.id, _label(family, entry.kind), entry.name, summary,
            f"in {region}" if region else ""), movable=True)
        details = self._details[entry.id]
        if summary and _summary(entry.params, 400) != summary:     # cut in the label
            details.append(_summary(entry.params, 400))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked if entry.enabled else Qt.CheckState.Unchecked)
        if isinstance(entry.params.get("code"), str):          # a Python node: its code
            details.append(entry.params["code"].rstrip())
        message = stage.problem
        if report is not None and report["status"] == "invalid":
            message = report["message"]
        if not entry.enabled:
            item.setText(1, marks.mark("disabled"))
            details.append("disabled: left out of the stack until its checkbox is ticked")
            self._paint(item, theme.DISABLED)
        elif message:
            self._mark_invalid(item, message)
        else:
            status = _mode(mode) if mode else ""
            if mode:
                details.append(f"the Hilbert space after it: {_mode(mode)}")
            if stage.warnings:
                status = f"{marks.mark('warning')} {status}".strip()
                details += [f"{marks.mark('warning')} {warning}" for warning in stage.warnings]
            item.setText(1, status)
        return item

    def _add_pluses(self, document):
        """The "+" of every section row of the tree."""
        for system in document.systems:
            for row, section in ADD_SECTIONS.items():
                item = self._items.get(f"{system.id}/{row}")
                if item is not None:
                    self._add_plus(item, f"{system.id}/{section}",
                                   ADD_TIPS[section].format(system=system.id))
        self._add_plus(self._items["calculations"], "calculations",
                       ADD_TIPS["calculations"].format(run=shortcuts.text("run")),
                       enabled=bool(document.systems))

    def _mark_locks(self, document):
        """"locked" (or "m locked") after the status of what a lock covers; a
        lattice parameter's on the base lattice row."""
        for lock in document.locks:
            head, _, param = lock.partition(".")
            if param and "/" not in head and any(s.id == head for s in document.systems):
                head = f"{head}/base"
            item = self._items.get(head)
            if item is None:
                continue
            text = f"{param} {marks.mark('locked')}" if param else marks.mark("locked")
            old = self._locks.get(head)
            self._locks[head] = (f"{old[0]} · {text}" if old else text,
                                 (old[1] + "\n" if old else "") + LOCK_TIP.format(lock=lock))
            item.setText(1, f"{item.text(1)} · {text}" if item.text(1) else text)

    def _mark_invalid(self, item, message):
        item.setText(1, marks.mark("invalid"))
        self._details[item.data(0, ID_ROLE)].append(f"invalid, skipped: {message}")
        self._paint(item, theme.ERROR)

    @staticmethod
    def _calculation_status(session, calc_id, job=None):
        """(status, colour or None, its state and messages in words) of a
        calculation's row; job: the one an event is about, which the session
        may not hold yet."""
        state, progress = marks.calculation_state(session, calc_id, job)
        if job is None or job.done:
            job = session.calc_jobs.get(calc_id)
        details = []
        if state not in ("queued", "running"):
            try:
                problem = session.plan_calculation(calc_id).problem
            except Exception as error:      # a broken document still displays
                problem = str(error)
            if problem:
                state = "invalid"
                details.append(f"invalid, it cannot run: {problem}")
        status = marks.mark(state, progress)
        if state == "running":
            details.append(f"running, {status}")
        elif state == "failed":
            details.append(f"failed: {job.error if job is not None else ''}")
        elif state in CALCULATION_WORDS:
            details.append(CALCULATION_WORDS[state])
        result = session.result(calc_id)
        if state in ("done", "stale") and result is not None and \
                result.plot.get("kind") == "scalar":              # the numbers themselves
            rows = scalar_rows(result)
            status = f"{status} {_short(', '.join(text for _, text in rows), SCALAR_CHARS)}"
            details.append(", ".join(f"{label} = {text}" for label, text in rows))
        color = theme.ERROR if state in marks.ERROR_STATES else \
            theme.DISABLED if state in marks.DIM_STATES else None
        return status, color, details

    def _add_calculation(self, session, parent, calc, several=False):
        label = _label("calculation", calc.kind) + (f" on {calc.system}" if several else "")
        status, color, details = self._calculation_status(session, calc.id)
        item = self._add(parent, calc.id, _entry_text(calc.id, label, calc.name), status,
                         details + ([] if several else [f"on {calc.system}"]), movable=True)
        if color is not None:
            self._paint(item, color, (1,))

    def update_calculation(self, session, calc_id, job=None):
        """Only the status of one calculation (progress arrives often); job:
        the one the event is about."""
        item = self._items.get(calc_id)
        if item is None:
            return
        status, color, details = self._calculation_status(session, calc_id, job)
        lock = self._locks.get(calc_id)
        if lock is not None:
            status = f"{status} · {lock[0]}" if status else lock[0]
        item.setText(1, status)
        item.setData(1, Qt.ItemDataRole.ForegroundRole,
                     QBrush(QColor(color)) if color is not None else None)
        several = self._session is not None and len(self._session.document.systems) > 1
        calc = next((c for c in session.document.calculations if c.id == calc_id), None)
        self._details[calc_id] = details + ([] if several or calc is None
                                            else [f"on {calc.system}"])
        self._set_tooltip(calc_id)
        self.fit_status()

    # ---- the widths
    def status_width(self):
        """The width the Status column needs: its longest text, with the
        cell's margins and, on a section row, the room of its "+"; the
        detail rows read theirs across the row and do not count. At least
        the header's."""
        margin = text_margin(self)
        width = self.header().sectionSizeHint(1)
        option = QStyleOptionViewItem()
        self.initViewItemOption(option)
        for item in self._items.values():
            if item.data(0, DETAIL_ROLE):
                continue
            text = item.text(1)
            need = text_width(self.item_font(item, 1), text) + 2 * margin if text else 0
            if item.data(1, ADD_ROLE):
                height = self._entry_delegate.line_height(option, self.indexFromItem(item, 0))
                need = (need - margin if text else margin) + add_room(height)
            width = max(width, need)
        return width

    def fit_status(self):
        """Size the Status column to its contents; the Entry column, which
        stretches, takes the rest."""
        width = self.status_width()
        if self.header().sectionSize(1) != width:
            self.header().resizeSection(1, width)

    def span_rect(self, index, height):
        """Where a detail row spans: from its indentation to the right edge
        of the viewport."""
        depth, parent = 0, index.parent()
        while parent.isValid():
            depth, parent = depth + 1, parent.parent()
        left = self.indentation() * (depth + (1 if self.rootIsDecorated() else 0))
        return QRect(left, 0, max(1, self.viewport().width() - left), height)

    def drawBranches(self, painter, rect, index):
        if index.data(DETAIL_ROLE):           # the arrow beside the first line, the label's
            option = QStyleOptionViewItem()
            self.initViewItemOption(option)
            rect = QRect(rect.x(), rect.y(), rect.width(),
                         min(rect.height(), self._entry_delegate.line_height(option, index)))
        super().drawBranches(painter, rect, index)

    def resizeEvent(self, event):
        """(the viewport's) A detail row reads on one line or two by the
        width it is given."""
        super().resizeEvent(event)
        if self.viewport().width() != self._viewport_width:
            self._viewport_width = self.viewport().width()
            if any(item.data(0, DETAIL_ROLE) for item in self._items.values()):
                self.scheduleDelayedItemsLayout()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.fit_status()               # View > Interface text
            self.scheduleDelayedItemsLayout()

    # ---- interaction
    def _current_changed(self, current, previous):
        self.selected.emit(current.data(0, ID_ROLE) if current is not None else "")

    def _item_changed(self, item, column):
        """A row's check box was toggled. Every QTreeWidgetItem is user
        checkable by default, so a change of column 0 on a row without a box
        (the tooltip of a calculation, rewritten at each progress report) is
        not a toggle."""
        if self._refreshing or column != 0 or not item.flags() & Qt.ItemFlag.ItemIsUserCheckable \
                or item.data(0, Qt.ItemDataRole.CheckStateRole) is None:
            return
        item_id = item.data(0, ID_ROLE)
        enabled = item.checkState(0) == Qt.CheckState.Checked
        if item_id.endswith("/meanfield"):
            name, args = "set_meanfield", {"system": system_of(item_id), "enabled": enabled}
        else:
            name, args = "set_enabled", {"entry": item_id, "enabled": enabled}
        # the command rebuilds the tree, which deletes this item: not inside its own signal
        QTimer.singleShot(0, lambda: self.command.emit(name, args))

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

    # ---- drag to reorder
    def move_for_drop(self, point):
        """(entry id, new index) for dropping the current item at a point of
        the viewport, or None when that drop moves nothing: only within
        the entry's own list (above or below a sibling, or onto the list's
        header for the top)."""
        found = self._family(self.current_id())
        target = self.itemAt(point)
        if found is None or found[0] not in MOVABLE or target is None:
            return None
        family, owner, items, old, obj = found
        target_id = target.data(0, ID_ROLE)
        if target_id == obj.id:
            return None
        system = owner.id if owner is not None else None
        if target_id in list_heads(family, system):
            new = 0
        else:
            other = self._family(target_id)
            if other is None or other[2] is not items:
                return None
            below = point.y() > self.visualItemRect(target).center().y()
            new = drop_index(old, other[3], below)
        new = min(max(new, 0), len(items) - 1)
        return None if new == old else (obj.id, new)

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)      # auto-scroll and the drop indicator
        if event.source() is self and self.move_for_drop(event.position().toPoint()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        event.setDropAction(Qt.DropAction.IgnoreAction)   # Qt must not move the item itself
        event.ignore()
        if event.source() is self:                         # never a drop from elsewhere
            self.drop_at(event.position().toPoint())

    def drop_at(self, point):
        """Drop the current item at a point of the viewport: sends the move
        command (later, since it rebuilds the tree) and returns it, or None."""
        move = self.move_for_drop(point)
        if move is not None:
            entry, index = move
            QTimer.singleShot(0, lambda: self.command.emit("move", {"entry": entry,
                                                                    "index": index}))
        return move

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
        locks = self._session.document.locks if self._session is not None else []
        targets = [(obj.id, "")] + ([(f"{obj.id}/geometry", " the geometry")]
                                    if family == "system" else [])
        for target, what in targets:
            if target in locks:
                menu.addAction(f"Unlock{what}", lambda t=target: self.command.emit(
                    "unlock", {"target": t}))
            else:
                menu.addAction(f"Lock{what}", lambda t=target: self.command.emit(
                    "lock", {"target": t}))
        menu.addAction("Duplicate", self.duplicate_current)
        if family != "system":
            menu.addAction("Move up", lambda: self.move_current(-1))
            menu.addAction("Move down", lambda: self.move_current(1))
        menu.addSeparator()
        menu.addAction("Delete", self.delete_current)
        menu.popup(self.viewport().mapToGlobal(point))
