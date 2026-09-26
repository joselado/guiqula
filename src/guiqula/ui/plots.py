"""Result plots (PLAN.md 3.4): one matplotlib implementation per plot kind,
drawn in the UI process from a Result's arrays. Phase 1 has ``lines`` and
``colored_scatter``; the other kinds arrive with their calculations."""
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def _lines(ax, arrays, plot):
    x = np.asarray(arrays[plot["x"]])
    y = np.asarray(arrays[plot["y"]])
    ax.plot(x, y.reshape(len(x), -1), color="C0", linewidth=1.2)


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


DRAW = {"lines": _lines, "colored_scatter": _colored_scatter}


def draw(figure, result, title=""):
    figure.clear()
    ax = figure.add_subplot(111)
    plot = result.plot
    DRAW[plot["kind"]](ax, result.arrays, plot)
    ax.set_xlabel(plot.get("xlabel", plot.get("x", "")))
    ax.set_ylabel(plot.get("ylabel", plot.get("y", "")))
    ax.set_title(title, fontsize=10)
    if plot.get("x") == "k":
        ax.set_xlim(np.min(result.arrays["k"]), np.max(result.arrays["k"]))
    figure.tight_layout()
    return ax


class PlotView(QWidget):
    """A matplotlib canvas with its navigation toolbar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("plotView")
        self.figure = Figure(figsize=(6, 4), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setObjectName("plotCanvas")
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.caption = QLabel("No result yet: choose a calculation and press Run (F5).")
        self.caption.setObjectName("plotCaption")
        self.caption.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.caption)
        self.result = None

    def show_result(self, result, title="", caption=""):
        self.result = result
        draw(self.figure, result, title)
        self.caption.setText(caption)
        self.canvas.draw_idle()

    def clear(self, caption=""):
        self.result = None
        self.figure.clear()
        self.caption.setText(caption)
        self.canvas.draw_idle()
