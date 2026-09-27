"""The look (decision 13.6, and the themes of phase 5, design item 9): the
Fusion style with an explicit palette, light or dark, so that a desktop
theme never produces a half-dark window, and the colours the widgets, the
structure canvas and the plots share.

The colour names below (ERROR, BOND, SELECTED, TEXT, ...) are those of the
active theme: apply() rebinds them, and the canvas, the plots and the
outliner read them when they draw, so a redraw follows a change of theme.
A choice of "system" follows the desktop's colour scheme when Qt reports
one (Qt 6.5), else it is light. mpl_rc() gives the matplotlib settings of
the active theme (figure and axes colours, text, ticks), used around
every drawing; exported figures are drawn with the light one (rc("light")).
"""
from contextlib import contextmanager

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

CHOICES = ("system", "light", "dark")

COLORS = {
    "light": {
        "TEXT": "#1e1e1e", "MUTED": "#9e9e9e", "DOC": "#505050", "POINT": "#424242",
        "FIGURE": "#ffffff", "AXES": "#ffffff", "GRID": "#b0b0b0",
        "ERROR": "#b3261e", "ERROR_BACKGROUND": "#fde7e4",
        "NOTICE_BACKGROUND": "#fff4d6", "NOTICE_BORDER": "#d8b24a", "DISABLED": "#8a8a8a",
        "SUBLATTICE": {1.0: "#2f6db3", -1.0: "#d9822b", None: "#4a4a4a"},
        "ATOM_EDGE": "#ffffff", "ARROW": "#1e1e1e", "SELECTED": "#e0218a",
        "REGION": "#2e9e5b", "REMOVED": "#b3261e", "BOND": "#9a9a9a", "CELL": "#5b8fd0",
    },
    "dark": {
        "TEXT": "#e3e3e3", "MUTED": "#8c8c8c", "DOC": "#b4b4b4", "POINT": "#c8c8c8",
        "FIGURE": "#262626", "AXES": "#1f1f1f", "GRID": "#4a4a4a",
        "ERROR": "#ff8a80", "ERROR_BACKGROUND": "#4a2320",
        "NOTICE_BACKGROUND": "#3d3420", "NOTICE_BORDER": "#8f7431", "DISABLED": "#7a7a7a",
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


def stylesheet():
    return f"""
QFrame#errorBar {{ background: {ERROR_BACKGROUND}; border-bottom: 1px solid {ERROR}; }}
QFrame#recoveryBar, QFrame#trustBar, QFrame#costBar {{
    background: {NOTICE_BACKGROUND}; border-bottom: 1px solid {NOTICE_BORDER}; }}
QLabel#formError {{ color: {ERROR}; }}
QLabel#formTitle {{ font-weight: bold; font-size: 11pt; }}
QLabel#formDoc {{ color: {DOC}; }}
"""


def palette(theme_name):
    result = QPalette()
    for role, color in PALETTES[theme_name].items():
        result.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        result.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS[theme_name]["DISABLED"]))
    return result


def apply(app, choice="light"):
    """Give the application the Fusion style and a theme's palette, and
    make its colours the active ones; returns the theme applied."""
    global name
    name = resolve(choice)
    globals().update(COLORS[name])
    app.setStyle("Fusion")
    app.setPalette(palette(name))
    app.setStyleSheet(stylesheet())
    app.setProperty("guiqula_theme", name)
    return name


def mpl_rc(theme_name=None):
    """matplotlib settings for drawing in a theme (the active one by default)."""
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
            "axes3d.zaxis.panecolor": c["AXES"]}


@contextmanager
def rc(theme_name=None):
    """Draw with a theme's matplotlib settings: what is created inside
    takes its colours (the figure's own background is set by the caller,
    set_figure)."""
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
