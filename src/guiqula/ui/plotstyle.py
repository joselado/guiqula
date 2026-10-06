"""The style of a result plot (decisions 164 to 169): what the user may
change of how a plot looks, per plot kind, and the popup that changes it.

The catalogue, OPTIONS, is one list per plot kind (the kinds of
ui/plots.py) of the cosmetics worth changing on that kind and nothing
else: the width and the colour of a curve, the size of the points and the
colour map of coloured bands, the colour map, its saturation and the
shading of a map, the size of the atoms, the colour map and the bonds of a
result drawn on them, and the length, the width and the colour of the
arrows of a vector per site. A scalar result (a table of numbers) has no
style. Every option is a dict with its name (the key of a style dict, and
of the window action plot_style), its label (the words of the physics, on
the control), its type (number, with a range and a step; choice, with its
choices; color, a matplotlib colour; bool), its default and its tip (the
engine's words, in the tooltip). An option whose default is None takes it
from the result's plot spec at drawing time (a colour map the spec names,
a diverging map for a quantity symmetric about zero) or from the theme (a
curve's first cycle colour, the arrows' colour), so that a style never
bakes one theme's colour into the other.

A style is a dict of option name to value, holding only what differs from
the defaults (clean drops the rest, and refuses or drops what is not an
option of the kind, as the caller asks): it is what the window keeps per
result view, saves in the Document's ui block next to the overlays and
hands ui/plots.py's draw, so the exported figure takes it too.

The popup (StylePopup) is one form of the kind's options, opened by the
Style button of a result's bar; each control emits the whole style as it
changes, and Reset empties it.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QWidget)

# the colour maps offered (matplotlib's names): sequential ones first, then the diverging
# ones (symmetric about zero), the cyclic one and the greys
COLOR_MAPS = ("viridis", "inferno", "magma", "plasma", "cividis", "hot", "Blues", "Reds",
              "coolwarm", "RdBu_r", "bwr", "seismic", "twilight", "gray")
TYPES = ("number", "choice", "color", "bool")


def _number(name, label, default, minimum, maximum, step, tip):
    return {"name": name, "label": label, "type": "number", "default": default,
            "minimum": minimum, "maximum": maximum, "step": step, "tip": tip}


def _choice(name, label, default, choices, tip):
    return {"name": name, "label": label, "type": "choice", "default": default,
            "choices": tuple(choices), "tip": tip}


def _color(name, label, tip):
    return {"name": name, "label": label, "type": "color", "default": None, "tip": tip}


def _bool(name, label, default, tip):
    return {"name": name, "label": label, "type": "bool", "default": default, "tip": tip}


_CMAP_TIP = "the colour map of the colour bar (matplotlib's name)"
_ATOM_SIZE = _number("atom_size", "atom size", 1.0, 0.2, 3.0, 0.1,
                     "the radius of the atoms, as a multiple of the usual one (0.22 in "
                     "units of the first-neighbour distance)")
_BONDS = _bool("bonds", "bonds", True, "draw the first-neighbour bonds between the atoms")

OPTIONS = {
    "lines": [
        _number("linewidth", "line width", 1.2, 0.2, 8.0, 0.2,
                "the width of the curves, in points (the overlays take it too)"),
        _color("color", "line colour",
               "the colour of the result's own curves; an overlay keeps its own"),
        _bool("dots", "dots on the points", False,
              "a dot at every data point of the curves, three line widths across"),
        _bool("fill", "fill under the curve", False,
              "fill between the curves and zero, as a density of states is often drawn"),
    ],
    "colored_scatter": [
        _number("size", "point size", 6.0, 1.0, 80.0, 1.0,
                "the area of the points, in points squared (matplotlib's s)"),
        _choice("cmap", "colour map", "coolwarm", COLOR_MAPS, _CMAP_TIP),
        _number("saturate", "saturate at", 1.0, 0.05, 1.0, 0.05,
                "the fraction of the largest |value| at which the colour scale saturates: "
                "below 1 the small values get the whole scale"),
    ],
    "heatmap": [
        _choice("cmap", "colour map", None, COLOR_MAPS,
                _CMAP_TIP + "; the result's own by default (a diverging one for a quantity "
                "symmetric about zero)"),
        _number("saturate", "saturate at", 1.0, 0.05, 1.0, 0.05,
                "the fraction of the largest value at which the colour scale saturates "
                "(both ends of a scale centred at zero): below 1 the faint features show"),
        _bool("smooth", "smooth", False,
              "shade the map between the grid points (Gouraud) instead of drawing one flat "
              "cell per point; a map that is not a grid is drawn as points either way"),
    ],
    "structure_scalar": [
        _ATOM_SIZE,
        _choice("cmap", "colour map", None, COLOR_MAPS,
                _CMAP_TIP + "; the result's own by default (a diverging one for a quantity "
                "symmetric about zero, a sequential one otherwise)"),
        _BONDS,
    ],
    "structure_vector": [
        _number("arrow_length", "arrow length", 1.0, 0.2, 3.0, 0.1,
                "the length of the longest arrow, as a multiple of the usual one (0.8 "
                "first-neighbour distances)"),
        _number("arrow_width", "arrow width", 1.0, 0.2, 3.0, 0.1,
                "the width of the arrows' shafts, as a multiple of the usual one"),
        _color("arrow_color", "arrow colour", "the colour of the arrows; the theme's by default"),
        _ATOM_SIZE,
        _choice("cmap", "colour map", "coolwarm", COLOR_MAPS,
                _CMAP_TIP + " of the z component, drawn as a dot on each atom"),
        _BONDS,
    ],
    "scalar": [],
}


def options(kind):
    """The options of a plot kind ([] for one without any, or unknown)."""
    return list(OPTIONS.get(kind, []))


def option(kind, name):
    """One option of a kind by name, or None."""
    return next((o for o in OPTIONS.get(kind, []) if o["name"] == name), None)


def defaults(kind):
    """{name: default} of a kind (None where the drawing decides)."""
    return {o["name"]: o["default"] for o in OPTIONS.get(kind, [])}


def valid_color(value):
    """Whether matplotlib reads a colour from this (a name, a hex string,
    a cycle colour such as C0)."""
    from matplotlib.colors import is_color_like
    return isinstance(value, str) and is_color_like(value)


def _check(opt, value):
    """The value as the option's type, or ValueError."""
    kind = opt["type"]
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{opt['name']} takes a number, not {value!r}")
        value = float(value)
        if not opt["minimum"] <= value <= opt["maximum"]:
            raise ValueError(f"{opt['name']} is between {opt['minimum']:g} and "
                             f"{opt['maximum']:g}, not {value:g}")
        return value
    if kind == "choice":
        if value not in opt["choices"]:
            raise ValueError(f"{opt['name']} is one of {', '.join(opt['choices'])}, "
                             f"not {value!r}")
        return value
    if kind == "color":
        if not valid_color(value):
            raise ValueError(f"{opt['name']} takes a colour matplotlib knows (a name or "
                             f"#rrggbb), not {value!r}")
        return value
    if not isinstance(value, bool):
        raise ValueError(f"{opt['name']} is true or false, not {value!r}")
    return value


