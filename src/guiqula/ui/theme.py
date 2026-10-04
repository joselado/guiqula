"""The look (decision 13.6, and the themes of phase 5, design item 9): the
Fusion style with an explicit palette, light or dark, so that a desktop
theme never produces a half-dark window, and the colours the widgets, the
structure canvas and the plots share.

The colour names below (ERROR, BOND, SELECTED, TEXT, ...) are those of the
active theme: apply() rebinds them, and the canvas, the plots and the
outliner read them when they draw, so a redraw follows a change of theme.
A choice of "system" follows the desktop's colour scheme when Qt reports
one (Qt 6.5), else it is light. mpl_rc() gives the matplotlib settings of
the active theme (figure and axes colours, text, ticks) and of the active
plot text size, used around every drawing; exported figures are drawn
with the light one (rc("light")).

Plot text (the maintainer's request, 2026-09-29): the labels, the ticks,
the titles and the legends of every drawing (the result plots, the
structure canvas, the k-space tab, the exported figures, pyvista's title
and colour bar) take their size from one setting, text_size, "small",
"normal" or "large" (View > Plot text; io/settings.py keeps it), through
matplotlib's relative sizes: FONT_POINTS gives the base, the axis labels
are "large" (1.2 times it), the ticks and the title "medium", a legend, a
marker's label and a k-point's name "small".

Check boxes: Fusion draws the box of a check box with a border derived
from the window colour, faint in the light theme and invisible in the
dark one, so CheckStyle, a proxy over Fusion, draws the indicators of the
check boxes, the item views (the outliner) and the checkable menu entries
itself: a bordered box (CHECK_BORDER), filled with the highlight colour
when checked, with a white mark.

Interface text (PLAN.md phase 8, package P5): the widgets' font, "normal"
or "large" (View > Interface text; io/settings.py keeps it, ui_text), for a
projector. UI_POINTS gives the sizes on Qt's default font: normal is the
desktop's font, at least UI_POINTS["normal"] points, and large is that plus
the difference of the two, so that large is larger on any desktop; the
desktop's own size is remembered at the first apply(), so that going back
to normal is exact.

Centring (the same request): matplotlib puts the y label and its ticks
left of the axes and a colour bar right of it, so the axes box sits off
the middle of its panel; centre() balances the margins of a figure drawn
with constrained layout, and Centring keeps a canvas centred across
resizes.
"""
from contextlib import contextmanager

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPalette, QPen
from PySide6.QtWidgets import QProxyStyle, QStyle

CHOICES = ("system", "light", "dark")
TEXT_SIZES = ("small", "normal", "large")
FONT_POINTS = {"small": 9, "normal": 11, "large": 14}   # matplotlib's font.size, in points
UI_TEXT_SIZES = ("normal", "large")
# the widgets' font (Qt's default is 9 points): normal is at least 10, large 2 points more
UI_POINTS = {"normal": 10, "large": 12}
DESKTOP_POINTS = "guiqula_desktop_points"     # the application's property: the desktop's size
CENTRE_PIXELS = 1.5     # a shift of the axes smaller than this is not worth another drawing
MOVES = 5               # drawings a centring may add after one (the labels changed width)

