"""Result plots (PLAN.md 3.4): one matplotlib implementation per plot kind,
drawn in the UI process from a Result's arrays.

Kinds (the ``kind`` of a Result's plot spec, which also names the arrays):

- ``lines``: y (one or more columns) against x;
- ``colored_scatter``: the same, points coloured by c (bands with an
  operator);
- ``heatmap``: c on the points (x, y), given flat (one value per point, a
  grid is recognised and drawn as cells) or as a (len(x), len(y)) array;
  ``symmetric`` centres a diverging colour map at zero (Berry curvature);
- ``structure_scalar``: one value per site drawn on the atoms (LDOS,
  density), from the geometry the Result carries (Result.structure);
- ``structure_vector``: one vector per site, arrows for the in-plane part
  and dots for the z part (magnetization);
- ``scalar``: numbers in a table (Chern number, gap), ``rows`` naming
  [array, label] pairs.

Every calculation gets its own PlotView (a tab of the viewport, which can
be detached into a floating dock): the navigation toolbar (pan, zoom, save
the figure), Save data (the arrays and the metadata, io/results.py),
Detach, and a readout of the data point under the mouse.
"""
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from guiqula.ui import structure as structure_tools

READOUT_PIXELS = 12      # the readout names a data point this close to the mouse
KINDS = ("lines", "colored_scatter", "heatmap", "structure_scalar", "structure_vector", "scalar")


def _lines(ax, result):
    arrays, plot = result.arrays, result.plot
    x = np.asarray(arrays[plot["x"]])
    y = np.asarray(arrays[plot["y"]]).reshape(len(x), -1)
    ax.plot(x, y, color="C0", linewidth=1.2)
    return np.repeat(x[:, None], y.shape[1], axis=1).ravel(), y.ravel(), None


def _colored_scatter(ax, result):
    arrays, plot = result.arrays, result.plot
    x = np.asarray(arrays[plot["x"]])
    y = np.asarray(arrays[plot["y"]]).reshape(len(x), -1)
    c = np.asarray(arrays[plot["c"]]).reshape(y.shape)
    xs = np.repeat(x[:, None], y.shape[1], axis=1)
    limit = float(np.max(np.abs(c)))
    if limit < 1e-8:          # all zero up to rounding: do not stretch the noise
        limit = 1.0
    points = ax.scatter(xs.ravel(), y.ravel(), c=c.ravel(), s=6, cmap="coolwarm",
                        vmin=-limit, vmax=limit)
    ax.figure.colorbar(points, ax=ax, label=plot.get("clabel", plot["c"]))
    return xs.ravel(), y.ravel(), c.ravel()


def grid_of(x, y, c):
    """(xs, ys, C) with C[i, j] the value at (xs[i], ys[j]) when the flat
    points (x, y, c) fill a regular grid, else None."""
    x, y, c = (np.asarray(a, dtype=float).ravel() for a in (x, y, c))
    xs, ix = np.unique(np.round(x, 10), return_inverse=True)
    ys, iy = np.unique(np.round(y, 10), return_inverse=True)
    if len(xs) * len(ys) != len(c) or len(xs) < 2 or len(ys) < 2:
        return None
    grid = np.full((len(xs), len(ys)), np.nan)
    grid[ix, iy] = c
    if np.isnan(grid).any():
        return None
    return xs, ys, grid


def _heatmap(ax, result):
    arrays, plot = result.arrays, result.plot
    x, y, c = (np.asarray(arrays[plot[k]], dtype=float) for k in ("x", "y", "c"))
    if c.ndim == 2:                          # c[i, j] at (x[i], y[j])
        xs, ys = np.meshgrid(x, y, indexing="ij")
        x, y, c = xs.ravel(), ys.ravel(), c.ravel()
    style = {"cmap": plot.get("cmap", "coolwarm" if plot.get("symmetric") else "inferno")}
    if plot.get("symmetric"):
        limit = float(np.max(np.abs(c))) if len(c) else 1.0
        style.update(vmin=-(limit or 1.0), vmax=limit or 1.0)
    grid = grid_of(x, y, c)
    if grid is not None:
        mesh = ax.pcolormesh(grid[0], grid[1], grid[2].T, shading="nearest", **style)
    else:
        mesh = ax.scatter(x, y, c=c, s=12, marker="s", linewidths=0, **style)
    ax.figure.colorbar(mesh, ax=ax, label=plot.get("clabel", plot["c"]))
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


