"""Result plots (PLAN.md 3.4): one matplotlib implementation per plot kind,
drawn in the UI process from a Result's arrays.

Kinds (the ``kind`` of a Result's plot spec, which also names the arrays):

- ``lines``: y (one or more columns) against x (or against its index);
- ``colored_scatter``: the same, points coloured by c (bands with an
  operator);
- ``heatmap``: c on the points (x, y), given flat (one value per point, a
  grid is recognised and drawn as cells) or as a (len(x), len(y)) array;
  a NaN leaves its cell blank; ``symmetric`` centres a diverging colour
  map at zero (Berry curvature);
- ``structure_scalar``: one value per site drawn on the atoms (LDOS,
  density), from the geometry the Result carries (Result.structure); on a
  chain (every site on one line along x) a curve of the values against x,
  since the atoms of a long chain are too small to read colours from;
- ``structure_vector``: one vector per site, arrows for the in-plane part
  and dots for the z part (magnetization);
- ``scalar``: numbers in a table (Chern number, gap), ``rows`` naming
  [array, label] pairs.

Every calculation gets its own PlotView (a tab of the viewport, which can
be detached into a window of its own): the navigation toolbar (pan, zoom, save
the figure), Save data (the arrays and the metadata, io/results.py),
Detach, Overlay, and a readout of the data point under the mouse, which
also says what a pick there would take.

A result drawn flat on the atoms moves as Inkscape's canvas does (the
wheel scrolls, ctrl and the wheel zooms, the middle button or Space and
the left button drag it; ui/canvas_navigation.py); the other plots keep
matplotlib's toolbar and its pan and zoom modes.

Picks (PLAN.md phase 7): a right click on the plot, in any mode, or a
left click with the Pick toggle on, asks the window for the menu of what
the point stands for (core/picks.py) and what can be done with it
(registry/picks.py); on a result drawn flat on the atoms, the Box and
Lasso toggles pick every atom inside a drag, as the canvas's tools select
them. The view only reports where (pick_requested); the window's pick and
pick_to actions do the rest, so that drivers reach them too.

Markers (PLAN.md phase 7, part 3): a picked value stays drawn on the plot
it was picked on, bound to the parameter it set, which is what a slider
holds; the window hands the view its markers (set_markers: a line at a
number on the axis that carries it, a vertical line at a point of a k-path,
circles at a k-point of a map and its images, rings around sites), and a
drag of a line or a circle reports the position (marker_moved), which the
window turns into the slider's value: the parameter follows, one undo step
per drag, and the marker follows the parameter when a slider, a form or an
undo changes it.

3D: a result on the atoms is drawn in 3D as the canvas's 3D box says
(the window hands over its projection: auto, 3D when the geometry is not
flat; xy; 3d, so that a magnetization on a flat lattice can be turned
too), by matplotlib's mplot3d or, when View > 3D drawing says pyvista, by
pyvista (ui/pyvista_view.py), which takes the place of the figure and of
the navigation actions of the toolbar; a result drawn in 3D has no readout,
picks or markers. The exported figure (io/bundle.py) is matplotlib's,
drawn with the same projection.

Overlays (decision 13.11): the curves of other results drawn on the same
axes, each in its colour with a legend, or the difference of this result
and another one with the same x (two densities of states on one energy
grid), drawn as curves instead of the result (no colours, no colour bar);
for lines and coloured scatter plots. The window keeps which, and
lists what can be overlaid in the Overlay menu.
"""
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.widgets import LassoSelector, RectangleSelector
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QLabel, QMenu, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from guiqula.core import picks as pick_tools
from guiqula.core.results import PLOT_KINDS as KINDS  # noqa: F401 (the kinds drawn here)
from guiqula.ui import structure as structure_tools
from guiqula.ui import theme
from guiqula.ui.canvas_navigation import CanvasNavigation, bind_keys
from guiqula.ui.pyvista_view import SceneView

READOUT_PIXELS = 12      # the readout names a data point this close to the mouse
CLICK_PIXELS = 3         # a press released this close to where it started is a click
GRAB_PIXELS = 6          # a press this close to a marker drags it
MARKER_KINDS = ("hline", "vline", "dots", "rings")
CURVES = ("lines", "colored_scatter")       # plot kinds that overlay
OVERLAY_MODES = ("overlay", "difference")


def _lines(ax, result):
    """y against x, or against its index when the spec names no x."""
    arrays, plot = result.arrays, result.plot
    y = np.asarray(arrays[plot["y"]])
    x = np.asarray(arrays[plot["x"]]) if plot.get("x") else np.arange(len(y))
    y = y.reshape(len(x), -1)
    ax.plot(x, y, color="C0", linewidth=1.2)
    return np.repeat(x[:, None], y.shape[1], axis=1).ravel(), y.ravel(), None


