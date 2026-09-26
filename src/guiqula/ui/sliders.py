"""Sliders (decision 13.10): a parameter attached to a slider, for live
changes; with the automatic re-run of cheap results (Run menu) the plots
follow the drag. A slider holds a number of an entry (the same parameters
a sweep can change: a Field of a term, a number of an op, a calculation,
the lattice, the mean field or a classical model), within a range; a drag
is one undo step. The window keeps the sliders with the view state."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSlider, QToolButton, QVBoxLayout, QWidget)

STEPS = 200          # positions of a slider between its minimum and its maximum


def fraction_of(value, minimum, maximum):
    if maximum == minimum:
        return 0
    return int(round(min(max((value - minimum) / (maximum - minimum), 0.0), 1.0) * STEPS))


class SliderRow(QWidget):
    moved = Signal(int, float, bool)          # index, value, still dragging
    removed = Signal(int)

    def __init__(self, index, spec, parent=None):
        super().__init__(parent)
        self.index, self.spec = index, dict(spec)
        component = spec.get("component")
        text = f"{spec['entry']} {spec['param']}" + ("" if component is None else
                                                     f"[{'xyz'[component]}]")
        self.label = QLabel(text)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName(f"slider_{index}")
        self.slider.setRange(0, STEPS)
        self.value = QLabel("")
        self.value.setObjectName(f"sliderValue_{index}")
        self.value.setMinimumWidth(60)
        self.remove = QToolButton()
        self.remove.setText("×")
        self.remove.setObjectName(f"sliderRemove_{index}")
        self.remove.setToolTip("remove this slider (the parameter keeps its value)")
        self.remove.clicked.connect(lambda: self.removed.emit(self.index))
        self.slider.valueChanged.connect(lambda _: self._moved(self.slider.isSliderDown()))
        self.slider.sliderReleased.connect(lambda: self._moved(False))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.label)
        row.addWidget(QLabel(f"{spec['min']:g}"))
        row.addWidget(self.slider, 1)
        row.addWidget(QLabel(f"{spec['max']:g}"))
        row.addWidget(self.value)
        row.addWidget(self.remove)

    def number(self):
        low, high = self.spec["min"], self.spec["max"]
        return low + (high - low) * self.slider.value() / STEPS

    def show_value(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(fraction_of(value, self.spec["min"], self.spec["max"]))
        self.slider.blockSignals(False)
        self.value.setText(f"{value:.4g}")

    def _moved(self, dragging):
        value = self.number()
        self.value.setText(f"{value:.4g}")
        self.moved.emit(self.index, value, dragging)


class SlidersPanel(QWidget):
    """The rows of sliders and a line to add one."""
    add_requested = Signal(str, str, object, float, float)    # entry, param, component, range
    moved = Signal(int, float, bool)
    removed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sliders")
        self.rows = []
        self.column = QVBoxLayout()
        self.empty = QLabel("No slider yet: name a parameter below (a term's Field, an op's "
                            "number, the mean field's U...) and its range.")
        self.empty.setWordWrap(True)
        self.entry, self.param = QLineEdit(), QLineEdit()
        self.component = QComboBox()
        self.minimum, self.maximum = QLineEdit("0"), QLineEdit("1")
        for widget, name, tip in ((self.entry, "sliderEntry", "t1, op2, c3, s1/meanfield, "
                                                              "s1/model, or s1 (its lattice)"),
                                  (self.param, "sliderParam", "the parameter's name"),
                                  (self.minimum, "sliderMin", "lowest value"),
                                  (self.maximum, "sliderMax", "highest value")):
            widget.setObjectName(name)
            widget.setPlaceholderText(tip)
        self.component.setObjectName("sliderComponent")
        for component, text in ((None, "—"), (0, "x"), (1, "y"), (2, "z")):
            self.component.addItem(text, component)
        add = QPushButton("Add slider")
        add.setObjectName("addSliderButton")
        add.clicked.connect(self._add)
        form = QGridLayout()
        form.addWidget(QLabel("entry"), 0, 0)
        form.addWidget(self.entry, 0, 1)
        form.addWidget(QLabel("parameter"), 0, 2)
        form.addWidget(self.param, 0, 3)
        form.addWidget(self.component, 0, 4)
        form.addWidget(QLabel("from"), 1, 0)
        form.addWidget(self.minimum, 1, 1)
        form.addWidget(QLabel("to"), 1, 2)
        form.addWidget(self.maximum, 1, 3)
        form.addWidget(add, 1, 4)
        layout = QVBoxLayout(self)
        layout.addWidget(self.empty)
        layout.addLayout(self.column)
        layout.addLayout(form)
        layout.addStretch(1)

    def _add(self):
        try:
            low, high = float(self.minimum.text()), float(self.maximum.text())
        except ValueError:
            low, high = 0.0, 1.0
        self.add_requested.emit(self.entry.text().strip(), self.param.text().strip(),
                                self.component.currentData(), low, high)

    def set_sliders(self, specs, values):
        """Rebuild the rows: specs [{entry, param, component, min, max}] and
        the current value of each (or None)."""
        for row in self.rows:
            self.column.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.rows = []
        for i, spec in enumerate(specs):
            row = SliderRow(i, spec)
            row.moved.connect(self.moved)
            row.removed.connect(self.removed)
            if values[i] is not None:
                row.show_value(values[i])
            self.column.addWidget(row)
            self.rows.append(row)
        self.empty.setVisible(not specs)

    def show_values(self, values):
        for row, value in zip(self.rows, values):
            if value is not None and not row.slider.isSliderDown():
                row.show_value(value)
