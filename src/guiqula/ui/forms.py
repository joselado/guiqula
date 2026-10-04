"""Editors for registry parameters (PLAN.md 3.2: the properties form is
derived from an entry's declaration). One editor per parameter type; each
shows a JSON value, returns the edited one from value() (raising
ValueError when the text is not even a number), and emits committed when
the user finishes an edit. Validation proper is the registry's: the panel
sends the value as a command and shows the refusal.

Fields (term parameters, PLAN.md 3.8) are edited as text: a number, or an
expression of x, y, z, r. The button next to a Field (PLAN.md phase 8,
package P6) says its kind when it is not a number ("f(r)" when it is) and
its menu lists the kinds: a number, an expression, piecewise (one value per
region), a profile, interpolated, painted, from a result. Choosing one
opens the panel of that kind only: the one line of what an expression may
use; per region, a value for each region plus the default; for a result,
the calculation (of another system, drawn on the sites), its array, the
component and a scale. A Field editor emits preview when the user looks at
it (focus, typing, the panel), with the value being typed when it parses,
so the window can draw the Field on the structure before anything runs.
Constant-only parameters (the pyqula call behind them takes no function of
position) have no such button.
"""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPlainTextEdit, QPushButton, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from guiqula.core import fields
from guiqula.registry.params import (BoolParam, ChoiceParam, CodeParam, ConditionParam,
                                     FieldParam, FloatParam, FloatVectorParam, IntParam,
                                     IntVectorParam, KPathParam, PositionsParam, SeedParam,
                                     TextParam, VectorFieldParam)
from guiqula.ui import theme

INT_LIMIT = 2**31 - 1
NONE_TEXT = "(none)"
FIELD_HELP = ("A number, or an expression of the position: x, y, z, r (distance from the "
              "origin), pi, and numpy functions such as sin, cos, exp, tanh, sqrt "
              "(e.g. 0.3*tanh(x/4)). A comparison is 1 where it holds and 0 elsewhere, so "
              "0.2*(x > 0) acts on the right half only.")
FIELD_LINE = "x, y, z, r; sin, exp, tanh; (x > 0) is 1 or 0"


def format_number(value):
    return f"{value:.12g}" if isinstance(value, float) else str(value)


def format_field(value):
    return format_number(value) if isinstance(value, (int, float)) else str(value)


def parse_field(text):
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        return text            # an expression; the registry parses it


def parse_kpath(text):
    """"G K M G" or "G (0.5, 0.5) G" -> a k-path; empty: None (the default)."""
    import re
    text = text.strip()
    if not text:
        return None
    out = []
    for match in re.finditer(r"\(([^)]*)\)|([A-Za-z][A-Za-z0-9']*)", text):
        point, label = match.groups()
        if label:
            out.append(label)
        else:
            out.append([parse_float(c) for c in point.split(",") if c.strip()])
    return out


def format_kpath(value):
    if value is None:
        return ""
    return " ".join(v if isinstance(v, str) else
                    "(" + ", ".join(format_number(float(c)) for c in v[:2]) +
                    (f", {format_number(float(v[2]))}" if len(v) > 2 and v[2] else "") + ")"
                    for v in value)


def parse_float(text):
    try:
        return float(text.strip())
    except ValueError:
        raise ValueError(f"{text.strip()!r} is not a number") from None


def parse_optional(text, integer=False):
    """Empty text is None (the default); otherwise a number."""
    if not text.strip():
        return None
    value = parse_float(text)
    if integer:
        if not value.is_integer():
            raise ValueError(f"{text.strip()!r} is not an integer")
        return int(value)
    return value


class Editor(QWidget):
    committed = Signal()

    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(2)
        self.layout_ = QHBoxLayout()
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.outer.addLayout(self.layout_)
        self.setToolTip(param.doc)

    def _quiet(self, widget, setter, *values):
        widget.blockSignals(True)
        try:
            setter(*values)
        finally:
            widget.blockSignals(False)


class LineEditor(Editor):
    """Text with a parser: floats, seeds, scalar Fields."""

    def __init__(self, param, parse, show, placeholder="", parent=None):
        super().__init__(param, parent)
        self.parse, self.show = parse, show
        self.edit = QLineEdit()
        self.edit.setObjectName(f"edit_{param.name}")
        self.edit.setPlaceholderText(placeholder)
        self.edit.editingFinished.connect(self._finished)
        self.layout_.addWidget(self.edit)
        self._shown = None

    def _finished(self):
        if self.edit.text() != self._shown:
            self.committed.emit()

    def value(self):
        return self.parse(self.edit.text())

    def set_value(self, value):
        self._shown = self.show(value)
        self._quiet(self.edit, self.edit.setText, self._shown)