def _limit(c):
    """The largest |value| of the finite ones (a colour scale centred at
    zero), 0 when there is none: one NaN made the scale NaN."""
    c = np.abs(np.asarray(c, dtype=float)).ravel()
    c = c[np.isfinite(c)]
    return float(c.max()) if len(c) else 0.0


def _colored_scatter(ax, result):
    arrays, plot = result.arrays, result.plot
    x = np.asarray(arrays[plot["x"]])
    y = np.asarray(arrays[plot["y"]]).reshape(len(x), -1)
    c = np.asarray(arrays[plot["c"]]).reshape(y.shape)
    xs = np.repeat(x[:, None], y.shape[1], axis=1)
    limit = _limit(c)
    if limit < 1e-8:          # all zero up to rounding: do not stretch the noise
        limit = 1.0
    points = ax.scatter(xs.ravel(), y.ravel(), c=c.ravel(), s=6, cmap="coolwarm",
                        vmin=-limit, vmax=limit)
    structure_tools.colorbar(ax, points, plot.get("clabel", plot["c"]))
    return xs.ravel(), y.ravel(), c.ravel()


def grid_of(x, y, c):
    """(xs, ys, C) with C[i, j] the value at (xs[i], ys[j]) when the flat
    points (x, y, c) fill a regular grid, else None. A value that is not a
    number (a sweep point that gave none) stays in its cell, drawn blank:
    only a cell without a point breaks the grid."""
    x, y, c = (np.asarray(a, dtype=float).ravel() for a in (x, y, c))
    xs, ix = np.unique(np.round(x, 10), return_inverse=True)
    ys, iy = np.unique(np.round(y, 10), return_inverse=True)
    if len(xs) * len(ys) != len(c) or len(xs) < 2 or len(ys) < 2:
        return None
    filled = np.zeros((len(xs), len(ys)), dtype=bool)
    filled[ix, iy] = True
    if not filled.all():                 # two points in one cell, so another is empty
        return None
    grid = np.empty((len(xs), len(ys)))
    grid[ix, iy] = c
    return xs, ys, grid


def _heatmap(ax, result):
    arrays, plot = result.arrays, result.plot
    x, y, c = (np.asarray(arrays[plot[k]], dtype=float) for k in ("x", "y", "c"))
    if c.ndim == 2:                          # c[i, j] at (x[i], y[j])
        xs, ys = np.meshgrid(x, y, indexing="ij")
        x, y, c = xs.ravel(), ys.ravel(), c.ravel()
    style = {"cmap": plot.get("cmap", "coolwarm" if plot.get("symmetric") else "inferno")}
    if plot.get("symmetric"):
        limit = _limit(c)
        style.update(vmin=-(limit or 1.0), vmax=limit or 1.0)
    grid = grid_of(x, y, c)
    if grid is not None:
        mesh = ax.pcolormesh(grid[0], grid[1], grid[2].T, shading="nearest", **style)
    else:
        mesh = ax.scatter(x, y, c=c, s=12, marker="s", linewidths=0, **style)
    structure_tools.colorbar(ax, mesh, plot.get("clabel", plot["c"]))
    if plot.get("equal"):
        ax.set_aspect("equal", adjustable="box")
    return x, y, c


def _on_structure(result):
    if result.structure is None:
        raise ValueError(f"{result.calculation}: this result carries no geometry to draw on")
    return result.structure


def _draw_on(ax):
    """draw_structure, or its 3D version on a 3D Axes."""
    return structure_tools.draw_structure_3d if getattr(ax, "name", "") == "3d" else \
        structure_tools.draw_structure


def _site_points(ax, build, values):
    """The readout's points: the sites in the xy drawing (none in 3D)."""
    if getattr(ax, "name", "") == "3d":
        return np.zeros(0), np.zeros(0), None
    r = np.asarray(build["positions"])
    return r[:, 0], r[:, 1], values


def along_a_line(result):
    """Whether a result on the atoms is drawn as a curve against x."""
    return result.plot["kind"] == "structure_scalar" and result.structure is not None and \
        structure_tools.on_a_line(result.structure)


def in_3d(result, projection="auto"):
    """Whether a result is drawn in 3D: one on the atoms, by the canvas's
    projection (auto: when its geometry is not flat)."""
    if result.plot["kind"] not in ON_STRUCTURE or result.structure is None:
        return False
    if projection == "auto":
        return not structure_tools.is_flat(result.structure)
    return projection == "3d"


