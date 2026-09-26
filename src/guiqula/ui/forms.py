"""Editors for registry parameters (PLAN.md 3.2: the properties form is
derived from an entry's declaration). One editor per parameter type; each
shows a JSON value, returns the edited one from value() (raising
ValueError when the text is not even a number), and emits committed when
the user finishes an edit. Validation proper is the registry's: the panel
sends the value as a command and shows the refusal.

Fields (term parameters, PLAN.md 3.8) are edited as text: a number, or an
expression of x, y, z, r. The f(r) button next to a Field opens its panel:
the kind (a number or an expression, one value per region, or a result
read site by site) and, per region, a value for each region plus the
default; for a result, the calculation (of another system, drawn on the
sites), its array, the component and a scale. A Field editor emits
preview when the user looks at it (focus, typing, the panel), with the
value being typed when it parses, so the window can draw the Field on the
structure before anything runs. Constant-only parameters (the pyqula call
behind them takes no function of position) have no f(r) button.
"""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from guiqula.core import fields
from guiqula.registry.params import (BoolParam, ChoiceParam, CodeParam, ConditionParam,
                                     FieldParam, FloatParam, FloatVectorParam, IntParam,
                                     IntVectorParam, PositionsParam, SeedParam, TextParam,
                                     VectorFieldParam)

INT_LIMIT = 2**31 - 1
NONE_TEXT = "(none)"
FIELD_HELP = ("A number, or an expression of the position: x, y, z, r (distance from the "
              "origin), pi, and numpy functions such as sin, cos, exp, tanh, sqrt "
              "(e.g. 0.3*tanh(x/4)).")


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

    def _quiet(self, widget, setter, value):
        widget.blockSignals(True)
        try:
            setter(value)
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


EXPRESSION_KIND, PIECEWISE_KIND = "number or f(x, y, z)", "one value per region"
RESULT_KIND = "from a result"
KINDS = (EXPRESSION_KIND, PIECEWISE_KIND, RESULT_KIND)
COMPONENTS = ((None, "the value"), (0, "x"), (1, "y"), (2, "z"))
FIELD_BUTTON_TIPS = {
    "constant": "make this a function of the position: an expression, one value per region, "
                "or a result of another system",
    "expression": "an expression of the position (bold); the panel explains what it may use",
    "piecewise": "one value per region (bold); the panel edits the values",
    "from_result": "read from a result of another system, site by site (bold)"}


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
    """One line for a piecewise or a from_result Field."""
    if value.get("kind") == "from_result":
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
        self.region.activated.connect(lambda _: editor._edited())
        self.value.editingFinished.connect(editor._piece_finished)
        self.value.textEdited.connect(lambda _: editor._look())
        self.remove.clicked.connect(lambda: editor.remove_piece(index))
        editor.install(self.value)

    def widgets(self):
        return (self.region, self.value, self.remove)


