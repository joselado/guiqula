"""The icons of the controls (PLAN.md section 7, phase 8, P8): a vendored
subset of Tabler Icons, outline style but for the filled stop square of
cancel, under the MIT licence kept in resources/icons/LICENSE;
resources/icons/README.md lists our name of each icon, Tabler's name and
style and the version, so that a refresh is reproducible.

icon(name) gives a QIcon drawn in the colours of the active theme. Every
file draws in currentColor alone, which is replaced by the theme's text
colour (or by another colour of theme.COLORS named by `color`, ERROR for a
failed mark); the disabled state is the same picture in DISABLED, the
colour the palette gives a disabled button's text, so that a disabled
button's icon greys with its label, and the selected state (a selected row
of a list or a tree) is in the highlighted text colour. Each icon holds
renderings at the sizes of SIZES, 16 px (SIZE, what every control shows
at the normal interface text) and 24 px, with 20 px (LARGE, what they show
at large interface text) while that is the size, and those times the pixel
ratio of a screen that has one above 1, made by QSvgRenderer: about 0.3 ms
for the first icon() of a name, a dictionary lookup afterwards. Nothing is
read or drawn before the first icon() call, so importing this module costs
nothing at start. Without
QtSvg (a Qt built without it) icon() gives an empty icon and the controls
keep their text.

Icons are cached per theme. theme.apply calls theme_changed(), which
empties the cache and runs the callbacks registered with on_theme_change:
the window registers the method that sets its icons, which then sets them
again in the colours of the new theme. A change of View > Interface text
does the same (text_changed, which theme.apply_text calls), so that the
controls take the size of size() for the new text. A bound method is held weakly, so a
closed window is never kept alive by its callback, and a callback whose Qt
object was deleted is dropped. follow(widget, method) is the usual way in:
the method sets the widget's icons when the widget is first shown, so a
control out of sight at start (the structure canvas's bar behind the start
page, the k-space tab) costs nothing then, and again after every change of
theme from then on, through on_theme_change."""
import types
import weakref
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QObject, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPainter, QPalette, QPixmap

from guiqula.ui import theme

DIRECTORY = Path(__file__).resolve().parents[1] / "resources" / "icons"

NAMES = (
    # the plan's list (PLAN.md section 7, P8)
    "new", "open", "save", "undo", "redo", "run", "cancel", "follow", "add", "search",
    "fit", "pan", "zoom_in", "zoom_out", "pick", "box", "lasso", "select", "paint",
    "image", "export", "data", "overlay", "detach", "help", "lattice", "op", "term",
    "calculation", "region", "meanfield", "python", "done", "stale", "failed", "locked",
    "log", "panels",
    # what the plan's controls need besides: Remove selected, Run every stale result,
    # the k-space and Structure tabs, the settings, the theme, the 3D switch, Show,
    # Attach a slider, and the marks of ui/marks.py the list leaves out
    "remove", "run_stale", "kspace", "structure", "settings", "theme", "3d", "show",
    "slider", "invalid", "disabled", "running",
    # the View menu of the 3D scene (Blender's views, perspective and orthographic)
    "view",
)

SIZE = 16                 # pixels of the icon of a control, in a bar, a row or a tree
LARGE = 20                # the same at large interface text (the maintainer's answer)
SIZES = (SIZE, 24)        # pixels of the renderings each icon holds on a plain screen

_cache = {}           # (theme name, icon name, colour name) -> QIcon
_listeners = []       # callables giving a callback of on_theme_change, or None when gone


def icon(name, color="TEXT"):
    """The QIcon of `name` (one of NAMES) in the active theme, drawn in the
    theme's colour named `color` (a key of theme.COLORS: "TEXT", the
    default, or "ERROR", "MUTED", ...), greyed when disabled and in the
    highlighted text colour when selected. Raises KeyError for a name that
    is not in NAMES and ValueError for a colour the theme does not have."""
    if name not in NAMES:
        raise KeyError(f"unknown icon {name!r}; the icons are {', '.join(NAMES)}")
    colors = theme.COLORS[theme.name]
    if not str(colors.get(color, "")).startswith("#"):         # a colour, not a colour map
        known = ", ".join(key for key, value in colors.items() if str(value).startswith("#"))
        raise ValueError(f"unknown icon colour {color!r}; the theme's colours are {known}")
    key = (theme.name, name, color)
    if key not in _cache:
        _cache[key] = _draw(name, {
            QIcon.Mode.Normal: colors[color],
            QIcon.Mode.Disabled: colors["DISABLED"],
            QIcon.Mode.Selected: theme.PALETTES[theme.name][QPalette.ColorRole.HighlightedText],
        })
    return _cache[key]


