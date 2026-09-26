"""The structure canvas (PLAN.md section 4): the geometry of one system as
the interactive worker built it (engine/structure.py), drawn with
matplotlib: atoms coloured by sublattice, first-neighbour bonds, the unit
cell and the neighbouring cells faded, and overlays for what the selected
entry touches (a region's sites, the positions a removal op deletes).
Drawn in the xy plane."""
import itertools

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from guiqula.ui import theme

IMAGE_LIMIT = 3000       # above this many sites the neighbouring cells are not drawn


def marker_size(n):
    return float(np.clip(3000.0 / max(n, 1), 6.0, 120.0))


def image_cells(dimensionality):
    ranges = [(-1, 0, 1)] * dimensionality + [(0,)] * (3 - dimensionality)
    return [np.array(c) for c in itertools.product(*ranges) if any(c)]


def site_colors(build):
    sublattice = build.get("sublattice")
    n = len(build["positions"])
    if sublattice is None:
        return [theme.SUBLATTICE[None]] * n
    return [theme.SUBLATTICE[1.0] if s > 0 else theme.SUBLATTICE[-1.0] for s in sublattice]


def bond_segments(build):
    """Segments (K, 2, 2) of the bonds touching the central cell."""
    r = np.asarray(build["positions"])[:, :2]
    lattice = np.asarray(build["lattice"])[:, :2]
    segments = [np.stack([r[i], r[j]]) for i, j in build["bonds"]]
    for i, j, *cell in build["image_bonds"]:
        shift = np.asarray(cell) @ lattice
        segments.append(np.stack([r[i], r[j] + shift]))
        segments.append(np.stack([r[j], r[i] - shift]))
    return np.array(segments).reshape(-1, 2, 2)


def cell_outline(build):
    """Corners of the unit cell (2D: a parallelogram around the sites), or
    None for a finite or one-dimensional system."""
    if build["dimensionality"] != 2:
        return None
    a1, a2 = np.asarray(build["lattice"])[:2, :2]
    centre = np.asarray(build["positions"])[:, :2].mean(axis=0)
    corner = centre - (a1 + a2) / 2
    return np.array([corner, corner + a1, corner + a1 + a2, corner + a2])


def draw_structure(ax, build, highlight=None, selected=None, removed=None, images=True):
    """Draw a build summary on a matplotlib Axes. highlight: boolean mask of
    sites (a region), selected: site indices, removed: (M, 3) positions."""
    r = np.asarray(build["positions"])
    xy = r[:, :2]
    n = len(r)
    size = marker_size(n)
    colors = site_colors(build)
    lattice = np.asarray(build["lattice"])[:, :2]
    central = bond_segments(build)
    cells = image_cells(build["dimensionality"]) if images and n <= IMAGE_LIMIT else []
    if cells:
        shifts = np.array([c @ lattice for c in cells])
        faded = (central[None, :, :, :] + shifts[:, None, None, :]).reshape(-1, 2, 2)
        ax.add_collection(LineCollection(faded, colors=theme.BOND, linewidths=0.8, alpha=0.25,
                                         zorder=1))
        ghosts = (xy[None, :, :] + shifts[:, None, :]).reshape(-1, 2)
        ax.scatter(ghosts[:, 0], ghosts[:, 1], c=colors * len(cells), s=size, alpha=0.2,
                   linewidths=0, zorder=2)
    if len(central):
        ax.add_collection(LineCollection(central, colors=theme.BOND, linewidths=1.2, zorder=3))
    ax.scatter(xy[:, 0], xy[:, 1], c=colors, s=size, edgecolors="white", linewidths=0.5,
               zorder=4)
    outline = cell_outline(build)
    if outline is not None:
        ax.add_patch(Polygon(outline, closed=True, fill=False, edgecolor=theme.CELL,
                             linestyle="--", linewidth=1.0, zorder=0))
    if highlight is not None and np.any(highlight):
        ax.scatter(xy[highlight, 0], xy[highlight, 1], s=size * 2.6, facecolors="none",
                   edgecolors=theme.REGION, linewidths=1.8, zorder=5)
    if selected is not None and len(selected):
        idx = np.asarray(selected, dtype=int)
        ax.scatter(xy[idx, 0], xy[idx, 1], s=size * 2.0, facecolors="none",
                   edgecolors=theme.SELECTED, linewidths=2.0, zorder=6)
    if removed is not None and len(removed):
        p = np.asarray(removed, dtype=float).reshape(-1, 3)
        ax.scatter(p[:, 0], p[:, 1], marker="x", c=theme.REMOVED, s=size, linewidths=2.0,
                   zorder=7)
    ax.set_aspect("equal", adjustable="box")
    ax.autoscale_view()
    ax.margins(0.08)
    ax.tick_params(labelsize=8)


class StructureView(QWidget):
    """A matplotlib canvas with its navigation toolbar (pan, zoom, save)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("structureView")
        self.figure = Figure(figsize=(6, 5), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setObjectName("structureCanvas")
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setObjectName("structureToolbar")
        self.caption = QLabel("No system yet: add one from the Geometry toolbar.")
        self.caption.setObjectName("structureCaption")
        self.caption.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.caption)
        self.system_id = None
        self.build = None
        self.ax = None

    def show_structure(self, system_id, build, caption="", **overlays):
        """Redraw; keeps the zoom when the same system is shown again."""
        limits = None
        if self.ax is not None and system_id == self.system_id and self.build is not None:
            limits = (self.ax.get_xlim(), self.ax.get_ylim())
        same_sites = self.build is not None and build is not None and \
            np.shape(self.build["positions"]) == np.shape(build["positions"])
        self.system_id, self.build = system_id, build
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        draw_structure(self.ax, build, **overlays)
        if limits is not None and same_sites:
            self.ax.set_xlim(*limits[0])
            self.ax.set_ylim(*limits[1])
        self.figure.tight_layout()
        self.caption.setText(caption)
        self.canvas.draw_idle()

    def clear(self, caption=""):
        self.system_id, self.build, self.ax = None, None, None
        self.figure.clear()
        self.caption.setText(caption)
        self.canvas.draw_idle()