def clean(kind, style, strict=True):
    """A style dict of a kind, checked: every value of its option's type and
    within its range, and only what differs from the defaults kept (a None
    stands for the default, so it is dropped). An option the kind does not
    have, or a value it refuses, is a ValueError when strict, else left out
    (a style saved for a result that now draws another kind)."""
    style = style if isinstance(style, dict) else {}
    cleaned = {}
    for name, value in style.items():
        opt = option(kind, name)
        if opt is None:
            if strict:
                names = ", ".join(o["name"] for o in OPTIONS.get(kind, [])) or "none"
                raise ValueError(f"a {kind} plot has no style option {name!r}; its options "
                                 f"are {names}")
            continue
        if value is None:
            continue
        try:
            value = _check(opt, value)
        except ValueError:
            if strict:
                raise
            continue
        if value != opt["default"]:
            cleaned[name] = value
    return cleaned


def resolve(kind, style):
    """{name: value} of every option of a kind: the style's value, else the
    default (None where the drawing decides)."""
    full = defaults(kind)
    full.update(clean(kind, style, strict=False))
    return full


class ColorButton(QToolButton):
    """A button showing a colour (or "default"), opening a colour dialog;
    its value is a hex string or None."""

    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = None
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.clicked.connect(self.choose)
        self._show()

    def set_value(self, value):
        self.value = value if valid_color(value) else None
        self._show()

    def _show(self):
        from matplotlib.colors import to_hex
        if self.value is None:
            self.setText("default")
            self.setStyleSheet("")
            return
        hexa = to_hex(self.value)
        self.setText(hexa)
        light = QColor(hexa).lightnessF() > 0.6
        self.setStyleSheet(f"QToolButton {{ background: {hexa}; "
                           f"color: {'#000000' if light else '#ffffff'}; }}")

    def choose(self):
        """The colour dialog; the popup holding the button closes when the
        dialog takes the focus (a popup closes on any click outside it), so
        it is shown again where it was once the dialog is done."""
        from matplotlib.colors import to_hex
        start = QColor(to_hex(self.value)) if self.value is not None else QColor("#1f77b4")
        popup = self.window()
        was_popup = bool(popup.windowFlags() & Qt.WindowType.Popup) and popup.isVisible()
        position = popup.pos()
        color = QColorDialog.getColor(start, self, "Choose a colour")
        if color.isValid():
            self.set_value(color.name())
            self.changed.emit(self.value)
        if was_popup and not popup.isVisible():
            popup.move(position)
            popup.show()