COLORS = {
    "light": {
        "TEXT": "#1e1e1e", "MUTED": "#9e9e9e", "DOC": "#505050", "POINT": "#424242",
        "FIGURE": "#ffffff", "AXES": "#ffffff", "GRID": "#b0b0b0",
        "ERROR": "#b3261e", "ERROR_BACKGROUND": "#fde7e4",
        "NOTICE_BACKGROUND": "#fff4d6", "NOTICE_BORDER": "#d8b24a", "DISABLED": "#8a8a8a",
        "CHECK_BORDER": "#6e6e6e",
        "SUBLATTICE": {1.0: "#2f6db3", -1.0: "#d9822b", None: "#4a4a4a"},
        "ATOM_EDGE": "#ffffff", "ARROW": "#1e1e1e", "SELECTED": "#e0218a",
        "REGION": "#2e9e5b", "REMOVED": "#b3261e", "BOND": "#9a9a9a", "CELL": "#5b8fd0",
    },
    "dark": {
        "TEXT": "#e3e3e3", "MUTED": "#8c8c8c", "DOC": "#b4b4b4", "POINT": "#c8c8c8",
        "FIGURE": "#262626", "AXES": "#1f1f1f", "GRID": "#4a4a4a",
        "ERROR": "#ff8a80", "ERROR_BACKGROUND": "#4a2320",
        "NOTICE_BACKGROUND": "#3d3420", "NOTICE_BORDER": "#8f7431", "DISABLED": "#7a7a7a",
        "CHECK_BORDER": "#a0a0a0",
        "SUBLATTICE": {1.0: "#6aa6ee", -1.0: "#f0a24e", None: "#b8b8b8"},
        "ATOM_EDGE": "#1f1f1f", "ARROW": "#f0f0f0", "SELECTED": "#ff5cb4",
        "REGION": "#52c987", "REMOVED": "#ff6b61", "BOND": "#8a8a8a", "CELL": "#79a7e6",
    },
}

PALETTES = {
    "light": {
        QPalette.ColorRole.Window: "#efefef",
        QPalette.ColorRole.WindowText: "#1e1e1e",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#f5f5f5",
        QPalette.ColorRole.ToolTipBase: "#ffffe1",
        QPalette.ColorRole.ToolTipText: "#1e1e1e",
        QPalette.ColorRole.Text: "#1e1e1e",
        QPalette.ColorRole.Button: "#e8e8e8",
        QPalette.ColorRole.ButtonText: "#1e1e1e",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: "#3874c8",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Link: "#2f6db3",
        QPalette.ColorRole.PlaceholderText: "#8a8a8a",
    },
    "dark": {
        QPalette.ColorRole.Window: "#2b2b2b",
        QPalette.ColorRole.WindowText: "#e3e3e3",
        QPalette.ColorRole.Base: "#1f1f1f",
        QPalette.ColorRole.AlternateBase: "#282828",
        QPalette.ColorRole.ToolTipBase: "#3a3a3a",
        QPalette.ColorRole.ToolTipText: "#e3e3e3",
        QPalette.ColorRole.Text: "#e3e3e3",
        QPalette.ColorRole.Button: "#353535",
        QPalette.ColorRole.ButtonText: "#e3e3e3",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: "#3d6fb4",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Link: "#79a7e6",
        QPalette.ColorRole.PlaceholderText: "#8c8c8c",
        QPalette.ColorRole.Light: "#454545",
        QPalette.ColorRole.Midlight: "#3a3a3a",
        QPalette.ColorRole.Mid: "#2f2f2f",
        QPalette.ColorRole.Dark: "#1a1a1a",
        QPalette.ColorRole.Shadow: "#0d0d0d",
    },
}

name = "light"             # the active theme ("light" or "dark")
text_size = "normal"       # the active plot text size (TEXT_SIZES)
ui_text = "normal"         # the active interface text size (UI_TEXT_SIZES)
globals().update(COLORS[name])


def resolve(choice):
    """The theme a choice stands for: "system" follows the desktop."""
    if choice not in CHOICES:
        raise ValueError(f"unknown theme {choice!r}; choose one of {CHOICES}")
    if choice != "system":
        return choice
    app = QGuiApplication.instance()
    hints = app.styleHints() if app is not None else None
    scheme = hints.colorScheme() if hints is not None and hasattr(hints, "colorScheme") \
        else None
    return "dark" if scheme == Qt.ColorScheme.Dark else "light"


def set_text_size(size="normal"):
    """Make a plot text size the active one (what mpl_rc gives from now
    on; the caller draws again); returns it."""
    global text_size
    if size not in TEXT_SIZES:
        raise ValueError(f"unknown plot text size {size!r}; choose one of {TEXT_SIZES}")
    text_size = size
    return size


def set_ui_text(size="normal"):
    """Make an interface text size the active one (what apply and
    apply_text give the widgets from now on); returns it."""
    global ui_text
    if size not in UI_TEXT_SIZES:
        raise ValueError(f"unknown interface text size {size!r}; choose one of {UI_TEXT_SIZES}")
    ui_text = size
    return size