def on_atoms(result):
    """What a result on the atoms draws on its geometry: the keywords of
    draw_structure (site_values, or arrows)."""
    plot = result.plot
    if plot["kind"] == "structure_scalar":
        return {"site_values": {
            "values": np.asarray(result.arrays[plot["values"]], dtype=float).ravel(),
            "label": plot.get("clabel", plot["values"]),
            "symmetric": plot.get("symmetric", False)}}
    return {"arrows": {"vectors": np.asarray(result.arrays[plot["vectors"]],
                                             dtype=float).reshape(-1, 3),
                       "label": plot.get("clabel", plot["vectors"])}}


def _structure_scalar(ax, result):
    build, plot = _on_structure(result), result.plot
    overlays = on_atoms(result)
    values = overlays["site_values"]["values"]
    if along_a_line(result) and getattr(ax, "name", "") != "3d":
        x = np.asarray(build["positions"])[:, 0]
        order = np.argsort(x)
        ax.plot(x[order], values[order], color=theme.MUTED, linewidth=1.0, zorder=1)
        ax.scatter(x, values, c=values, cmap=structure_tools.SEQUENTIAL_MAP, s=18, zorder=2)
        ax.set_ylabel(plot.get("clabel", plot["values"]))
        return x, values, values
    _draw_on(ax)(ax, build, **overlays)
    return _site_points(ax, build, values)


def _structure_vector(ax, result):
    build, overlays = _on_structure(result), on_atoms(result)
    _draw_on(ax)(ax, build, **overlays)
    return _site_points(ax, build, np.linalg.norm(overlays["arrows"]["vectors"], axis=1))


def scalar_rows(result):
    """[(label, text)] of a scalar result."""
    rows = []
    for name, label in result.plot["rows"]:
        value = np.asarray(result.arrays[name])
        if value.size == 1:
            text = _number(complex(value.ravel()[0]).real) if np.isrealobj(value) or \
                abs(complex(value.ravel()[0]).imag) < 1e-12 else str(complex(value.ravel()[0]))
        else:
            text = ", ".join(_number(v) for v in np.real(value).ravel())
        rows.append((label, text))
    return rows


def _scalar(ax, result):
    ax.set_axis_off()
    rows = scalar_rows(result)
    for i, (label, text) in enumerate(rows):
        yy = 0.8 - i * 0.18
        ax.text(0.05, yy, label, fontsize="large", transform=ax.transAxes, va="center")
        ax.text(0.95, yy, text, fontsize="xx-large", transform=ax.transAxes, va="center",
                ha="right", family="monospace", weight="bold")
    return np.zeros(0), np.zeros(0), None


DRAW = {"lines": _lines, "colored_scatter": _colored_scatter, "heatmap": _heatmap,
        "structure_scalar": _structure_scalar, "structure_vector": _structure_vector,
        "scalar": _scalar}
ON_STRUCTURE = ("structure_scalar", "structure_vector")


def curves(result):
    """(x, y) of a lines or colored_scatter result, y with one column per
    curve (or against its index when the spec names no x)."""
    plot = result.plot
    y = np.asarray(result.arrays[plot["y"]])
    x = np.asarray(result.arrays[plot["x"]]) if plot.get("x") else np.arange(len(y))
    return x, y.reshape(len(x), -1)


def can_overlay(result, other, mode="overlay"):
    """Whether other can be drawn over result (in this mode)."""
    if result is None or other is None or result.plot["kind"] not in CURVES \
            or other.plot["kind"] not in CURVES:
        return False
    try:
        (x1, y1), (x2, y2) = curves(result), curves(other)
    except Exception:                     # arrays that do not make curves
        return False
    if mode == "overlay":
        return True
    return x1.shape == x2.shape and y1.shape == y2.shape and np.allclose(x1, x2)


def _draw_difference(ax, result, label, other):
    """The curves of result minus those of other (the same x), drawn
    instead of result's own drawing; returns the points of the readout."""
    (x, y), (_, y_other) = curves(result), curves(other)
    lines = ax.plot(x, y - y_other, color="C3", linewidth=1.2)
    lines[0].set_label(f"{result.calculation} − {label}")
    ax.legend()
    return np.repeat(x[:, None], y.shape[1], axis=1).ravel(), (y - y_other).ravel(), None


def _draw_overlays(ax, result, overlays):
    """overlays: [(label, Result, mode)] drawn over result's curves, each
    in its colour, with a legend."""
    handles = [ax.lines[0]] if ax.lines else []
    if handles:
        handles[0].set_label(result.calculation)
    for i, (label, other, _) in enumerate(overlays):
        x, y = curves(other)
        lines = ax.plot(x, y, color=f"C{i + 1}", linewidth=1.0, alpha=0.85)
        lines[0].set_label(label)
        handles.append(lines[0])
    if handles:
        ax.legend(handles=handles)