# the kinds of a Field (fields.kind_of), in the order of its button's menu: kind -> (the
# button's word, the menu's text, what it is)
FIELD_KINDS = {
    "constant": ("f(r)", "number", "the same number on every site, typed in the box"),
    "expression": ("expression", "expression of x, y, z, r",
                   "a function of the position typed in the box, such as 0.3*tanh(x/4)"),
    "piecewise": ("piecewise", "piecewise (one value per region)",
                  "a number or an expression on each region of the system, another elsewhere"),
    "profile": ("profile", "profile (gaussian, step, disk...)",
                "a named shape and its numbers: a gaussian, a step, a disk, a plane wave, a "
                "domain wall, an Aubry-Andre modulation"),
    "interpolated": ("interpolated", "interpolated (control points)",
                     "smoothed between control points x, y, value"),
    "painted": ("painted", "painted (with the brush)",
                "values painted site by site with the brush of the Field preview"),
    "from_result": ("from result", "from result (of another system)",
                    "read site by site from a result of another system drawn on the sites: a "
                    "texture, a density, an LDOS"),
}
STRUCTURED = ("piecewise", "profile", "interpolated", "painted", "from_result")
COMPONENTS = ((None, "the value"), (0, "x"), (1, "y"), (2, "z"))


def kind_of(value):
    """The kind of a Field as its editor shows it: constant (a number, or
    nothing yet), expression (a string), or the kind of a structured one."""
    if isinstance(value, dict):
        return value.get("kind", "piecewise")
    return "expression" if isinstance(value, str) else "constant"


def result_sources(session, system_id):
    """[(calculation id, label, {array: components or None})] a from_result
    Field of system_id can read: results of other systems drawn on the sites,
    and their arrays with one value (None) or a few (2, 3) per site."""
    import numpy as np
    out = []
    for calc in session.document.calculations:
        result = session.result(calc.id)
        if calc.system == system_id or result is None or result.structure is None:
            continue
        n = len(result.structure["positions"])
        arrays = {}
        for name, value in result.arrays.items():
            shape = np.shape(value)
            if shape == (n,):
                arrays[name] = None
            elif len(shape) == 2 and shape[0] == n and shape[1] in (2, 3):
                arrays[name] = shape[1]
        if arrays:
            out.append((calc.id, f"{calc.id} {calc.kind} on {calc.system}", arrays))
    return out


def _summary(value, regions):
    """One line for a structured Field (piecewise, from a result, profile,
    interpolated, painted)."""
    kind = value.get("kind")
    if kind == "profile":
        return value["name"] + " " + ", ".join(f"{k} {format_number(v)}"
                                               for k, v in value["params"].items())
    if kind == "interpolated":
        return f"{len(value['points'])} control points, length {format_number(value['length'])}"
    if kind == "painted":
        return f"{len(value['sites'])} sites painted, elsewhere {format_number(value['default'])}"
    if kind == "from_result":
        component = "" if value["component"] is None else "[" + "xyz"[value["component"]] + "]"
        scale = "" if value["scale"] == 1.0 else f" × {format_number(value['scale'])}"
        return f"{value['calculation']}.{value['array']}{component}{scale}"
    names = dict(regions)
    parts = [f"{names.get(p['region'], p['region']) or p['region']}: {format_field(p['value'])}"
             for p in value["pieces"]]
    return "; ".join([f"elsewhere {format_field(value['default'])}"] + parts)


class _PieceRow:
    def __init__(self, editor, index):
        name = editor.name
        self.region = QComboBox()
        self.region.setObjectName(f"pieceRegion_{name}_{index}")
        for region_id, label in editor.regions:
            self.region.addItem(f"{region_id}  {label}" if label != region_id else region_id,
                                region_id)
        self.value = QLineEdit()
        self.value.setObjectName(f"pieceValue_{name}_{index}")
        self.value.setPlaceholderText("number or f(x, y, z)")
        self.remove = QToolButton()
        self.remove.setText("×")
        self.remove.setToolTip("remove this region's value")
        self.remove.setObjectName(f"pieceRemove_{name}_{index}")
        self.region.activated.connect(lambda _: editor._piece_finished())
        self.value.editingFinished.connect(editor._piece_finished)
        self.value.textEdited.connect(lambda _: editor._look())
        self.remove.clicked.connect(lambda: editor.remove_piece(index))
        editor.install(self.value)

    def widgets(self):
        return (self.region, self.value, self.remove)