def pixels():
    """The side of a control's icon at the active interface text: SIZE, or
    LARGE at large text."""
    return LARGE if theme.ui_text == "large" else SIZE


def size():
    """The QSize of a control's icon (setIconSize), at the active interface
    text."""
    return QSize(pixels(), pixels())


def follow(widget, method):
    """Set a widget's icons: method() (a bound method of the widget or of
    its owner, never a lambda) runs at the widget's first show, at once if
    it is shown already, and from then on after every change of theme
    (on_theme_change). A widget never shown costs nothing."""
    if widget.isVisible():
        method()
        on_theme_change(method)
    else:
        _FirstShow(widget, method)


class _FirstShow(QObject):
    """The event filter of follow(): at its widget's first Show event it
    runs the method, registers it with on_theme_change and goes."""

    def __init__(self, widget, method):
        super().__init__(widget)
        self._method = weakref.WeakMethod(method) if isinstance(method, types.MethodType) \
            else (lambda: method)
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show:
            watched.removeEventFilter(self)
            method = self._method()
            self.deleteLater()
            if method is not None:
                method()
                on_theme_change(method)
        return False


def on_theme_change(callback):
    """Call `callback()` after every theme.apply, once the cache is empty,
    so that it sets its icons again; returns a function that removes it. A
    bound method (the window's) is held weakly, anything else strongly, so
    a lambda that captures a window keeps it alive: pass the method."""
    if isinstance(callback, types.MethodType):
        reference = weakref.WeakMethod(callback)
    else:
        def reference():
            return callback
    # the callbacks of objects collected since (the forms of earlier selections) go now,
    # not only at the next change of theme, so that the list does not grow with them
    _listeners[:] = [r for r in _listeners if r() is not None]
    same = next((r for r in _listeners if isinstance(r, weakref.WeakMethod)
                 and r == reference), None)
    if same is not None:                  # registered already (the menus share one method)
        return lambda: _forget(same)
    _listeners.append(reference)
    return lambda: _forget(reference)


def _forget(reference):
    _listeners[:] = [r for r in _listeners if r is not reference]


def theme_changed():
    """What theme.apply calls: empty the cache and run the callbacks of
    on_theme_change, dropping those whose object is gone (a closed window,
    collected by Python or deleted by Qt)."""
    _cache.clear()
    for reference in list(_listeners):
        callback = reference()
        if callback is not None:
            try:
                callback()
                continue
            except RuntimeError as error:     # "Internal C++ object (...) already deleted."
                if "already deleted" not in str(error):
                    raise
        _forget(reference)


def text_changed():
    """What theme.apply_text calls when the interface text size changed:
    the same as a change of theme, so that every control that follows its
    icons sets them again, at size(), from renderings at that size."""
    theme_changed()


def clear():
    """Empty the cache (theme_changed does it on a change of theme)."""
    _cache.clear()


def _draw(name, colors):
    """A QIcon holding the renderings of an icon at every size of SIZES, in
    one colour per mode (colors, the Normal one first); an empty one without
    QtSvg. The SVG is rendered once per size, with currentColor replaced by
    the Normal colour, and the other modes are that rendering filled with
    their colour through its alpha: the same picture, since every file draws
    in currentColor alone, for less than a second rendering costs."""
    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        return QIcon()
    (normal, color), *others = colors.items()
    source = (DIRECTORY / f"{name}.svg").read_bytes().replace(b"currentColor", color.encode())
    renderer = QSvgRenderer(QByteArray(source))
    result = QIcon()
    for size in _sizes():
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        result.addPixmap(QPixmap.fromImage(image), normal, QIcon.State.Off)
        for mode, other in others:
            # the colour kept where the rendering is drawn: a plain fill, then its alpha
            # (DestinationIn; SourceIn's fillRect costs 3 ms the first time it is used)
            tinted = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
            tinted.fill(QColor(other))
            painter = QPainter(tinted)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            painter.drawImage(0, 0, image)
            painter.end()
            result.addPixmap(QPixmap.fromImage(tinted), mode, QIcon.State.Off)
    return result


def _sizes():
    """SIZES and the size of the active interface text, and those times the
    pixel ratio of each screen above 1 (a rendering per size: drawing the 2x
    ones on a plain screen would double the cost of every icon for
    nothing)."""
    app = QGuiApplication.instance()
    ratios = {screen.devicePixelRatio() for screen in app.screens()} if app is not None else ()
    sizes = {*SIZES, pixels()}
    return sorted({round(size * ratio) for size in sizes for ratio in {1.0, *ratios}})