def draw(figure, result, title="", overlays=(), theme_name=None, projection="auto"):
    """Draw a Result, with the overlays [(label, Result, mode)], in a theme
    (the active one by default) and, on the atoms, in 3D as the projection
    says (in_3d); returns the Axes and the points (x, y, c or None) the
    readout looks up."""
    with theme.drawing(figure, theme_name):
        return _draw(figure, result, title, overlays, projection)


def _draw(figure, result, title, overlays, projection="auto"):
    figure.clear()
    plot = result.plot
    three_d = in_3d(result, projection)
    ax = figure.add_subplot(111, projection="3d" if three_d else None)
    overlays = [o for o in overlays if can_overlay(result, o[1], o[2])]
    difference = [(label, other) for label, other, mode in overlays if mode == "difference"]
    if difference:          # instead of the result's own drawing, and its colour bar
        points = _draw_difference(ax, result, *difference[0])
    else:
        points = DRAW[plot["kind"]](ax, result)
        if overlays:
            _draw_overlays(ax, result, overlays)
    if along_a_line(result) and not three_d:
        ax.set_xlabel("x")
    elif plot["kind"] in ON_STRUCTURE and not three_d:
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    elif plot["kind"] != "scalar":
        ax.set_xlabel(plot.get("xlabel", plot.get("x", "")))
        ax.set_ylabel(plot.get("ylabel", plot.get("y", "")))
    ax.set_title(title)
    if plot.get("x") == "k" and plot["kind"] in ("lines", "colored_scatter"):
        ax.set_xlim(np.min(result.arrays["k"]), np.max(result.arrays["k"]))
    if plot.get("xticks"):                  # the vertices of a k-path
        positions = [float(i) for i, _ in plot["xticks"]]
        ax.set_xticks(positions, [name for _, name in plot["xticks"]])
        for position in positions:
            ax.axvline(position, color=theme.MUTED, linewidth=0.6, zorder=0)
    return ax, points


def _number(value):
    return f"{value:.6g}"


def _same_sites(a, b):
    """Whether two results on the atoms carry the same positions (a result
    of the same geometry computed again keeps its camera)."""
    ra = np.asarray((a.structure or {}).get("positions", np.zeros((0, 3))))
    rb = np.asarray((b.structure or {}).get("positions", np.zeros((0, 3))))
    return ra.shape == rb.shape and bool(np.allclose(ra, rb, rtol=0.0,
                                                     atol=structure_tools.SAME_SITE))