class FieldEditor(Editor):
    """A scalar Field with its kind menu and its panel."""

    preview = Signal()

    def __init__(self, param, regions=(), suffix="", parent=None, sources=()):
        super().__init__(param, parent)
        self.name = param.name + suffix
        self.regions = list(regions)            # [(id, name)] of the system
        self.sources = list(sources)            # result_sources(): what it may read
        self.edit = QLineEdit()
        self.edit.setObjectName(f"edit_{self.name}")
        self.edit.setPlaceholderText("a constant" if not param.native else "number or f(x, y, z)")
        self.edit.editingFinished.connect(self._finished)
        self.edit.textEdited.connect(lambda _: self._look())
        self.install(self.edit)
        self.marker = QLabel("")
        self.marker.setObjectName(f"fieldKind_{self.name}")
        self.marker.setMinimumWidth(28)
        self.marker.hide()                      # shown when it has something to say
        self.layout_.addWidget(self.edit, 1)
        self.layout_.addWidget(self.marker)
        self.button = None
        self.kind_menu = None
        self.kind_actions = {}                  # kind -> its QAction in the kind menu
        self.panel_kind = None                  # the kind whose panel is open, or None
        self.rows = []
        self._value = None
        self._shown = None
        self._draft = None
        self.setToolTip(param.doc + ("\n\n" + FIELD_HELP if param.native else
                                     "\n\nConstant only: the pyqula call behind it does not "
                                     "take a function of position."))
        if param.native:
            from guiqula.ui.palette import MenuButton
            self.kind_menu = QMenu(self)
            self.kind_menu.setObjectName(f"fieldKindMenu_{self.name}")
            self.kind_menu.setToolTipsVisible(True)
            group = QActionGroup(self.kind_menu)
            for kind, (_, text, tip) in FIELD_KINDS.items():
                action = self.kind_menu.addAction(text)
                action.setObjectName(f"fieldKind_{self.name}_{kind}")
                action.setCheckable(True)
                action.setToolTip(tip)
                action.setActionGroup(group)
                action.triggered.connect(lambda _=False, k=kind: self.choose_kind(k))
                self.kind_actions[kind] = action
            self.button = MenuButton("f(r)", self.kind_menu)
            self.button.setObjectName(f"fieldButton_{self.name}")
            self.button.clicked.connect(self.show_kind_menu)
            self.layout_.addWidget(self.button)
            self._build_panel()

    def install(self, widget):
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn:
            self._look()
        return False

    def show_kind_menu(self):
        """The button's menu, opened below it with popup() (a click returns
        at once); returns it."""
        self.kind_menu.popup(self.button.mapToGlobal(self.button.rect().bottomLeft()))
        return self.kind_menu

    # ---- the panel
    def _build_panel(self):
        self.panel = QFrame()
        self.panel.setObjectName(f"fieldPanel_{self.name}")
        self.panel.setFrameShape(QFrame.Shape.StyledPanel)
        column = QVBoxLayout(self.panel)
        column.setContentsMargins(6, 4, 6, 4)
        self.result_box = QWidget()
        form = QGridLayout(self.result_box)
        form.setContentsMargins(0, 0, 0, 0)
        self.result_calc, self.result_array = QComboBox(), QComboBox()
        self.result_component, self.result_scale = QComboBox(), QLineEdit()
        for widget, what in ((self.result_calc, "Calc"), (self.result_array, "Array"),
                             (self.result_component, "Component"), (self.result_scale, "Scale")):
            widget.setObjectName(f"fieldResult{what}_{self.name}")
        for source in self.sources:
            self.result_calc.addItem(source[1], source[0])
        for component, label in COMPONENTS:
            self.result_component.addItem(label, component)
        self.result_calc.activated.connect(lambda _: self._result_edited(new_calc=True))
        self.result_array.activated.connect(lambda _: self._result_edited(new_array=True))
        self.result_component.activated.connect(lambda _: self._result_edited())
        self.result_scale.editingFinished.connect(self._result_edited)
        for row, (label, widget) in enumerate((("result", self.result_calc),
                                               ("array", self.result_array),
                                               ("component", self.result_component),
                                               ("times", self.result_scale))):
            form.addWidget(QLabel(label), row, 0)
            form.addWidget(widget, row, 1)
        column.addWidget(self.result_box)
        self._build_profile(column)
        self._build_interpolated(column)
        self._build_painted(column)
        self.no_results = QLabel("No result of another system drawn on the sites yet: run "
                                 "one there first (a texture, a density, an LDOS).")
        self.no_results.setWordWrap(True)
        self.no_results.setObjectName(f"fieldNoResults_{self.name}")
        column.addWidget(self.no_results)
        self.help = QLabel(FIELD_LINE)
        self.help.setWordWrap(True)
        self.help.setToolTip(FIELD_HELP)
        self.help.setObjectName(f"fieldHelp_{self.name}")
        column.addWidget(self.help)
        self.pieces = QWidget()
        grid = QGridLayout(self.pieces)
        grid.setContentsMargins(0, 0, 0, 0)
        self.grid = grid
        grid.addWidget(QLabel("elsewhere"), 0, 0)
        self.default = QLineEdit()
        self.default.setObjectName(f"pieceDefault_{self.name}")
        self.default.setToolTip("the value on the sites in none of the regions")
        self.default.editingFinished.connect(self._piece_finished)
        self.default.textEdited.connect(lambda _: self._look())
        self.install(self.default)
        grid.addWidget(self.default, 0, 1, 1, 2)
        self.add = QPushButton("Add a region")
        self.add.setObjectName(f"pieceAdd_{self.name}")
        self.add.clicked.connect(self.add_piece)
        self.no_regions = QLabel("This system has no region yet: make one with the + of its "
                                 "Regions row in the outliner (by expression, or from the "
                                 "sites selected on the canvas).")
        self.no_regions.setWordWrap(True)
        column.addWidget(self.pieces)
        column.addWidget(self.add)
        column.addWidget(self.no_regions)
        self.order = QLabel("Where regions overlap, the lower one wins.")
        self.order.setObjectName(f"pieceOrder_{self.name}")
        column.addWidget(self.order)
        self.outer.addWidget(self.panel)
        self.panel.hide()

    def _build_profile(self, column):
        self.profile_box = QWidget()
        grid = QGridLayout(self.profile_box)
        grid.setContentsMargins(0, 0, 0, 0)
        self.profile_name = QComboBox()
        self.profile_name.setObjectName(f"fieldProfile_{self.name}")
        self.profile_name.addItems(sorted(fields.PROFILES))
        self.profile_name.activated.connect(lambda _: self._profile_edited(new_name=True))
        grid.addWidget(QLabel("profile"), 0, 0)
        grid.addWidget(self.profile_name, 0, 1)
        self.profile_grid, self.profile_edits = grid, {}
        column.addWidget(self.profile_box)

    def _build_interpolated(self, column):
        self.points_box = QWidget()
        grid = QGridLayout(self.points_box)
        grid.setContentsMargins(0, 0, 0, 0)
        self.points = QPlainTextEdit()
        self.points.setObjectName(f"fieldPoints_{self.name}")
        self.points.setPlaceholderText("one control point per line: x, y, value")
        self.points.setMaximumHeight(6 * self.points.fontMetrics().lineSpacing())
        self.length = QLineEdit()
        self.length.setObjectName(f"fieldLength_{self.name}")
        self.length.setToolTip("the length over which the control points are smoothed")
        apply = QPushButton("Apply")
        apply.setObjectName(f"fieldPointsApply_{self.name}")
        apply.clicked.connect(self._points_edited)
        self.length.editingFinished.connect(self._points_edited)
        grid.addWidget(self.points, 0, 0, 1, 3)
        grid.addWidget(QLabel("length"), 1, 0)
        grid.addWidget(self.length, 1, 1)
        grid.addWidget(apply, 1, 2)
        column.addWidget(self.points_box)

    def _build_painted(self, column):
        self.paint_box = QWidget()
        grid = QGridLayout(self.paint_box)
        grid.setContentsMargins(0, 0, 0, 0)
        self.paint_info = QLabel("")
        self.paint_info.setObjectName(f"fieldPaintInfo_{self.name}")
        self.paint_info.setWordWrap(True)
        self.paint_default = QLineEdit()
        self.paint_default.setObjectName(f"fieldPaintDefault_{self.name}")
        self.paint_default.editingFinished.connect(self._paint_edited)
        clear = QPushButton("Clear")
        clear.setObjectName(f"fieldPaintClear_{self.name}")
        clear.setToolTip("forget the painted sites")
        clear.clicked.connect(lambda: self._paint_edited(clear=True))
        grid.addWidget(self.paint_info, 0, 0, 1, 3)
        grid.addWidget(QLabel("elsewhere"), 1, 0)
        grid.addWidget(self.paint_default, 1, 1)
        grid.addWidget(clear, 1, 2)
        column.addWidget(self.paint_box)

    def _sync_profile(self):
        value = self._value
        self._quiet(self.profile_name, self.profile_name.setCurrentText, value["name"])
        if set(self.profile_edits) != set(value["params"]):
            for label, edit in self.profile_edits.values():
                for widget in (label, edit):
                    widget.blockSignals(True)     # hiding the box with the focus finishes it
                    self.profile_grid.removeWidget(widget)
                    widget.hide()
                    widget.deleteLater()          # may run inside one of their own signals
            self.profile_edits = {}
            for row, name in enumerate(value["params"], 1):
                label, edit = QLabel(name), QLineEdit()
                edit.setObjectName(f"fieldProfile_{self.name}_{name}")
                edit.editingFinished.connect(self._profile_edited)
                self.profile_grid.addWidget(label, row, 0)
                self.profile_grid.addWidget(edit, row, 1)
                self.profile_edits[name] = (label, edit)
        for name, (_, edit) in self.profile_edits.items():
            self._quiet(edit, edit.setText, format_number(value["params"][name]))

    def _profile_edited(self, new_name=False):
        if self._kind() != "profile":
            return
        if new_name:            # another profile starts from its defaults; the same one stays
            if self.profile_name.currentText() == self._value["name"]:
                return
            value = {"kind": "profile", "name": self.profile_name.currentText(), "params": {}}
        else:
            try:
                params = {name: self._number(edit.text(), name)
                          for name, (_, edit) in self.profile_edits.items()}
            except ValueError as error:
                self._commit_draft(error)
                return
            value = dict(self._value, params=params)
        if value != self._value:
            self._commit_draft(value)

    def _points_edited(self):
        if self._kind() != "interpolated":
            return
        try:
            points = [[self._number(c, "points") for c in line.replace(";", ",").split(",")]
                      for line in self.points.toPlainText().splitlines() if line.strip()]
            length = self._number(self.length.text(), "length")
        except ValueError as error:
            self._commit_draft(error)
            return
        value = {"kind": "interpolated", "points": points, "length": length}
        if value != self._value:
            self._commit_draft(value)

    def _paint_edited(self, clear=False):
        if self._kind() != "painted":
            return
        try:
            default = self._number(self.paint_default.text(), "elsewhere")
        except ValueError as error:
            self._commit_draft(error)
            return
        value = dict(self._value, default=default, **({"sites": []} if clear else {}))
        if value != self._value:
            self._commit_draft(value)

    def open_panel(self, shown=True):
        """Open the panel of the Field's kind (a number's is the line of what
        an expression may use, as choosing expression opens), or close it."""
        if self.button is None:
            return
        kind = self._kind()
        self.panel_kind = ("expression" if kind == "constant" else kind) if shown else None
        self._sync_panel()
        if shown:
            self._look()

    def _kind(self):
        """The kind of the stored Field: constant, expression, piecewise,
        from_result, profile, interpolated or painted."""
        return kind_of(self._value)

    def _piecewise_shown(self):
        return self._kind() == "piecewise"

    def _sync_panel(self):
        kind = self._kind()
        shown = self.panel_kind
        self.panel.setVisible(shown is not None)
        for name, action in self.kind_actions.items():
            self._quiet(action, action.setChecked, name == kind)
        self.help.setVisible(shown == "expression")
        self.result_box.setVisible(shown == "from_result" and kind == "from_result")
        self.no_results.setVisible(shown == "from_result" and not self.sources)
        self.profile_box.setVisible(shown == "profile" and kind == "profile")
        self.points_box.setVisible(shown == "interpolated" and kind == "interpolated")
        self.paint_box.setVisible(shown == "painted" and kind == "painted")
        if kind == "from_result":
            self._sync_result()
        elif kind == "profile":
            self._sync_profile()
        elif kind == "interpolated":
            self._quiet(self.points, self.points.setPlainText, "\n".join(
                ", ".join(format_number(c) for c in p) for p in self._value["points"]))
            self._quiet(self.length, self.length.setText, format_number(self._value["length"]))
        elif kind == "painted":
            self.paint_info.setText(f"{len(self._value['sites'])} sites painted: paint more "
                                    f"with the Paint tool of the Field preview (Structure tab)")
            self._quiet(self.paint_default, self.paint_default.setText,
                        format_number(self._value["default"]))
        piecewise = kind == "piecewise"
        self.pieces.setVisible(piecewise)
        self.add.setVisible(piecewise)
        self.add.setEnabled(bool(self.regions))
        self.no_regions.setVisible(piecewise and not self.regions)
        self.order.setVisible(piecewise and len(self._value["pieces"]) > 1 if piecewise else False)
        pieces = self._value["pieces"] if piecewise else []
        if len(pieces) != len(self.rows):
            for row in self.rows:
                for widget in row.widgets():
                    # hiding the box with the focus finishes its edit, which would send
                    # the pieces of these old rows again (and take back an undo)
                    widget.blockSignals(True)
                    self.grid.removeWidget(widget)
                    widget.hide()
                    widget.deleteLater()        # may run inside one of their own signals
            self.rows = [_PieceRow(self, i) for i in range(len(pieces))]
            for i, row in enumerate(self.rows):
                for column, widget in enumerate(row.widgets()):
                    self.grid.addWidget(widget, i + 1, column)
        if piecewise:
            self._quiet(self.default, self.default.setText, format_field(self._value["default"]))
        for row, piece in zip(self.rows, pieces):
            index = row.region.findData(piece["region"])
            if index < 0:                       # a region this form does not list
                self._quiet(row.region, row.region.addItem, piece["region"], piece["region"])
                index = row.region.findData(piece["region"])
            self._quiet(row.region, row.region.setCurrentIndex, index)
            self._quiet(row.value, row.value.setText, format_field(piece["value"]))

    def _source(self, calc):
        return next((s for s in self.sources if s[0] == calc), None)

    def _sync_result(self):
        value = self._value
        index = self.result_calc.findData(value["calculation"])
        if index < 0:                          # a result this form does not list (yet)
            self._quiet(self.result_calc, self.result_calc.addItem, value["calculation"],
                        value["calculation"])
            index = self.result_calc.findData(value["calculation"])
        self._quiet(self.result_calc, self.result_calc.setCurrentIndex, index)
        source = self._source(value["calculation"])
        self.result_array.blockSignals(True)
        self.result_array.clear()
        for name in (source[2] if source else {value["array"]: None}):
            self.result_array.addItem(name, name)
        self.result_array.setCurrentIndex(max(self.result_array.findData(value["array"]), 0))
        self.result_array.blockSignals(False)
        self._quiet(self.result_component, self.result_component.setCurrentIndex,
                    max(self.result_component.findData(value["component"]), 0))
        self._quiet(self.result_scale, self.result_scale.setText, format_number(value["scale"]))

    def _result_value(self, calc=None):
        """A from_result Field reading calc (first array, first component)."""
        source = self._source(calc) if calc else (self.sources[0] if self.sources else None)
        if source is None:
            return None
        array, components = next(iter(source[2].items()))
        return {"kind": "from_result", "calculation": source[0], "array": array,
                "component": None if components is None else 0, "scale": 1.0, "tol": 0.1}

    def _result_edited(self, new_calc=False, new_array=False):
        if self._kind() != "from_result":
            return
        if new_calc and self.result_calc.currentData() != self._value["calculation"]:
            value = self._result_value(self.result_calc.currentData())   # from its first array
        else:
            value = dict(self._value, array=self.result_array.currentData(),
                         component=self.result_component.currentData())
            if new_array and value["array"] != self._value["array"]:
                source = self._source(value["calculation"])
                components = source[2].get(value["array"]) if source else None
                value["component"] = None if components is None else 0
            try:
                value["scale"] = self._number(self.result_scale.text(), "times")
            except ValueError as error:
                self._commit_draft(error)
                return
        if value is not None and value != self._value:
            self._commit_draft(value)

    # ---- edits
    def _look(self):
        self.preview.emit()

    def _finished(self):
        if not self._piecewise_shown() and self.edit.text() != self._shown:
            self.committed.emit()

    def _piece_finished(self):
        if self._piecewise_shown() and self._read_pieces() != self._value:
            self._edited()

    def _edited(self):
        self.committed.emit()

    def _read_pieces(self):
        return {"kind": "piecewise", "default": parse_field(self.default.text()),
                "pieces": [{"region": row.region.currentData(),
                            "value": parse_field(row.value.text())} for row in self.rows]}

    def _commit_draft(self, value):
        """Send value as the Field; a ValueError instead is refused the
        way a main editor refuses text (value() raises it): the form says
        what is wrong and shows the stored value again."""
        self._draft = value
        try:
            self.committed.emit()
        finally:
            self._draft = None

    @staticmethod
    def _number(text, box):
        try:
            return parse_float(text)
        except ValueError as error:
            raise ValueError(f"{box}: {error}") from None

    def choose_kind(self, kind):
        """The kind menu: make the Field of that kind, from what it holds
        (a number or an expression stays the default of the regions or of
        the painted sites), and open the panel of that kind only. The same
        kind opens its panel; expression on a number opens the line of what
        an expression may use and puts the cursor in the box, since a number
        is stored until an expression of the position is typed there; from
        result with nothing to read says so and keeps the value."""
        current = self._kind()
        if kind not in FIELD_KINDS:
            raise ValueError(f"no Field kind {kind!r}; kinds: {', '.join(FIELD_KINDS)}")
        simple = self._value if current in ("constant", "expression") else \
            self._value["default"] if current in ("piecewise", "painted") else 0.0
        if current == "profile" and kind == "expression":     # the formula it stands for
            try:
                simple = fields.profile_expression(self._value)
            except (KeyError, ValueError):
                pass
        number = float(simple) if isinstance(simple, (int, float)) else 0.0
        value = None
        if kind == current or (kind == "expression" and current == "constant"):
            pass
        elif kind == "constant":
            value = number
        elif kind == "expression":
            value = simple
        elif kind == "piecewise":
            value = {"kind": "piecewise", "default": simple, "pieces": []}
        elif kind == "profile":
            value = {"kind": "profile", "name": "gaussian", "params": {}}
        elif kind == "interpolated":
            value = {"kind": "interpolated", "points": [[0.0, 0.0, number]], "length": 2.0}
        elif kind == "painted":
            value = {"kind": "painted", "sites": [], "tol": 0.1, "default": number}
        else:
            value = self._result_value()
            if value is None:              # nothing to read: say so, keep the value
                self.panel_kind = "from_result"
                self._sync_panel()
                return
        self.panel_kind = None if kind == "constant" else kind
        if value is not None:
            self._commit_draft(value)      # the form shows it again: set_value, _sync_panel
        self._sync_panel()
        if kind == "expression":
            self.edit.setFocus()
            self.edit.selectAll()
        self._look()

    def add_piece(self):
        if not self._piecewise_shown() or not self.regions:
            return
        used = {p["region"] for p in self._value["pieces"]}
        region = next((r for r, _ in self.regions if r not in used), self.regions[0][0])
        value = self._read_pieces()
        value["pieces"].append({"region": region, "value": value["default"]})
        self._commit_draft(value)

    def remove_piece(self, index):
        if not self._piecewise_shown():
            return
        value = self._read_pieces()
        del value["pieces"][index]
        self._commit_draft(value)

    # ---- the value
    def value(self):
        if isinstance(self._draft, ValueError):
            raise self._draft
        if self._draft is not None:
            return self._draft
        if self._kind() == "piecewise":
            return self._read_pieces()
        if self._kind() in STRUCTURED:
            return self._value
        return parse_field(self.edit.text())

    def live_value(self):
        """What is being typed, if it is a valid Field, else None."""
        try:
            return fields.normalize(self.value())
        except (fields.FieldError, ValueError, TypeError, KeyError):
            return None

    def set_value(self, value):
        self._value = value
        structured = isinstance(value, dict)
        self._shown = _summary(value, self.regions) if structured else format_field(value)
        self._quiet(self.edit, self.edit.setText, self._shown)
        self.edit.setReadOnly(structured)
        self.edit.setToolTip("edit it in the panel below; the button beside it changes its kind"
                             if structured else "")
        kind = self._kind()
        if self.button is None:                 # constant only: the marker says the kind
            self.marker.setText("" if kind == "constant" else FIELD_KINDS[kind][0])
            self.marker.setVisible(kind != "constant")
            return
        self.button.setText(FIELD_KINDS[kind][0])
        font = self.button.font()
        font.setBold(kind != "constant")
        self.button.setFont(font)
        self.button.setToolTip(
            ("a number; " if kind == "constant" else
             f"{FIELD_KINDS[kind][0]}: {FIELD_KINDS[kind][2]}; ") +
            "click to choose the kind of this Field: a number, an expression of the position, "
            "piecewise per region, a profile, interpolated, painted, or from a result")
        if structured:                          # its panel is where it is edited
            self.panel_kind = kind
        elif self.panel_kind != "expression":   # the line stays while it is typed
            self.panel_kind = None
        self._sync_panel()