def _structure_scalar(ax, result):
    build, plot = _on_structure(result), result.plot
    values = np.asarray(result.arrays[plot["values"]], dtype=float).ravel()
    _draw_on(ax)(ax, build, site_values={
        "values": values, "label": plot.get("clabel", plot["values"]),
        "symmetric": plot.get("symmetric", False)})
    return _site_points(ax, build, values)


def _structure_vector(ax, result):
    build, plot = _on_structure(result), result.plot
    vectors = np.asarray(result.arrays[plot["vectors"]], dtype=float).reshape(-1, 3)
    _draw_on(ax)(ax, build, arrows={
        "vectors": vectors, "label": plot.get("clabel", plot["vectors"])})
    return _site_points(ax, build, np.linalg.norm(vectors, axis=1))


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
        ax.text(0.05, yy, label, fontsize=13, transform=ax.transAxes, va="center")
        ax.text(0.95, yy, text, fontsize=18, transform=ax.transAxes, va="center", ha="right",
                family="monospace", weight="bold")
    return np.zeros(0), np.zeros(0), None


DRAW = {"lines": _lines, "colored_scatter": _colored_scatter, "heatmap": _heatmap,
        "structure_scalar": _structure_scalar, "structure_vector": _structure_vector,
        "scalar": _scalar}
ON_STRUCTURE = ("structure_scalar", "structure_vector")


def draw(figure, result, title=""):
    """Draw a Result; returns the Axes and the points (x, y, c or None)
    the readout looks up."""
    figure.clear()
    plot = result.plot
    three_d = plot["kind"] in ON_STRUCTURE and result.structure is not None and \
        not structure_tools.is_flat(result.structure)
    ax = figure.add_subplot(111, projection="3d" if three_d else None)
    points = DRAW[plot["kind"]](ax, result)
    if plot["kind"] in ON_STRUCTURE and not three_d:
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    elif plot["kind"] != "scalar":
        ax.set_xlabel(plot.get("xlabel", plot.get("x", "")))
        ax.set_ylabel(plot.get("ylabel", plot.get("y", "")))
    ax.set_title(title, fontsize=10)
    if plot.get("x") == "k" and plot["kind"] in ("lines", "colored_scatter"):
        ax.set_xlim(np.min(result.arrays["k"]), np.max(result.arrays["k"]))
    return ax, points


def _number(value):
    return f"{value:.6g}"


class PlotView(QWidget):
    """A matplotlib canvas with its navigation toolbar, for the results of
    one calculation (calc_id)."""

    save_requested = Signal(str)          # calculation id
    detach_requested = Signal(str)

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
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.save_data)
        self.toolbar.addWidget(self.detach)
        self.readout = QLabel("")
        self.readout.setObjectName(f"readout{suffix}")
        self.caption = QLabel("No result yet: choose a calculation and press Run (F5).")
        self.caption.setObjectName(f"plotCaption{suffix}")
        self.caption.setWordWrap(True)
        self.caption.setMinimumHeight(2 * self.caption.fontMetrics().lineSpacing())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.readout)
        layout.addWidget(self.caption)
        self.result = None
        self.ax = None
        self.points = None
        self.stale = False
        self._update_buttons()
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)

    def _update_buttons(self):
        self.save_data.setEnabled(self.result is not None and bool(self.calc_id))
        self.detach.setVisible(bool(self.calc_id))

    def show_result(self, result, title="", caption="", stale=False):
        self.result = result
        self.stale = stale
        self.ax, self.points = draw(self.figure, result, title)
        self.caption.setText(caption)
        self.readout.setText("")
        self.canvas.draw()        # now: the limits and the layout are final for the readout
        self._update_buttons()

    def clear(self, caption=""):
        self.result = self.ax = self.points = None
        self.stale = False
        self.figure.clear()
        self.caption.setText(caption)
        self.readout.setText("")
        self.canvas.draw_idle()
        self._update_buttons()

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
            return f"site {i} at ({_number(x[i])}, {_number(y[i])}) · {what} {_number(c[i])}"
        text = (f"{plot.get('xlabel', plot.get('x'))} {_number(x[i])} · "
                f"{plot.get('ylabel', plot.get('y'))} {_number(y[i])}")
        if c is not None:
            text += f" · {plot.get('clabel', plot.get('c'))} {_number(c[i])}"
        return text

    def _on_motion(self, event):
        if self.result is None or event.inaxes is not self.ax or event.xdata is None:
            if self.readout.text():
                self.readout.setText("")
            return
        i = self.point_near(event.x, event.y)
        self.readout.setText(self.readout_text(i) if i is not None else
                             f"({_number(event.xdata)}, {_number(event.ydata)})")