class ResultWindow(QWidget):
    """A detached PlotView, in a top-level window of its own. It is a plain
    window and not a floating QDockWidget on purpose: a floating dock draws
    its own title bar and moves itself, which a Wayland compositor ignores
    (a client cannot place its windows there), so the plot could not be
    moved; a plain window gets the decoration of the desktop (on Wayland,
    Qt's client-side one), which asks the compositor for the move."""

    def __init__(self, calc_id, view, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName(f"resultWindow_{calc_id}")
        self.view = view
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

    def release(self):
        """Give the view back, to be placed somewhere else."""
        self.layout().removeWidget(self.view)
        self.view.setParent(None)


class PlotView(QWidget):
    """A matplotlib canvas with its navigation toolbar, for the results of
    one calculation (calc_id)."""

    save_requested = Signal(str)          # calculation id
    export_requested = Signal(str)        # figure, data and script (io/bundle.py)
    detach_requested = Signal(str)
    overlay_menu_requested = Signal(str)      # the window fills the Overlay menu
    # calculation id, where ({"x", "y"} in data coordinates, {"box"} or {"polygon"}), the
    # global position of the menu: the window shows what can be done there
    pick_requested = Signal(str, object, object)
    marker_moved = Signal(int, float, float, bool)     # slider index, x, y, still dragging

    def __init__(self, calc_id="", parent=None):
        super().__init__(parent)
        self.calc_id = calc_id
        suffix = f"_{calc_id}" if calc_id else ""
        self.setObjectName(f"plot{suffix}" if calc_id else "plotView")
        # constrained layout is redone at every draw, so the labels fit the
        # size the view has, not the size the figure was created with
        self.figure = Figure(figsize=(6, 4), dpi=100, layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setObjectName(f"plotCanvas{suffix}")
        self.centring = theme.Centring(self.canvas, lambda: self.ax)   # the axes in the middle
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.save_data = QToolButton()
        self.save_data.setText("Save data")
        self.save_data.setObjectName(f"saveData{suffix}")
        self.save_data.setToolTip("save the arrays (.npz) and what produced them (.json)")
        self.save_data.clicked.connect(lambda: self.save_requested.emit(self.calc_id))
        self.detach = QToolButton()
        self.detach.setText("Detach")
        self.detach.setObjectName(f"detach{suffix}")
        self.detach.setToolTip("show this result in a window of its own, to compare it with "
                               "another; Attach puts it back")
        self.detach.clicked.connect(lambda: self.detach_requested.emit(self.calc_id))
        self.export = QToolButton()
        self.export.setText("Export")
        self.export.setObjectName(f"export{suffix}")
        self.export.setToolTip("the figure (PNG and PDF, on white), the data (.npz, .csv) and "
                               "the pyqula script reproducing them, in one folder "
                               "(Ctrl+Shift+E)")
        self.export.clicked.connect(lambda: self.export_requested.emit(self.calc_id))
        self.toolbar.addSeparator()
        # a widget on a toolbar is shown and hidden by its action (Qt ignores its setVisible)
        self._shown_by = {}
        for widget in (self.export, self.save_data, self.detach):
            self._shown_by[widget] = self.toolbar.addWidget(widget)
        self.overlay = QToolButton()
        self.overlay.setText("Overlay")
        self.overlay.setObjectName(f"overlay{suffix}")
        self.overlay.setToolTip("draw another result on the same axes, or the difference of "
                                "the two")
        self.overlay.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.overlay.setMenu(QMenu(self.overlay))
        self.overlay.menu().aboutToShow.connect(
            lambda: self.overlay_menu_requested.emit(self.calc_id))
        self._shown_by[self.overlay] = self.toolbar.addWidget(self.overlay)
        self.toolbar.addSeparator()
        self.pick_tools = {}
        for tool, text, tip in (
                ("pick", "Pick", "a click picks what the point stands for (an energy, a "
                                 "k-point, a parameter, a site) and offers what to do with it; "
                                 "a right click does the same in any mode"),
                ("box", "Box", "pick the atoms inside a box drawn on the result"),
                ("lasso", "Lasso", "pick the atoms inside a lasso drawn on the result")):
            button = QToolButton()
            button.setText(text)
            button.setCheckable(True)
            button.setObjectName(f"{tool}Tool{suffix}")
            button.setToolTip(tip)
            button.toggled.connect(lambda on, t=tool: self._tool_toggled(t, on))
            self._shown_by[button] = self.toolbar.addWidget(button)
            self.pick_tools[tool] = button
        self.readout = QLabel("")
        self.readout.setObjectName(f"readout{suffix}")
        self.caption = QLabel("No result yet: choose a calculation and press Run (F5).")
        self.caption.setObjectName(f"plotCaption{suffix}")
        self.caption.setWordWrap(True)
        self.caption.setMinimumHeight(2 * self.caption.fontMetrics().lineSpacing())
        self.scene = SceneView(f"plotScene{suffix}")        # pyvista loads at its first drawing
        self.stack = QStackedWidget()
        self.stack.addWidget(self.canvas)
        self.stack.addWidget(self.scene)
        # the toolbar's own actions (home, pan, zoom, save the figure), which the scene replaces
        navigation = {text for text, *_ in NavigationToolbar2QT.toolitems if text}
        self._navigation = [a for a in self.toolbar.actions() if a.text() in navigation]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.readout)
        layout.addWidget(self.caption)
        self.projection = "auto"           # the canvas's (the window sets both)
        self.renderer_3d = "matplotlib"
        self.in_scene = False              # the result is drawn by pyvista (self.scene)
        self.result = None
        self.ax = None
        self.points = None
        self.stale = False
        self.overlays = []
        self._press = None                 # (x, y, button) of a press on the canvas, in pixels
        self._selector = None
        self.markers = []                  # [{index, kind, value, label}] (set_markers)
        self._marker_artists = []          # [(marker, [artists])]
        self._dragging = None              # the marker being dragged
        self._update_buttons()
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.navigation = CanvasNavigation(
            self.canvas, lambda: self.ax, active=self._on_the_atoms, fit=self._fit_2d,
            on_hand=self._hand_changed)
        bind_keys(self.canvas, self.navigation.key_handlers())
        bind_keys(self.scene.canvas, self.scene.key_handlers())

    def _on_the_atoms(self):
        """Whether Inkscape's controls apply: a result drawn flat on the
        atoms, not a curve against x."""
        return self.result is not None and self.result.plot["kind"] in ON_STRUCTURE \
            and getattr(self.ax, "name", "") != "3d" and not along_a_line(self.result)

    def _fit_2d(self):
        self.ax.set_autoscale_on(True)
        self.ax.autoscale_view()
        self.canvas.draw_idle()

    def _hand_changed(self, hand):
        """Space held: the left button drags the drawing, so the box and
        lasso stand aside."""
        if self._selector is not None:
            self._selector.set_active(not hand)

    def _update_buttons(self):
        self.save_data.setEnabled(self.result is not None and bool(self.calc_id))
        self.export.setEnabled(self.result is not None and bool(self.calc_id))
        self._shown_by[self.detach].setVisible(bool(self.calc_id))
        self._shown_by[self.overlay].setVisible(bool(self.calc_id))
        self.overlay.setEnabled(self.result is not None and self.ax is not None
                                and self.result.plot["kind"] in CURVES)
        pickable = bool(self.calc_id) and self.result is not None and self.ax is not None \
            and bool(pick_tools.spec_of(self.result))
        on_atoms = pickable and self.result.plot["kind"] in ON_STRUCTURE \
            and getattr(self.ax, "name", "") != "3d"
        for tool, button in self.pick_tools.items():
            shown = on_atoms if tool in ("box", "lasso") else pickable
            self._shown_by[button].setVisible(shown)
            if button.isChecked() and not shown:
                button.setChecked(False)

    def show_result(self, result, title="", caption="", stale=False, overlays=()):
        """Draw a result; one that cannot be drawn (arrays a plugin or a
        Python calculation shaped otherwise than its plot kind) says why in
        the caption, and its data can still be saved."""
        was_scene = self.in_scene and self.result is not None and \
            _same_sites(self.result, result)
        self.navigation.history.clear()            # drawn again: the earlier zooms are gone
        self.result = result
        self.stale = stale
        self.overlays = list(overlays)
        if self.renderer_3d == "pyvista" and in_3d(result, self.projection):
            try:
                self.scene.show_scene(_on_structure(result), keep=was_scene, fit=False,
                                      title=title, **on_atoms(result))
            except Exception as error:
                self.scene.forget()
                caption = " · ".join(filter(None, [
                    caption, f"drawn with matplotlib: pyvista could not draw ({error})"]))
            else:
                self._show_canvas(False)
                self.figure.clear()
                self.ax = self.points = None
                self._marker_artists = []
                self.caption.setText(caption)
                self.readout.setText("")
                self._update_buttons()
                self._install_selector()
                return
        self._show_canvas(True)
        try:
            self.ax, self.points = draw(self.figure, result, title, overlays,
                                        projection=self.projection)
            self._marker_artists = []
            self._draw_markers()
            self.centring.settle()   # now: the limits and the layout are final for the readout
        except Exception as error:
            self.figure.clear()
            theme.set_figure(self.figure)
            self.ax = self.points = None
            self.canvas.draw_idle()
            caption = " · ".join(filter(None, [
                f"this result cannot be drawn: {type(error).__name__}: {error}", caption]))
        self.caption.setText(caption)
        self.readout.setText("")
        self._update_buttons()
        self._install_selector()

    def _show_canvas(self, canvas):
        """The matplotlib figure and the toolbar's navigation, or pyvista's
        scene."""
        self.in_scene = not canvas
        self.stack.setCurrentWidget(self.canvas if canvas else self.scene)
        if not canvas:
            mode = str(getattr(self.toolbar, "mode", ""))     # the scene takes the mouse now
            if mode == "pan/zoom":
                self.toolbar.pan()
            elif mode == "zoom rect":
                self.toolbar.zoom()
        for action in self._navigation:
            action.setVisible(canvas)

    def clear(self, caption=""):
        self.navigation.history.clear()
        self.scene.forget()
        self._show_canvas(True)
        self._marker_artists = []
        self._dragging = None
        self.result = self.ax = self.points = None
        self.stale = False
        self.figure.clear()
        theme.set_figure(self.figure)
        self.caption.setText(caption)
        self.readout.setText("")
        self.canvas.draw_idle()
        self._update_buttons()
        self._install_selector()

    def set_detached(self, detached):
        self.detach.setText("Attach" if detached else "Detach")

    # ---- the readout
    def point_near(self, x_pixels, y_pixels, radius=READOUT_PIXELS):
        """Index of the plotted point nearest to a position in display
        pixels (matplotlib's, origin bottom left), or None."""
        if self.points is None or self.ax is None or not len(self.points[0]):
            return None
        xy = self.ax.transData.transform(np.column_stack(self.points[:2]))
        d = np.hypot(xy[:, 0] - x_pixels, xy[:, 1] - y_pixels)
        i = int(np.argmin(d))
        return i if d[i] <= radius else None

    def readout_text(self, i):
        plot = self.result.plot
        x, y, c = self.points
        if plot["kind"] in ON_STRUCTURE:
            what = plot.get("clabel", plot.get("values", plot.get("vectors")))
            if plot["kind"] == "structure_vector":
                what = f"|{what}|"
            if along_a_line(self.result):
                return f"site {i} at x = {_number(x[i])} · {what} {_number(c[i])}"
            return f"site {i} at ({_number(x[i])}, {_number(y[i])}) · {what} {_number(c[i])}"
        text = (f"{plot.get('xlabel', plot.get('x'))} {_number(x[i])} · "
                f"{plot.get('ylabel', plot.get('y'))} {_number(y[i])}")
        if c is not None:
            text += f" · {plot.get('clabel', plot.get('c'))} {_number(c[i])}"
        return text

    def snap(self, x, y):
        """(index, x, y) of the drawn point nearest to a position in data
        coordinates, within the readout's radius (what the readout names
        there), or (None, x, y) when there is none."""
        if self.ax is None or self.points is None or not len(self.points[0]):
            return None, x, y
        px, py = self.ax.transData.transform((x, y))
        i = self.point_near(px, py)
        if i is None:
            return None, x, y
        return i, float(self.points[0][i]), float(self.points[1][i])

    def picks_y(self):
        """Whether the y of a point is what the plot's spec says it carries:
        not when the difference of two results is drawn instead."""
        return not any(mode == "difference" for _, _, mode in self.overlays)

    def _on_motion(self, event):
        if self._dragging is not None and event.inaxes is self.ax and event.xdata is not None:
            self._drag_to(event, True)
            return
        if self.result is None or event.inaxes is not self.ax or event.xdata is None:
            if self.readout.text():
                self.readout.setText("")
            return
        i = self.point_near(event.x, event.y)
        text = self.readout_text(i) if i is not None else \
            f"({_number(event.xdata)}, {_number(event.ydata)})"
        if self.calc_id and pick_tools.spec_of(self.result):
            x, y = (self.points[0][i], self.points[1][i]) if i is not None else \
                (event.xdata, event.ydata)
            try:
                label = pick_tools.pick(self.result, x, y if self.picks_y() else None,
                                        index=i)["label"]
            except Exception:               # arrays a plugin shaped otherwise
                label = ""
            if label:
                text += f" · a pick takes {label}"
        self.readout.setText(text)

    # ---- markers (part 3)
    def set_markers(self, markers):
        """Draw these markers instead of the ones drawn: [{"index": the
        slider's, "kind": hline | vline | dots | rings, "value": a number or
        [[x, y], ...], "label"}]; the plot itself is not drawn again, so its
        zoom stays."""
        markers = [dict(m) for m in markers]
        if markers == self.markers and (self._marker_artists or not markers):
            return
        self.markers = markers
        if self.ax is None:
            return
        with theme.drawing(self.figure):
            for _, artists in self._marker_artists:
                for artist in artists:
                    artist.remove()
            self._marker_artists = []
            self._draw_markers()
        self.canvas.draw_idle()

    def _draw_markers(self):
        if self.ax is None or getattr(self.ax, "name", "") == "3d":
            return
        style = {"color": theme.SELECTED, "linewidth": 1.4, "linestyle": "--", "zorder": 8}
        # in points: a relative size would be resolved against the rc of the moment, and the
        # markers are drawn outside theme.drawing after a result
        small = theme.font_points("small")
        for marker in self.markers:
            kind, value, artists = marker["kind"], marker["value"], []
            if kind == "hline":
                artists.append(self.ax.axhline(value, **style))
                artists.append(self.ax.annotate(
                    marker.get("label", ""), (1.0, value), xycoords=("axes fraction", "data"),
                    xytext=(-4, 3), textcoords="offset points", ha="right", fontsize=small,
                    color=theme.SELECTED, zorder=8))
            elif kind == "vline":
                artists.append(self.ax.axvline(value, **style))
                artists.append(self.ax.annotate(
                    marker.get("label", ""), (value, 1.0), xycoords=("data", "axes fraction"),
                    xytext=(3, -10), textcoords="offset points", fontsize=small,
                    color=theme.SELECTED, zorder=8))
            elif kind == "dots" and len(value):
                xy = np.asarray(value, dtype=float).reshape(-1, 2)
                artists += self.ax.plot(xy[:, 0], xy[:, 1], "o", markersize=9,
                                        markerfacecolor="none", markeredgewidth=2,
                                        color=theme.SELECTED, zorder=8, linestyle="none")
            elif kind == "rings" and len(value):
                xy = np.asarray(value, dtype=float).reshape(-1, 2)
                artists.append(self.ax.scatter(xy[:, 0], xy[:, 1], s=260, facecolors="none",
                                               edgecolors=theme.SELECTED, linewidths=2,
                                               zorder=8))
            self._marker_artists.append((marker, artists))

    def marker_near(self, x_pixels, y_pixels, radius=GRAB_PIXELS):
        """The marker a press at this position (display pixels) grabs, or
        None: a line within radius of it, a circle within radius (rings are
        not dragged)."""
        if self.ax is None:
            return None
        best, best_d = None, radius
        for marker in self.markers:
            kind, value = marker["kind"], marker["value"]
            if kind == "hline":
                d = abs(self.ax.transData.transform((0, value))[1] - y_pixels)
            elif kind == "vline":
                d = abs(self.ax.transData.transform((value, 0))[0] - x_pixels)
            elif kind == "dots" and len(value):
                xy = self.ax.transData.transform(np.asarray(value, dtype=float).reshape(-1, 2))
                d = float(np.min(np.hypot(xy[:, 0] - x_pixels, xy[:, 1] - y_pixels)))
            else:
                continue
            if d <= best_d:
                best, best_d = marker, d
        return best

    def _drag_to(self, event, dragging):
        marker = self._dragging
        for drawn, artists in self._marker_artists:        # the line follows at once
            if drawn is marker and artists:
                if marker["kind"] == "hline":
                    artists[0].set_ydata([event.ydata, event.ydata])
                elif marker["kind"] == "vline":
                    artists[0].set_xdata([event.xdata, event.xdata])
                elif marker["kind"] == "dots":           # its images come back after
                    artists[0].set_data([event.xdata], [event.ydata])
        self.canvas.draw_idle()
        self.marker_moved.emit(int(marker["index"]), float(event.xdata), float(event.ydata),
                               dragging)

    # ---- picks: the gestures (the window does the rest)
    def _tool_toggled(self, tool, on):
        if on:
            for other, button in self.pick_tools.items():
                if other != tool and button.isChecked():
                    button.setChecked(False)
            mode = str(getattr(self.toolbar, "mode", ""))   # pan and zoom would take the clicks
            if mode == "pan/zoom":
                self.toolbar.pan()
            elif mode == "zoom rect":
                self.toolbar.zoom()
        self._install_selector()

    def tool(self):
        """The pick toggle that is on, or None."""
        return next((t for t, b in self.pick_tools.items() if b.isChecked()), None)

    def _install_selector(self):
        if self._selector is not None:
            self._selector.set_active(False)
            self._selector = None
        tool = self.tool()
        if self.ax is None or tool not in ("box", "lasso") or getattr(self.ax, "name", "") == "3d":
            return
        if tool == "box":
            self._selector = RectangleSelector(
                self.ax, self._on_box, useblit=False, button=[1], interactive=False,
                props={"edgecolor": theme.SELECTED, "fill": False, "linewidth": 1.5})
        else:
            self._selector = LassoSelector(self.ax, self._on_lasso, useblit=False, button=[1],
                                           props={"color": theme.SELECTED, "linewidth": 1.5})

    def _navigating(self):
        return bool(getattr(self.toolbar, "mode", ""))

    @staticmethod
    def _global(event):
        gui = getattr(event, "guiEvent", None)
        try:
            return gui.globalPosition().toPoint()
        except AttributeError:
            return QCursor.pos()

    def _on_press(self, event):
        self._press = (event.x, event.y, event.button) \
            if event.inaxes is self.ax and not self.navigation.hand else None
        if self._press is not None and event.button == 1 and not self._navigating():
            self._dragging = self.marker_near(event.x, event.y)
            if self._dragging is not None:
                self._press = None                 # a drag of the marker, not a pick
                if self._selector is not None:     # nor a box
                    self._selector.set_active(False)

    def _on_release(self, event):
        if self._dragging is not None:
            if event.xdata is not None and event.inaxes is self.ax:
                self._drag_to(event, False)
            else:                                  # released outside: where it was last
                marker = self._dragging
                self.marker_moved.emit(int(marker["index"]), float("nan"), float("nan"), False)
            self._dragging = None
            if self._selector is not None:
                self._selector.set_active(True)
            return
        press, self._press = self._press, None
        if press is None or self.result is None or event.inaxes is not self.ax \
                or event.xdata is None or press[2] != event.button \
                or np.hypot(event.x - press[0], event.y - press[1]) > CLICK_PIXELS:
            return
        right = event.button == 3
        left = event.button == 1 and self.tool() == "pick" and not self._navigating()
        if right or left:
            self.pick_requested.emit(self.calc_id, {"x": float(event.xdata),
                                                    "y": float(event.ydata)},
                                     self._global(event))

    def _on_box(self, press, release):
        if self._navigating() or None in (press.xdata, release.xdata):
            return
        self.pick_requested.emit(self.calc_id, {"box": [float(press.xdata), float(press.ydata),
                                                        float(release.xdata),
                                                        float(release.ydata)]},
                                 self._global(release))

    def _on_lasso(self, vertices):
        if self._navigating() or len(vertices) < 3:
            return
        self.pick_requested.emit(self.calc_id, {"polygon": [[float(x), float(y)]
                                                            for x, y in vertices]},
                                 QCursor.pos())