class VectorFieldEditor(Editor):
    """One Field editor per component."""

    preview = Signal()

    def __init__(self, param, regions=(), parent=None, sources=()):
        super().__init__(param, parent)
        self.components = []
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        for i, axis in enumerate("xyz"[:param.length]):
            editor = FieldEditor(param, regions, suffix=f"_{axis}", sources=sources)
            editor.edit.setPlaceholderText(axis)
            editor.setToolTip(f"{param.doc}, {axis} component\n\n{FIELD_HELP}")
            editor.committed.connect(self.committed)
            editor.preview.connect(self.preview)
            grid.addWidget(QLabel(axis), i, 0)
            grid.addWidget(editor, i, 1)
            self.components.append(editor)
        self.layout_.addLayout(grid, 1)

    @property
    def edits(self):
        return [editor.edit for editor in self.components]

    def value(self):
        return [editor.value() for editor in self.components]

    def live_value(self):
        values = [editor.live_value() for editor in self.components]
        return None if any(v is None for v in values) else values

    def set_value(self, value):
        for editor, v in zip(self.components, value):
            editor.set_value(v)
        # the kind buttons as wide as the widest, so that the components' boxes line up
        # whatever kind each one shows ("f(r)" beside "expression")
        buttons = [editor.button for editor in self.components if editor.button is not None]
        width = max((button.sizeHint().width() for button in buttons), default=0)
        for button in buttons:
            button.setMinimumWidth(width)


