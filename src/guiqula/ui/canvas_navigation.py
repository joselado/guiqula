"""Moving over a flat drawing as Inkscape's canvas does (PLAN.md phase 8):
the structure canvas and the results drawn on the atoms, both matplotlib.

The wheel scrolls up and down, shift and the wheel sideways, ctrl and the
wheel zooms about the pointer; the middle button drags the drawing (a click
of it zooms in, with shift out); holding Space turns the left button into
that drag as well (the hand), which is how a touchpad pans; ctrl and the
arrow keys scroll, + and - zoom, 3 zooms to the selected sites, 4 (and
Home, which the canvas binds itself) shows the whole drawing, and the
backtick and its shifted key go to the previous and the next zoom. The
arithmetic is ui/navigation.py's; this module connects it to the events of
a matplotlib canvas and to the keys of the shortcut table (context "2D
canvas"). The toolbar's pan and zoom modes stay as they were.
"""
import numpy as np
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence, QShortcut

from guiqula.ui import navigation, shortcuts

CLICK_PIXELS = 4        # a middle press that moves less than this is a click


class CanvasNavigation(QObject):
    """The Inkscape controls of one matplotlib canvas.

    axes: a function giving the Axes drawn now (or None); active: whether
    these controls apply to what is drawn (not in 3D, not on a curve); fit:
    what "the whole drawing" does; selection: a function giving the (K, 2)
    positions of what "zoom to the selection" frames (or None); on_hand: told
    when the hand (Space held) goes on or off, so that the selection tools can
    step aside."""

    def __init__(self, canvas, axes, active=None, fit=None, selection=None, on_hand=None):
        super().__init__(canvas)
        self.canvas = canvas
        self._axes = axes
        self._active = active or (lambda: True)
        self._fit = fit
        self._selection = selection or (lambda: None)
        self._on_hand = on_hand
        self.history = navigation.ZoomHistory()
        self.hand = False               # Space is held: the left button drags the drawing
        self._drag = None
        canvas.installEventFilter(self)
        for name, slot in (("scroll_event", self._on_scroll),
                           ("button_press_event", self._on_press),
                           ("motion_notify_event", self._on_motion),
                           ("button_release_event", self._on_release)):
            canvas.mpl_connect(name, slot)

    # ---- the drawing
    def axes(self):
        """The Axes these controls move, or None when they do not apply."""
        ax = self._axes()
        if ax is None or not self._active():
            return None
        return ax

    def view(self):
        """((x0, x1), (y0, y1)) as drawn (the equal aspect applied)."""
        ax = self.axes()
        ax.apply_aspect()
        return tuple(ax.get_xlim()), tuple(ax.get_ylim())

    def set_view(self, view):
        ax = self.axes()
        ax.set_xlim(*view[0])
        ax.set_ylim(*view[1])
        self.canvas.draw_idle()

    def _pixels(self):
        return float(getattr(self.canvas, "device_pixel_ratio", 1.0))

    def _remember(self):
        self.history.push(self.view())

    # ---- what moves the view
    def scroll(self, dx, dy):
        """Move the view by (dx, dy) screen pixels (right, up)."""
        ax = self.axes()
        if ax is None:
            return False
        to_data = ax.transData.inverted()
        (x0, y0), (x1, y1) = to_data.transform((0.0, 0.0)), to_data.transform((dx, dy))
        (xl, xh), (yl, yh) = self.view()
        self.set_view((navigation.shift_limits((xl, xh), x1 - x0),
                       navigation.shift_limits((yl, yh), y1 - y0)))
        return True

    def zoom(self, factor, centre=None):
        """Scale the view by `factor` (below 1: in) about a point in data
        coordinates (the middle of the view when none is given)."""
        ax = self.axes()
        if ax is None:
            return False
        self._remember()
        (xl, xh), (yl, yh) = self.view()
        cx, cy = centre if centre is not None else ((xl + xh) / 2, (yl + yh) / 2)
        self.set_view((navigation.zoom_limits((xl, xh), cx, factor),
                       navigation.zoom_limits((yl, yh), cy, factor)))
        return True

    def zoom_selection(self):
        """Frame the selected sites, with the aspect of the view kept; the
        whole drawing when nothing is selected."""
        points = self._selection()
        ax = self.axes()
        if ax is None:
            return False
        if points is None or len(points) == 0:
            return self.zoom_drawing()
        points = np.asarray(points, dtype=float).reshape(-1, 2)
        self._remember()
        (xl, xh), (yl, yh) = self.view()
        ratio = (xh - xl) / (yh - yl) if yh != yl else 1.0
        (x0, x1), (y0, y1) = (navigation.limits_around(points[:, k]) for k in (0, 1))
        width = max(x1 - x0, (y1 - y0) * ratio)
        height = width / ratio if ratio else y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        self.set_view(((cx - width / 2, cx + width / 2), (cy - height / 2, cy + height / 2)))
        return True

    def zoom_drawing(self):
        """The whole drawing in sight."""
        if self.axes() is None or self._fit is None:
            return False
        self._remember()
        self._fit()
        return True

    def previous(self):
        if self.axes() is None:
            return False
        view = self.history.previous(self.view())
        if view is None:
            return False
        self.set_view(view)
        return True

    def next(self):
        if self.axes() is None:
            return False
        view = self.history.next(self.view())
        if view is None:
            return False
        self.set_view(view)
        return True

    def key_handlers(self):
        """{shortcut id: function} for the keys of context "2D canvas"."""
        step = navigation.SCROLL_STEP * self._pixels()
        zoom_in, zoom_out = 1 / navigation.ZOOM_FACTOR, navigation.ZOOM_FACTOR
        return {"zoom_in": lambda: self.zoom(zoom_in),
                "zoom_out": lambda: self.zoom(zoom_out),
                "zoom_selection": self.zoom_selection,
                "zoom_drawing": self.zoom_drawing,
                "zoom_previous": self.previous,
                "zoom_next": self.next,
                "scroll_left": lambda: self.scroll(-step, 0.0),
                "scroll_right": lambda: self.scroll(step, 0.0),
                "scroll_up": lambda: self.scroll(0.0, step),
                "scroll_down": lambda: self.scroll(0.0, -step)}

    # ---- the wheel
    @staticmethod
    def held(event):
        """The modifiers held, from the Qt event when there is one (the
        canvas may not have the focus) and from matplotlib's key otherwise:
        a set of "shift", "control", "alt"."""
        held = set()
        gui = getattr(event, "guiEvent", None)
        if gui is not None and hasattr(gui, "modifiers"):
            modifiers = gui.modifiers()
            for name, flag in (("shift", Qt.KeyboardModifier.ShiftModifier),
                               ("control", Qt.KeyboardModifier.ControlModifier),
                               ("alt", Qt.KeyboardModifier.AltModifier)):
                if modifiers & flag:
                    held.add(name)
        key = getattr(event, "key", None) or ""
        for name, spellings in (("shift", ("shift",)), ("control", ("control", "ctrl")),
                                ("alt", ("alt",))):
            if any(spelling in key for spelling in spellings):
                held.add(name)
        return held

    def _on_scroll(self, event):
        ax = self.axes()
        if ax is None or not event.step:
            return
        held = self.held(event)
        step = navigation.SCROLL_STEP * self._pixels() * event.step
        if "control" in held:
            centre = ax.transData.inverted().transform((event.x, event.y))
            self.zoom(navigation.ZOOM_FACTOR ** -event.step, tuple(centre))
        elif "shift" in held:
            self.scroll(-step, 0.0)              # a notch up scrolls to the left
        else:
            self.scroll(0.0, step)               # a notch up scrolls up

    # ---- the middle button, and the left one while Space is held
    def _on_press(self, event):
        ax = self.axes()
        if ax is None or event.x is None:
            return
        if event.button == 2 or (event.button == 1 and self.hand):
            (xl, xh), (yl, yh) = self.view()
            self._drag = {"button": event.button, "x": event.x, "y": event.y,
                          "to_data": ax.transData.inverted(), "view": ((xl, xh), (yl, yh)),
                          "moved": False, "held": self.held(event)}
            self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _on_motion(self, event):
        drag = self._drag
        if drag is None or self.axes() is None or event.x is None:
            return
        if np.hypot(event.x - drag["x"], event.y - drag["y"]) > CLICK_PIXELS:
            drag["moved"] = True
        if not drag["moved"]:
            return
        start = drag["to_data"].transform((drag["x"], drag["y"]))
        now = drag["to_data"].transform((event.x, event.y))
        (xl, xh), (yl, yh) = drag["view"]
        self.set_view((navigation.shift_limits((xl, xh), start[0] - now[0]),
                       navigation.shift_limits((yl, yh), start[1] - now[1])))

    def _on_release(self, event):
        drag, self._drag = self._drag, None
        if drag is None or drag["button"] != event.button:
            self._drag = drag
            return
        self._show_cursor()
        if drag["button"] == 2 and not drag["moved"] and event.xdata is not None \
                and self.axes() is not None:
            factor = navigation.ZOOM_FACTOR if "shift" in drag["held"] \
                else 1 / navigation.ZOOM_FACTOR
            self.zoom(factor, (event.xdata, event.ydata))

    # ---- the hand: Space held
    def set_hand(self, hand):
        if hand == self.hand:
            return
        self.hand = hand
        self._show_cursor()
        if self._on_hand is not None:
            self._on_hand(hand)

    def _show_cursor(self):
        if self._drag is not None:
            self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self.hand:
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.canvas.unsetCursor()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
                self.set_hand(kind == QEvent.Type.KeyPress and self.axes() is not None)
        elif kind == QEvent.Type.FocusOut:
            self.set_hand(False)
        elif kind == QEvent.Type.Wheel:
            # a wheel that only turns sideways (a touchpad, or shift+wheel on platforms
            # that swap them) is not a matplotlib scroll event
            delta = event.angleDelta()
            if delta.x() and not delta.y() and self.axes() is not None:
                self.scroll(-navigation.SCROLL_STEP * self._pixels() * delta.x() / 120.0, 0.0)
                return True
        return False


def bind_keys(widget, handlers):
    """A shortcut for each key of each id of `handlers` ({shortcut id:
    function}), active while `widget` has the focus. The shortcuts are the
    table's (ui/shortcuts.py), of the contexts its widgets handle
    themselves, so they are QShortcuts and not the window's actions."""
    made = []
    for shortcut_id, function in handlers.items():
        for key in shortcuts.keys(shortcut_id):
            shortcut = QShortcut(QKeySequence(key), widget)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(function)
            made.append(shortcut)
    return made
