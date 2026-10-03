"""The bars of the drawings (PLAN.md phase 8, package P3): the structure
canvas, each result view and the k-space tab carry a bar with what that
drawing needs, Fit, Pan, Zoom and Save image and the tools of the drawing,
in place of matplotlib's navigation toolbar, whose Back, Forward, Subplots
and Customize did nothing useful here.

matplotlib's toolbar is still made, hidden, and kept as the canvas's
toolbar (canvas.toolbar): its pan and zoom modes are what Pan and Zoom turn
on, the views and ui/canvas_navigation.py read its mode, Fit is its home
when the drawing has no fit of its own, and Save image is its save_figure.

The bar wraps. Its controls come in groups, each a small QToolBar, laid
out left to right, and a group that does not fit goes to the next line: at
1200x800 the viewport is about 480 px wide, narrower than one line of the
structure's tools. A separator is drawn before a group that starts a
section, unless the group begins a line; a joined group continues the
section of the one before it, and the end group (Save image) sits at the
right of its line.
"""
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLayout, QStyle, QStyleOption, QToolBar, QToolButton, QWidget

from guiqula.ui import shortcuts

KEPT = ("Home", "Pan", "Zoom", "Save")     # matplotlib's tools the bar stands on
SECTION_GAP = 9          # pixels between two sections, the separator in the middle
JOINED_GAP = 2           # pixels between two groups of one section
ROW_GAP = 1              # pixels between two lines
PAN_TIP = ("drag the drawing with the left button and zoom with the right one, until Pan "
           "is clicked again or a tool is chosen")
ZOOM_TIP = ("zoom to the rectangle dragged with the left button, until Zoom is clicked "
            "again or a tool is chosen")
SAVE_TIP = "save the drawing as an image (PNG, PDF, SVG...), as it is shown"


class HiddenToolbar(NavigationToolbar2QT):
    """matplotlib's navigation toolbar with Home, Pan, Zoom and Save only,
    never shown; `changed` is called after its mode changes, whoever
    changed it (a button of the bar, a selection tool turning it off)."""

    toolitems = [item for item in NavigationToolbar2QT.toolitems if item[0] in KEPT]

    def __init__(self, canvas, parent, changed):
        super().__init__(canvas, parent, coordinates=False)
        self._changed = changed
        self.hide()

    def pan(self, *args):
        super().pan(*args)
        self._changed()

    def zoom(self, *args):
        super().zoom(*args)
        self._changed()