class IntEditor(Editor):
    def __init__(self, param, parent=None):
        super().__init__(param, parent)
        self.spin = QSpinBox()
        self.spin.setObjectName(f"spin_{param.name}")
        self.spin.setKeyboardTracking(False)       # commit on Enter, focus-out, arrows
        self.spin.setRange(param.minimum if param.minimum is not None else -INT_LIMIT,
                           param.maximum if param.maximum is not None else INT_LIMIT)
        self.spin.valueChanged.connect(lambda _: self.committed.emit())
        self.layout_.addWidget(self.spin)

    def value(self):
        return self.spin.value()

    def set_value(self, value):
        self._quiet(self.spin, self.spin.setValue, int(value))


class IntVectorEditor(Editor):
    def __init__(self, param, parent=None):
        super().__init__(param, parent)
        self.spins = []
        for i in range(param.length):
            spin = QSpinBox()
            spin.setObjectName(f"spin_{param.name}_{i}")
            spin.setKeyboardTracking(False)
            spin.setRange(param.minimum if param.minimum is not None else -INT_LIMIT, INT_LIMIT)
            spin.valueChanged.connect(lambda _: self.committed.emit())
            self.layout_.addWidget(spin)
            self.spins.append(spin)

    def value(self):
        return [s.value() for s in self.spins]

    def set_value(self, value):
        for spin, v in zip(self.spins, value):
            self._quiet(spin, spin.setValue, int(v))