def ui_scale():
    """How much larger the active interface text is than the normal one: 1,
    or 1.2 at large (what the formula images and the fixed-width fonts follow)."""
    return UI_POINTS[ui_text] / UI_POINTS["normal"]


def fixed_font(points=None):
    """The desktop's fixed-width font at the points of the interface text
    (the console, a Python node's code), so that it follows View > Interface
    text as the other widgets do."""
    from PySide6.QtGui import QFontDatabase
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if points and points > 0:            # a desktop font given in pixels reads -1: left alone
        font.setPointSizeF(points)
    return font


def ui_points(app):
    """The point size of the widgets' font at the active interface text
    size, or None when the desktop's font is given in pixels (left alone)."""
    desktop = app.property(DESKTOP_POINTS)
    if desktop is None:
        desktop = app.font().pointSizeF()
        app.setProperty(DESKTOP_POINTS, desktop)
    if not desktop or desktop <= 0:
        return None
    return max(float(desktop), UI_POINTS["normal"]) + UI_POINTS[ui_text] - UI_POINTS["normal"]


def apply_text(app):
    """Give the widgets the font of the active interface text size (and the
    style sheet, whose titles follow it); returns its points."""
    points = ui_points(app)
    if points is not None and app.font().pointSizeF() != points:
        font = app.font()
        font.setPointSizeF(points)
        app.setFont(font)
    app.setStyleSheet(stylesheet(points))
    return points


def font_points(relative="medium", size=None):
    """Points of a relative matplotlib size ("small", "medium", "large",
    ...) at a plot text size (the active one by default): what a drawing
    outside matplotlib (pyvista) uses to match the plots."""
    from matplotlib.font_manager import font_scalings
    return FONT_POINTS[size or text_size] * font_scalings[relative]


def stylesheet(points=None):
    # a menu button (New system, Add op, Overlay...) gets room for its arrow, drawn at the
    # right and centred instead of Fusion's small one in the corner under the text; a
    # form's title is 2 points above the widgets' font (points)
    title = (points or UI_POINTS["normal"]) + 2
    return f"""
QFrame#errorBar {{ background: {ERROR_BACKGROUND}; border-bottom: 1px solid {ERROR}; }}
QFrame#recoveryBar, QFrame#trustBar, QFrame#costBar {{
    background: {NOTICE_BACKGROUND}; border-bottom: 1px solid {NOTICE_BORDER}; }}
QLabel#formError {{ color: {ERROR}; }}
QLabel#statusMessage[error="true"] {{ color: {ERROR}; }}
QLabel#formTitle {{ font-weight: bold; font-size: {title:g}pt; }}
QLabel#formDoc {{ color: {DOC}; }}
QToolButton[popupMode="2"] {{ padding-right: 14px; }}
QToolButton::menu-indicator {{ subcontrol-origin: padding; subcontrol-position: right center;
    right: 3px; width: 10px; }}
"""


def palette(theme_name):
    result = QPalette()
    for role, color in PALETTES[theme_name].items():
        result.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        result.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS[theme_name]["DISABLED"]))
    return result