class StylePopup(QFrame):
    """The form of a plot kind's options (one control per option, named
    style_<option>_<id>), and Reset; `changed` carries the style (only
    what differs from the defaults) after every change."""

    changed = Signal(object)

    def __init__(self, suffix="", parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName(f"stylePopup{suffix}")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.suffix = suffix
        self.kind = None
        self.controls = {}
        self._filling = False
        self.form = QFormLayout()
        self.form.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("Style")
        self.title.setObjectName(f"styleTitle{suffix}")
        self.reset = QPushButton("Reset")
        self.reset.setObjectName(f"styleReset{suffix}")
        self.reset.setToolTip("the plot drawn as it is by default")
        self.reset.clicked.connect(self._reset)
        head = QHBoxLayout()
        head.addWidget(self.title, 1)
        head.addWidget(self.reset)
        layout = QFormLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addRow(head)
        layout.addRow(self.form)

    def set_kind(self, kind, style=None):
        """Build the controls of a kind (again only when the kind changed)
        and show a style in them."""
        if kind != self.kind:
            while self.form.rowCount():
                self.form.removeRow(0)
            self.controls = {}
            self.kind = kind
            for opt in options(kind):
                self.form.addRow(opt["label"], self._control(opt))
        self.show_style(style or {})

    def _control(self, opt):
        name = opt["name"]
        if opt["type"] == "number":
            widget = QDoubleSpinBox()
            widget.setRange(opt["minimum"], opt["maximum"])
            widget.setSingleStep(opt["step"])
            widget.setDecimals(2 if opt["step"] < 1 else 0)
            widget.setValue(opt["default"])
            widget.valueChanged.connect(lambda value, n=name: self._set(n, float(value)))
        elif opt["type"] == "choice":
            widget = QComboBox()
            if opt["default"] is None:
                widget.addItem("default", None)
            for choice in opt["choices"]:
                widget.addItem(choice, choice)
            widget.currentIndexChanged.connect(
                lambda index, w=widget, n=name: self._set(n, w.itemData(index)))
        elif opt["type"] == "color":
            widget = ColorButton()
            widget.changed.connect(lambda value, n=name: self._set(n, value))
        else:
            widget = QCheckBox()
            widget.setChecked(bool(opt["default"]))
            widget.toggled.connect(lambda on, n=name: self._set(n, bool(on)))
        widget.setObjectName(f"style_{name}{self.suffix}")
        widget.setToolTip(opt["tip"])
        self.controls[name] = widget
        return widget

    def show_style(self, style):
        """The controls set to a style (the defaults where it says nothing)
        without emitting it."""
        self._filling = True
        try:
            for name, value in resolve(self.kind, style).items():
                widget = self.controls.get(name)
                opt = option(self.kind, name)
                if widget is None:
                    continue
                if opt["type"] == "number":
                    widget.setValue(float(value))
                elif opt["type"] == "choice":
                    widget.setCurrentIndex(max(widget.findData(value), 0))
                elif opt["type"] == "color":
                    widget.set_value(value)
                else:
                    widget.setChecked(bool(value))
        finally:
            self._filling = False

    def style(self):
        """What the controls hold, cleaned (only what differs from the
        defaults)."""
        values = {}
        for name, widget in self.controls.items():
            opt = option(self.kind, name)
            if opt["type"] == "number":
                values[name] = float(widget.value())
            elif opt["type"] == "choice":
                values[name] = widget.currentData()
            elif opt["type"] == "color":
                values[name] = widget.value
            else:
                values[name] = bool(widget.isChecked())
        return clean(self.kind, values, strict=False)

    def _set(self, name, value):
        if not self._filling:
            self.changed.emit(self.style())

    def _reset(self):
        self.show_style({})
        self.changed.emit({})

    def set_value(self, name, value):
        """Set one control as the user would (emits the style)."""
        if name not in self.controls:
            raise KeyError(f"a {self.kind} plot has no style option {name!r}")
        self.show_style(dict(self.style(), **{name: value}))
        self.changed.emit(self.style())