class FloatVectorEditor(Editor):
    """One number per component, each a line of text; for an optional
    parameter every box left empty is None (the entry's own default, the
    k-mesh of an LDOS), and the boxes say so."""

    def __init__(self, param, parent=None):
        super().__init__(param, parent)
        self.edits = []
        for i in range(param.length):
            edit = QLineEdit()
            edit.setObjectName(f"edit_{param.name}_{i}")
            if getattr(param, "optional", False):
                edit.setPlaceholderText("empty")
            edit.editingFinished.connect(self._finished)
            self.layout_.addWidget(edit)
            self.edits.append(edit)
        self._shown = None

    def _finished(self):
        if [e.text() for e in self.edits] != self._shown:
            self.committed.emit()

    def value(self):
        texts = [e.text().strip() for e in self.edits]
        if getattr(self.param, "optional", False) and not any(texts):
            return None
        return [parse_float(text) for text in texts]

    def set_value(self, value):
        self._shown = [""] * len(self.edits) if value is None else \
            [format_number(float(v)) for v in value]
        for edit, text in zip(self.edits, self._shown):
            self._quiet(edit, edit.setText, text)


class CodeEditor(Editor):
    """Python source of a Python node: a monospace text box, committed with
    Apply (Ctrl+Return) or when the box loses the focus."""

    def __init__(self, param, parent=None):
        super().__init__(param, parent)
        self.text = QPlainTextEdit()
        self.text.setObjectName(f"code_{param.name}")
        self.text.setFont(theme.fixed_font(self.font().pointSizeF()))   # interface text
        self.text.setMinimumHeight(8 * self.text.fontMetrics().lineSpacing())
        self.text.setTabChangesFocus(False)
        self.text.installEventFilter(self)
        self.apply = QPushButton("Apply")
        self.apply.setObjectName(f"apply_{param.name}")
        self.apply.setToolTip("send the code (Ctrl+Return); it runs in the worker, in a "
                              "trusted document only")
        self.apply.clicked.connect(self._finished)
        self.layout_.addWidget(self.text, 1)
        self.outer.addWidget(self.apply)
        self._shown = None

    def eventFilter(self, watched, event):
        if watched is self.text:
            if event.type() == QEvent.Type.FocusOut:
                self._finished()
            elif event.type() == QEvent.Type.KeyPress \
                    and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._finished()
                return True
        return super().eventFilter(watched, event)

    def _finished(self):
        if self.text.toPlainText() != self._shown:
            self.committed.emit()

    def value(self):
        return self.text.toPlainText()

    def set_value(self, value):
        self._shown = value
        if self.text.toPlainText() != value:
            self._quiet(self.text, self.text.setPlainText, value)