class CheckStyle(QProxyStyle):
    """Fusion, with the check boxes drawn here: a box with a visible
    border in both themes (Fusion derives its border from the window
    colour, which leaves no box in the dark theme), filled with the
    highlight colour when checked, a bar for a partial state, greyed when
    disabled. Fusion routes the item views' check boxes and the checkable
    menu entries through the same primitive, so the outliner and the menus
    get the same box."""

    CHECKS = (QStyle.PrimitiveElement.PE_IndicatorCheckBox,
              QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck)

    def __init__(self):
        super().__init__("Fusion")

    def drawPrimitive(self, element, option, painter, widget=None):
        if element not in self.CHECKS:
            super().drawPrimitive(element, option, painter, widget)
            return
        state, colors = option.state, option.palette
        on = bool(state & QStyle.StateFlag.State_On)
        partial = bool(state & QStyle.StateFlag.State_NoChange)
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        hot = bool(state & (QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_HasFocus))
        highlight = colors.color(QPalette.ColorRole.Highlight)
        if not enabled:
            border = QColor(DISABLED)
            fill = QColor(DISABLED) if on or partial else colors.color(QPalette.ColorRole.Window)
            mark = colors.color(QPalette.ColorRole.Window)
        elif on or partial:
            border = fill = highlight
            mark = colors.color(QPalette.ColorRole.HighlightedText)
        else:
            border = highlight if hot else QColor(CHECK_BORDER)
            fill = colors.color(QPalette.ColorRole.Base)
            mark = None
        box = QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -0.5)     # crisp one-pixel border
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(fill)
        painter.drawRoundedRect(box, 2.0, 2.0)
        if mark is not None:
            painter.setPen(QPen(mark, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            x, y, w, h = box.x(), box.y(), box.width(), box.height()
            if on:
                painter.drawPolyline([QPointF(x + 0.22 * w, y + 0.53 * h),
                                      QPointF(x + 0.42 * w, y + 0.73 * h),
                                      QPointF(x + 0.78 * w, y + 0.30 * h)])
            else:
                painter.drawLine(QPointF(x + 0.25 * w, y + 0.5 * h),
                                 QPointF(x + 0.75 * w, y + 0.5 * h))
        painter.restore()


def apply(app, choice="light"):
    """Give the application the Fusion style (with the check boxes of
    CheckStyle), a theme's palette and the font of the interface text size
    (apply_text), and make the theme's colours the active ones, the icons'
    included (icons.theme_changed: the cache emptied, the window's callback
    setting its icons again); returns the theme applied."""
    global name
    name = resolve(choice)
    globals().update(COLORS[name])
    app.setStyle(CheckStyle())           # the application owns it and drops the previous one
    app.setPalette(palette(name))
    apply_text(app)
    app.setProperty("guiqula_theme", name)
    from guiqula.ui import icons      # here: icons reads this module's colours
    icons.theme_changed()             # the icons of the new theme, set again by the window
    return name


def mpl_rc(theme_name=None, size=None):
    """matplotlib settings for drawing in a theme (the active one by
    default) at a plot text size (the active one by default)."""
    c = COLORS[theme_name or name]
    return {"figure.facecolor": c["FIGURE"], "figure.edgecolor": c["FIGURE"],
            "savefig.facecolor": c["FIGURE"], "savefig.edgecolor": c["FIGURE"],
            "axes.facecolor": c["AXES"], "axes.edgecolor": c["TEXT"],
            "axes.labelcolor": c["TEXT"], "axes.titlecolor": c["TEXT"],
            "text.color": c["TEXT"], "xtick.color": c["TEXT"], "ytick.color": c["TEXT"],
            "xtick.labelcolor": c["TEXT"], "ytick.labelcolor": c["TEXT"],
            "grid.color": c["GRID"], "legend.facecolor": c["AXES"],
            "legend.edgecolor": c["MUTED"], "legend.labelcolor": c["TEXT"],
            "axes3d.xaxis.panecolor": c["AXES"], "axes3d.yaxis.panecolor": c["AXES"],
            "axes3d.zaxis.panecolor": c["AXES"],
            "font.size": FONT_POINTS[size or text_size], "axes.labelsize": "large",
            "axes.titlesize": "medium", "xtick.labelsize": "medium",
            "ytick.labelsize": "medium", "legend.fontsize": "small", "axes.labelpad": 3.0}


@contextmanager
def rc(theme_name=None):
    """Draw with a theme's matplotlib settings: what is created inside
    takes its colours and its text sizes (the figure's own background is
    set by the caller, set_figure)."""
    import matplotlib
    with matplotlib.rc_context(mpl_rc(theme_name)):
        yield


def set_figure(figure, theme_name=None):
    """A figure's background in a theme (a Figure keeps the colour it was
    created with)."""
    color = COLORS[theme_name or name]["FIGURE"]
    figure.set_facecolor(color)
    figure.set_edgecolor(color)


def finish(figure, theme_name=None):
    """Colour the ticks of every axes of a figure (matplotlib makes most
    ticks when it first draws, after the rc context has ended)."""
    color = COLORS[theme_name or name]["TEXT"]
    for ax in figure.axes:
        for axis in (ax.xaxis, ax.yaxis, getattr(ax, "zaxis", None)):
            if axis is not None:
                axis.set_tick_params(which="both", colors=color)


@contextmanager
def drawing(figure, theme_name=None):
    """Draw into a figure in a theme (the active one by default): its
    background, the colours of what is created inside and of the ticks, and
    the colour names of this module while inside (an exported figure is
    drawn in the light theme from a dark window)."""
    other = theme_name is not None and theme_name != name
    if other:
        globals().update(COLORS[theme_name])
    try:
        with rc(theme_name):
            set_figure(figure, theme_name)
            yield
            finish(figure, theme_name)
    finally:
        if other:
            globals().update(COLORS[name])


def centre(figure, ax, floor=None):
    """Balance the horizontal margins of a figure drawn with constrained
    layout, so that its axes box sits in the middle: the y label and the
    tick labels on the left, a colour bar on the right, push it aside
    otherwise. Measured on the last drawing (the position the layout gave
    the axes), so it is called after a draw; returns True when the layout
    was changed, meaning that the figure must be drawn again.

    floor: a dict kept over the drawings of one round (Centring), in which
    the padding given to each side never shrinks. The decorations depend on
    the room: an equal aspect widens the limits of a narrower axes, and its
    tick labels with them ("-10" for "-8"), while a colour bar narrows with
    it; balancing for the last measure alone could then swing between two
    layouts for ever, and only narrowing within a round settles it."""
    engine = figure.get_layout_engine()
    if engine is None or ax is None or ax.figure is not figure or "rect" not in engine.get():
        return False
    width = figure.bbox.width
    if width <= 0:
        return False
    rect = tuple(engine.get()["rect"])
    left, bottom, span, height = rect
    position = ax.get_position()
    # what the decorations take on each side of the axes box, in pixels
    on_left = (position.x0 - left) * width
    on_right = (left + span - position.x1) * width
    floor = {} if floor is None else floor
    # the padding of each side, at least what this round gave it before
    base = max(on_left + floor.get("left", 0.0), on_right + floor.get("right", 0.0))
    pad_left, pad_right = base - on_left, base - on_right
    room = max(1.0 - (pad_left + pad_right) / width, 0.2)
    target = (min(pad_left / width, 1.0 - room), bottom, room, height)
    if all(abs(a - b) * width < CENTRE_PIXELS for a, b in zip(target, rect)):
        return False
    floor["left"], floor["right"] = pad_left, pad_right
    engine.set(rect=target)
    return True


class Centring:
    """Keeps the axes of a canvas centred (centre): after every drawing,
    when the labels moved the axes (a resize changes the room they take),
    the canvas is drawn again; settle() draws at once, for a drawing whose
    transforms are read right after it (the readout, a test). axes_of()
    gives the axes to centre, or None."""

    def __init__(self, canvas, axes_of):
        self.canvas, self.axes_of = canvas, axes_of
        self._settling = False
        self._moves = 0
        self._floor = {}         # the paddings of this round (centre)
        canvas.mpl_connect("draw_event", self._on_draw)

    def _on_draw(self, event):
        if self._settling:
            return
        ax = self.axes_of()
        if ax is not None and self._moves < MOVES and centre(self.canvas.figure, ax,
                                                               self._floor):
            self._moves += 1
            self.canvas.draw_idle()
        else:
            self._moves = 0
            self._floor = {}

    def settle(self):
        """Draw now, and again when centring moved the axes."""
        self._settling = True
        floor = {}
        try:
            self.canvas.draw()
            for _ in range(MOVES):
                ax = self.axes_of()
                if ax is None or not centre(self.canvas.figure, ax, floor):
                    break
                self.canvas.draw()
        finally:
            self._settling = False
