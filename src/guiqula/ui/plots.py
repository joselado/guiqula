"""Result plots (PLAN.md 3.4): one matplotlib implementation per plot kind,
drawn in the UI process from a Result's arrays. Phase 1 has ``lines`` and
``colored_scatter``; the other kinds arrive with their calculations.

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

READOUT_PIXELS = 12      # the readout names a data point this close to the mouse


def _lines(ax, arrays, plot):
    x = np.asarray(arrays[plot["x"]])
    y = np.asarray(arrays[plot["y"]]).reshape(len(x), -1)
    ax.plot(x, y, color="C0", linewidth=1.2)
    return np.repeat(x[:, None], y.shape[1], axis=1).ravel(), y.ravel(), None


def _colored_scatter(ax, arrays, plot):
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


DRAW = {"lines": _lines, "colored_scatter": _colored_scatter}


def draw(figure, result, title=""):
    """Draw a Result; returns the Axes and the points (x, y, c or None)
    the readout looks up."""
    figure.clear()
    ax = figure.add_subplot(111)
    plot = result.plot
    points = DRAW[plot["kind"]](ax, result.arrays, plot)
    ax.set_xlabel(plot.get("xlabel", plot.get("x", "")))
    ax.set_ylabel(plot.get("ylabel", plot.get("y", "")))
    ax.set_title(title, fontsize=10)
    if plot.get("x") == "k":
        ax.set_xlim(np.min(result.arrays["k"]), np.max(result.arrays["k"]))
    figure.tight_layout()
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
        self.figure = Figure(figsize=(6, 4), dpi=100)
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
        self.canvas.draw_idle()
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