class BoolEditor(Editor):
    def __init__(self, param, parent=None):
        super().__init__(param, parent)
        self.box = QCheckBox()
        self.box.setObjectName(f"check_{param.name}")
        self.box.toggled.connect(lambda _: self.committed.emit())
        self.layout_.addWidget(self.box)

    def value(self):
        return self.box.isChecked()

    def set_value(self, value):
        self._quiet(self.box, self.box.setChecked, bool(value))


class ChoiceEditor(Editor):
    """A fixed list, or pyqula's own names (param.source) with free text
    allowed: the engine checks the name against pyqula when it runs."""

    def __init__(self, param, names=None, parent=None):
        super().__init__(param, parent)
        self.combo = QComboBox()
        self.combo.setObjectName(f"choice_{param.name}")
        items = list(param.choices or names or [])
        if param.optional:
            items = [NONE_TEXT] + items
        self.combo.addItems(items)
        if param.source:
            self.combo.setEditable(True)
            self.combo.lineEdit().editingFinished.connect(self._finished)
        self.combo.activated.connect(lambda _: self._finished())
        self.layout_.addWidget(self.combo)
        self._shown = None

    def _finished(self):
        if self.combo.currentText() != self._shown:
            self.committed.emit()

    def value(self):
        text = self.combo.currentText().strip()
        return None if self.param.optional and text in ("", NONE_TEXT) else text

    def set_value(self, value):
        self._shown = NONE_TEXT if value is None else str(value)
        index = self.combo.findText(self._shown)
        if index < 0:
            self._quiet(self.combo, self.combo.addItem, self._shown)
            index = self.combo.findText(self._shown)
        self._quiet(self.combo, self.combo.setCurrentIndex, index)