class FieldEditor(Editor):
    """A scalar Field with its f(r) panel."""

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
        self.layout_.addWidget(self.edit, 1)
        self.layout_.addWidget(self.marker)
        self.button = None
        self.rows = []
        self._value = None
        self._shown = None
        self._draft = None
        self.setToolTip(param.doc + ("\n\n" + FIELD_HELP if param.native else
                                     "\n\nConstant only: the pyqula call behind it does not "
                                     "take a function of position."))
        if param.native:
            self.button = QToolButton()
            self.button.setText("f(r)")
            self.button.setCheckable(True)
            self.button.setObjectName(f"fieldButton_{self.name}")
            self.button.toggled.connect(self._toggle_panel)
            self.layout_.addWidget(self.button)
            self._build_panel()

    def install(self, widget):
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn:
            self._look()
        return False

    # ---- the panel
    def _build_panel(self):
        self.panel = QFrame()
        self.panel.setObjectName(f"fieldPanel_{self.name}")
        self.panel.setFrameShape(QFrame.Shape.StyledPanel)
        column = QVBoxLayout(self.panel)
        column.setContentsMargins(6, 4, 6, 4)
        self.kind = QComboBox()
        self.kind.setObjectName(f"fieldKindBox_{self.name}")
        self.kind.addItems(list(KINDS))
        self.kind.activated.connect(self._kind_chosen)
        column.addWidget(self.kind)
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
        self.no_results = QLabel("No result of another system drawn on the sites yet: run "
                                 "one there first (a texture, a density, an LDOS).")
        self.no_results.setWordWrap(True)
        self.no_results.setObjectName(f"fieldNoResults_{self.name}")
        column.addWidget(self.no_results)
        self.help = QLabel(FIELD_HELP)
        self.help.setWordWrap(True)
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
        self.no_regions = QLabel("This system has no region yet: make one on the Geometry "
                                 "toolbar (Add region, or Region from selection).")
        self.no_regions.setWordWrap(True)
        column.addWidget(self.pieces)
        column.addWidget(self.add)
        column.addWidget(self.no_regions)
        self.order = QLabel("Where regions overlap, the lower one wins.")
        self.order.setObjectName(f"pieceOrder_{self.name}")
        column.addWidget(self.order)
        self.outer.addWidget(self.panel)
        self.panel.hide()

    def _toggle_panel(self, shown):
        self.panel.setVisible(shown)
        if shown:
            self._look()

    def open_panel(self, shown=True):
        if self.button is not None:
            self.button.setChecked(shown)

    def _mode(self):
        """0: a number or an expression; 1: piecewise; 2: from a result."""
        if isinstance(self._value, dict):
            return 2 if self._value.get("kind") == "from_result" else 1
        return 0

    def _piecewise_shown(self):
        return self._mode() == 1

    def _sync_panel(self):
        mode = self._mode()
        piecewise = mode == 1
        self._quiet(self.kind, self.kind.setCurrentIndex, mode)
        self.help.setVisible(mode == 0)
        self.result_box.setVisible(mode == 2)
        self.no_results.setVisible(mode == 2 and not self.sources)
        if mode == 2:
            self._sync_result()
        self.pieces.setVisible(piecewise)
        self.add.setVisible(piecewise)
        self.add.setEnabled(bool(self.regions))
        self.no_regions.setVisible(piecewise and not self.regions)
        self.order.setVisible(piecewise and len(self._value["pieces"]) > 1 if piecewise else False)
        pieces = self._value["pieces"] if piecewise else []
        if len(pieces) != len(self.rows):
            for row in self.rows:
                for widget in row.widgets():
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
        if self._mode() != 2:
            return
        if new_calc:
            value = self._result_value(self.result_calc.currentData())
        else:
            value = dict(self._value, array=self.result_array.currentData(),
                         component=self.result_component.currentData())
            if new_array:
                source = self._source(value["calculation"])
                components = source[2].get(value["array"]) if source else None
                value["component"] = None if components is None else 0
            try:
                value["scale"] = parse_float(self.result_scale.text())
            except ValueError:
                pass
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
        self._draft = value
        self.committed.emit()
        self._draft = None

    def _kind_chosen(self, index):
        mode = self._mode()
        if index == mode:
            return
        simple = self._value if mode == 0 else \
            self._value["default"] if mode == 1 else 0.0
        if index == 0:
            self._commit_draft(simple)
        elif index == 1:
            self._commit_draft({"kind": "piecewise", "default": simple, "pieces": []})
        else:
            value = self._result_value()
            if value is None:              # nothing to read: say so, keep the value
                self._quiet(self.kind, self.kind.setCurrentIndex, mode)
                self.no_results.show()
                return
            self._commit_draft(value)

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
        if self._draft is not None:
            return self._draft
        if self._mode() == 1:
            return self._read_pieces()
        if self._mode() == 2:
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
        self.edit.setToolTip("edit it in the f(r) panel" if structured else "")
        kind = fields.kind_of(value) if value is not None else "constant"
        self.marker.setText({"constant": "", "expression": "f(r)", "piecewise": "per region",
                             "from_result": "result"}[kind])
        if self.button is not None:
            self.marker.hide()                  # the button says it instead
            font = self.button.font()
            font.setBold(kind != "constant")
            self.button.setFont(font)
            self.button.setToolTip(FIELD_BUTTON_TIPS[kind])
            self._sync_panel()
            if structured and not self.button.isChecked():
                self.open_panel()


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
    """One number per component, each a line of text."""

    def __init__(self, param, parent=None):
        super().__init__(param, parent)
        self.edits = []
        for i in range(param.length):
            edit = QLineEdit()
            edit.setObjectName(f"edit_{param.name}_{i}")
            edit.editingFinished.connect(self._finished)
            self.layout_.addWidget(edit)
            self.edits.append(edit)
        self._shown = None

    def _finished(self):
        if [e.text() for e in self.edits] != self._shown:
            self.committed.emit()

    def value(self):
        return [parse_float(e.text()) for e in self.edits]

    def set_value(self, value):
        self._shown = [format_number(float(v)) for v in value]
        for edit, text in zip(self.edits, self._shown):
            self._quiet(edit, edit.setText, text)


class CodeEditor(Editor):
    """Python source of a Python node: a monospace text box, committed with
    Apply (Ctrl+Return) or when the box loses the focus."""

    def __init__(self, param, parent=None):
        super().__init__(param, parent)
        self.text = QPlainTextEdit()
        self.text.setObjectName(f"code_{param.name}")
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
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