class FlowLayout(QLayout):
    """Items left to right, a new line when the next one does not fit; an
    item wider than the line is cut to it (a toolbar then shows its
    chevron). An item's widget may carry the properties "joined" (no
    separator before it) and "end" (at the right of its line). separators
    holds the rectangles between sections, which the owner paints."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.items = []
        self.separators = []

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    @staticmethod
    def shown(item):
        """Whether an item takes room: a widget shown, and a toolbar with
        something shown in it (a group whose tools are all hidden is not
        there, nor its separator)."""
        if item.isEmpty():
            return False
        widget = item.widget()
        return not isinstance(widget, QToolBar) or any(a.isVisible() for a in widget.actions())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def sizeHint(self):
        """One line holding everything."""
        shown = [item for item in self.items if self.shown(item)]
        if not shown:
            return QSize(0, 0)
        width = sum(item.sizeHint().width() for item in shown) + \
            sum(self._gap(item) for item in shown[1:])
        margins = self.contentsMargins()
        return QSize(width + margins.left() + margins.right(),
                     max(item.sizeHint().height() for item in shown)
                     + margins.top() + margins.bottom())

    def minimumSize(self):
        """As narrow as the widest item may be cut to, one line high."""
        shown = [item for item in self.items if self.shown(item)]
        margins = self.contentsMargins()
        if not shown:
            return QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return QSize(max(item.minimumSize().width() for item in shown)
                     + margins.left() + margins.right(),
                     max(item.sizeHint().height() for item in shown)
                     + margins.top() + margins.bottom())

    @staticmethod
    def _gap(item):
        widget = item.widget()
        return JOINED_GAP if widget is not None and widget.property("joined") else SECTION_GAP

    def lines(self, width):
        """The items shown, line by line, at this width: [[(item, width)]]."""
        margins = self.contentsMargins()
        room = max(width - margins.left() - margins.right(), 1)
        lines, line, used = [], [], 0
        for item in self.items:
            if not self.shown(item):
                continue
            wide = min(item.sizeHint().width(), room)
            gap = self._gap(item) if line else 0
            if line and used + gap + wide > room:
                lines.append(line)
                line, used, gap = [], 0, 0
            line.append((item, wide))
            used += gap + wide
        if line:
            lines.append(line)
        return lines

    def _arrange(self, rect, apply):
        margins = self.contentsMargins()
        left, top = rect.x() + margins.left(), rect.y() + margins.top()
        room = rect.width() - margins.left() - margins.right()
        y, separators = top, []
        if apply:                   # a group with nothing shown takes no room
            for item in self.items:
                if not item.isEmpty() and not self.shown(item):
                    item.setGeometry(QRect(left, top, 0, 0))
        for line in self.lines(rect.width()):
            height = max(item.sizeHint().height() for item, _ in line)
            x = left
            for i, (item, wide) in enumerate(line):
                gap = self._gap(item) if i else 0
                x += gap
                widget = item.widget()
                if widget is not None and widget.property("end"):
                    x = max(x, left + room - wide)
                if gap == SECTION_GAP:          # in the middle of the gap, just before it
                    separators.append(QRect(x - gap // 2 - 1, y, 2, height))
                if apply:
                    tall = min(item.sizeHint().height(), height)
                    item.setGeometry(QRect(x, y + (height - tall) // 2, wide, tall))
                x += wide
            y += height + ROW_GAP
        if apply:
            self.separators = separators
        if y == top:
            return margins.top() + margins.bottom()
        return y - ROW_GAP - top + margins.top() + margins.bottom()


class CanvasBar(QWidget):
    """The bar of one matplotlib drawing (see the module's docstring).

    canvas: the FigureCanvas; name: the bar's objectName; toolbar_name: the
    hidden matplotlib toolbar's; names: the format of the objectNames of the
    bar's own buttons, given key ("fit", "pan", "zoom", "saveImage") and Key
    (the same capitalized), "structure{Key}" or "{key}_c1"; fit: what Fit
    does (the toolbar's home when None). adopt_scene() takes a pyvista
    SceneView's Reset view, View and Save image into the bar, shown instead
    of the matplotlib ones while the scene is (show_scene).

    groups (name -> QToolBar) are made with group(); the first is
    "navigation" (Fit, Pan, Zoom) and the last "save" (Save image, at the
    right of its line, in the section before it)."""

    navigation_changed = Signal(bool)     # the hidden toolbar's pan or zoom went on or off

    def __init__(self, canvas, name, toolbar_name=None, names="{key}", fit=None,
                 fit_tip=None, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.flow = FlowLayout(self)
        self.names = names
        self._fit = fit
        self._navigating = False
        self.groups = {}
        self.actions_of = {}               # widget -> the QAction showing it in its group
        self.group_of = {}                 # widget -> its group
        self.scene = None
        self.in_scene = False
        self.toolbar = HiddenToolbar(canvas, self, self._mode_changed)
        if toolbar_name:
            self.toolbar.setObjectName(toolbar_name)
        self.group("navigation")
        self.group("save", joined=True, end=True)     # at the end of the last section
        fit_tip = fit_tip or (f"show the whole drawing again ({shortcuts.text('fit')}, "
                              f"{shortcuts.text('zoom_drawing')} on a flat drawing)")
        self.fit_button = self.button("navigation", "fit", "Fit", fit_tip, self.fit)
        self.pan_button = self.button("navigation", "pan", "Pan", PAN_TIP,
                                      lambda: self.toolbar.pan(), checkable=True)
        self.zoom_button = self.button("navigation", "zoom", "Zoom", ZOOM_TIP,
                                       lambda: self.toolbar.zoom(), checkable=True)
        self.save_button = self.button("save", "saveImage", "Save image", SAVE_TIP,
                                       lambda: self.toolbar.save_figure())

    # ---- building
    def control_name(self, key):
        return self.names.format(key=key, Key=key[:1].upper() + key[1:])

    def group(self, name, joined=False, end=False, after=None):
        """A group of controls (a QToolBar named <bar>_<name>), placed after
        the others and before the end groups, or right after the group
        `after`; joined: no separator before it."""
        if name in self.groups:
            return self.groups[name]
        bar = QToolBar(self)
        bar.setObjectName(f"{self.objectName()}_{name}")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setProperty("joined", bool(joined))
        bar.setProperty("end", bool(end))
        widgets = [item.widget() for item in self.flow.items]
        ends = [i for i, widget in enumerate(widgets) if widget.property("end")]
        self.flow.addWidget(bar)                   # appended, then moved into its place
        if after is not None:
            self.flow.items.insert(widgets.index(self.groups[after]) + 1, self.flow.items.pop())
        elif ends:
            self.flow.items.insert(ends[0], self.flow.items.pop())
        self.groups[name] = bar
        return bar

    def add(self, group, widget):
        """Put a widget in a group; returns the QAction that shows or hides it
        (Qt ignores setVisible on a widget of a toolbar)."""
        action = self.group(group).addWidget(widget)
        self.actions_of[widget] = action
        self.group_of[widget] = self.groups[group]
        return action

    def button(self, group, key, text, tooltip, slot=None, checkable=False):
        """A tool button named after key (names), in a group."""
        button = QToolButton()
        button.setText(text)
        button.setObjectName(self.control_name(key))
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        if slot is not None:
            button.clicked.connect(lambda checked=False: slot())
        self.add(group, button)
        return button

    def set_shown(self, widget, shown):
        self.actions_of[widget].setVisible(bool(shown))

    def shown(self, widget):
        """Whether a control is in the bar now (its group shown too)."""
        return self.actions_of[widget].isVisible() and not self.group_of[widget].isHidden()

    def adopt_scene(self, scene):
        """Take a SceneView's Reset view and View into a group in the place of
        the navigation one and its Save image into one in the place of the
        save one, shown instead of those by show_scene."""
        self.scene = scene
        self.group("scene", after="navigation")
        self.group("sceneSave", joined=True, end=True)
        self.add("scene", scene.reset)
        self.add("scene", scene.view_button)
        self.add("sceneSave", scene.save)
        self.show_scene(False)

    def show_scene(self, scene):
        """The scene's controls (scene: true) or matplotlib's, whole groups
        swapped; the scene takes the mouse, so pan or zoom stops."""
        self.in_scene = bool(scene) and self.scene is not None
        self.groups["navigation"].setVisible(not self.in_scene)
        self.groups["save"].setVisible(not self.in_scene)
        if self.scene is not None:
            self.groups["scene"].setVisible(self.in_scene)
            self.groups["sceneSave"].setVisible(self.in_scene)
        if self.in_scene:
            self.stop_navigating()

    # ---- navigation
    def fit(self):
        """The whole drawing again: the drawing's own fit, else the view the
        toolbar remembered first."""
        if self._fit is not None:
            self._fit()
        else:
            self.toolbar.home()

    def reset_history(self):
        """Forget the remembered views: the drawing was made again (its
        axes are new, and Fit goes back to how it is drawn now)."""
        self.toolbar.update()

    def mode(self):
        """matplotlib's mode: "", "pan/zoom" or "zoom rect"."""
        return str(getattr(self.toolbar, "mode", ""))

    def navigating(self):
        return bool(self.mode())

    def stop_navigating(self):
        """Turn off pan or zoom, which take the clicks until turned off."""
        mode = self.mode()
        if mode == "pan/zoom":
            self.toolbar.pan()
        elif mode == "zoom rect":
            self.toolbar.zoom()

    def _mode_changed(self):
        mode = self.mode()
        self.pan_button.setChecked(mode == "pan/zoom")
        self.zoom_button.setChecked(mode == "zoom rect")
        if bool(mode) != self._navigating:
            self._navigating = bool(mode)
            self.navigation_changed.emit(self._navigating)

    # ---- lines and separators
    def lines(self):
        """The objectNames of the groups shown, line by line (tests, layout)."""
        return [[item.widget().objectName() for item, _ in line]
                for line in self.flow.lines(self.width())]

    def controls(self):
        """The objectNames of the controls shown, in the order they are
        laid out (tests, drivers)."""
        out = []
        for item in self.flow.items:
            group = item.widget()
            if not self.flow.shown(item):
                continue
            for action in group.actions():
                widget = group.widgetForAction(action)
                if action.isVisible() and widget is not None and widget.objectName():
                    out.append(widget.objectName())
        return out

    def overflows(self):
        """The groups shown whose chevron is shown (they do not fit)."""
        out = []
        for name, bar in self.groups.items():
            chevron = bar.findChild(QToolButton, "qt_toolbar_ext_button")
            if bar.isVisible() and chevron is not None and chevron.isVisible():
                out.append(name)
        return out

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.flow.separators:
            return
        painter = QPainter(self)
        option = QStyleOption()
        option.initFrom(self)
        option.state |= QStyle.StateFlag.State_Horizontal
        for rect in self.flow.separators:
            option.rect = rect
            self.style().drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorToolBarSeparator,
                                       option, painter, self)
        painter.end()