class PositionsEditor(Editor):
    """Positions are picked on the structure canvas; here only counted."""

    def __init__(self, param, parent=None):
        super().__init__(param, parent)
        self.label = QLabel()
        self.label.setObjectName(f"count_{param.name}")
        self.clear = QPushButton("Clear")
        self.clear.setObjectName(f"clear_{param.name}")
        self.clear.clicked.connect(self._clear)
        self.layout_.addWidget(self.label, 1)
        self.layout_.addWidget(self.clear)
        self._value = []

    def _clear(self):
        if self._value:
            self._value = []
            self.committed.emit()

    def value(self):
        return self._value

    def set_value(self, value):
        self._value = [list(p) for p in value]
        n = len(self._value)
        self.label.setText(f"{n} position{'s' if n != 1 else ''} (pick on the Structure tab)")
        self.clear.setEnabled(bool(n))


def make_editor(param, names=None, regions=(), sources=()):
    """The editor for a registry parameter (subclasses first); regions:
    [(id, name)] a piecewise Field can use; sources: result_sources() a
    from_result Field can read."""
    if isinstance(param, VectorFieldParam):
        return VectorFieldEditor(param, regions, sources=sources)
    if isinstance(param, FieldParam):
        return FieldEditor(param, regions, sources=sources)
    if isinstance(param, IntParam) and param.optional:
        integer = not isinstance(param, FloatParam)
        return LineEditor(param, lambda t: parse_optional(t, integer),
                          lambda v: "" if v is None else format_number(v), "default")
    if isinstance(param, SeedParam):
        return LineEditor(param, lambda t: int(parse_float(t)) if parse_float(t).is_integer()
                          else parse_float(t), str)
    if isinstance(param, FloatParam):
        return LineEditor(param, parse_float, format_number)
    if isinstance(param, IntParam):
        return IntEditor(param)
    if isinstance(param, FloatVectorParam):
        return FloatVectorEditor(param)
    if isinstance(param, IntVectorParam):
        return IntVectorEditor(param)
    if isinstance(param, CodeParam):
        return CodeEditor(param)
    if isinstance(param, KPathParam):
        return LineEditor(param, parse_kpath, format_kpath,
                          "default path, or e.g. G K M G, (0.5, 0) for reduced coordinates")
    if isinstance(param, ConditionParam):
        return LineEditor(param, str.strip, str, "a condition on x, y, z, r")
    if isinstance(param, TextParam):
        return LineEditor(param, str.strip, str, param.hint)
    if isinstance(param, BoolParam):
        return BoolEditor(param)
    if isinstance(param, ChoiceParam):
        return ChoiceEditor(param, (names or {}).get(param.source))
    if isinstance(param, PositionsParam):
        return PositionsEditor(param)
    raise TypeError(f"no editor for {type(param).__name__}")
