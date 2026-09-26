"""Editors for registry parameters (PLAN.md 3.2: the properties form is
derived from an entry's declaration). One editor per parameter type; each
shows a JSON value, returns the edited one from value() (raising
ValueError when the text is not even a number), and emits committed when
the user finishes an edit. Validation proper is the registry's: the panel
sends the value as a command and shows the refusal.

Fields (term parameters) are edited as text: a number, or an expression of
x, y, z, r (PLAN.md 3.8). The f(r) editor with profiles and regions is
phase 3.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QWidget)

from guiqula.core import fields
from guiqula.registry.params import (BoolParam, ChoiceParam, FieldParam, FloatParam, IntParam,
                                     IntVectorParam, PositionsParam, SeedParam, VectorFieldParam)

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


class Editor(QWidget):
    committed = Signal()

    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
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


class FieldEditor(LineEditor):
    def __init__(self, param, parent=None):
        super().__init__(param, parse_field, format_field,
                         "a constant" if not param.native else "number or f(x, y, z)", parent)
        self.marker = QLabel("")
        self.marker.setObjectName(f"fieldKind_{param.name}")
        self.marker.setMinimumWidth(28)
        self.layout_.addWidget(self.marker)
        self.setToolTip(param.doc + ("\n\n" + FIELD_HELP if param.native else
                                     "\n\nConstant only: the pyqula call behind it does not "
                                     "take a function of position."))

    def set_value(self, value):
        super().set_value(value)
        self.marker.setText("" if fields.is_constant(value) else "f(r)")


class VectorFieldEditor(Editor):
    def __init__(self, param, parent=None):
        super().__init__(param, parent)
        self.edits = []
        for i, axis in enumerate("xyz"[:param.length]):
            edit = QLineEdit()
            edit.setObjectName(f"edit_{param.name}_{axis}")
            edit.setPlaceholderText(axis)
            edit.setToolTip(f"{param.doc}, {axis} component\n\n{FIELD_HELP}")
            edit.editingFinished.connect(self._finished)
            self.layout_.addWidget(edit)
            self.edits.append(edit)
        self._shown = None

    def _finished(self):
        if [e.text() for e in self.edits] != self._shown:
            self.committed.emit()

    def value(self):
        return [parse_field(e.text()) for e in self.edits]

    def set_value(self, value):
        self._shown = [format_field(v) for v in value]
        for edit, text in zip(self.edits, self._shown):
            self._quiet(edit, edit.setText, text)


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


def make_editor(param, names=None):
    """The editor for a registry parameter (subclasses first)."""
    if isinstance(param, VectorFieldParam):
        return VectorFieldEditor(param)
    if isinstance(param, FieldParam):
        return FieldEditor(param)
    if isinstance(param, SeedParam):
        return LineEditor(param, lambda t: int(parse_float(t)) if parse_float(t).is_integer()
                          else parse_float(t), str)
    if isinstance(param, FloatParam):
        return LineEditor(param, parse_float, format_number)
    if isinstance(param, IntParam):
        return IntEditor(param)
    if isinstance(param, IntVectorParam):
        return IntVectorEditor(param)
    if isinstance(param, BoolParam):
        return BoolEditor(param)
    if isinstance(param, ChoiceParam):
        return ChoiceEditor(param, (names or {}).get(param.source))
    if isinstance(param, PositionsParam):
        return PositionsEditor(param)
    raise TypeError(f"no editor for {type(param).__name__}")
