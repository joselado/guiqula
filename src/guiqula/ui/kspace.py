"""The Brillouin-zone canvas (decision 13.9): the zone of the current
system (the Wigner-Seitz cell of pyqula's reciprocal lattice, whose
vectors satisfy a_i . b_j = delta_ij), the high-symmetry points pyqula
names for its geometry, pyqula's default path (dashed), and the k-path of
the chosen calculation (bands, spectral function) with vertices that can
be dragged (they snap to the high-symmetry points, and are then stored by
label) or added with the Add points tool (a click on a vertex adds it
again, so that a path can pass twice through a point, Γ-K-M-Γ); the Fermi surface of the system,
when it has one, is drawn under the zone. The worker hands the geometry of
k-space in the build summary (engine/structure.kspace), since this process
cannot call pyqula; the window turns an edit into set_param on the
calculation's kpath. A click in the zone with Add points off, or a right
click in any mode, picks the k-point there (snapped onto a high-symmetry
point nearby, a vertex when on one), and the window offers what takes it
(PLAN.md phase 7: the LDOS or the eigenstate at that k). Drawn for one- and
two-dimensional systems (a 3D
zone is shown by its k3 = 0 cut: the plane of b1 and b2, clipped by every
reciprocal lattice vector, with the high-symmetry points in that plane; a
path that leaves it, pyqula's default one for instance, is drawn projected
onto it)."""
import itertools

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton, QToolButton,
                               QVBoxLayout, QWidget)

from guiqula.registry import kpaths
from guiqula.ui import theme

SNAP = 0.08          # a vertex this close (in |b1|) to a high-symmetry point takes its label
GRAB_PIXELS = 10     # a press this close to a vertex drags it
CLICK_PIXELS = 3     # a press released this close to where it started is a click, not a drag
NAMES = {"G": "Γ"}


def plane_basis(reciprocal):
    """Orthonormal rows (2, 3) of the plane drawn, the plane of b1 and b2
    (k3 = 0): x and y when that is the xy plane (every one- and
    two-dimensional lattice, a cubic one), else b1's direction and the one
    normal to it in the plane."""
    b = np.asarray(reciprocal, dtype=float).reshape(3, 3)
    if np.all(np.abs(b[:2, 2]) < 1e-9):
        return np.eye(3)[:2]
    along = b[0] / np.linalg.norm(b[0])
    across = b[1] - b[1].dot(along) * along
    return np.array([along, across / np.linalg.norm(across)])


def plane(reciprocal):
    """The in-plane coordinates (2, 2) of b1 and b2."""
    b = np.asarray(reciprocal, dtype=float).reshape(3, 3)
    return b[:2] @ plane_basis(b).T


def in_plane(kspace):
    """The periodic directions drawn: one, or two (the k3 = 0 cut of a 3D
    lattice)."""
    return min(int(kspace.get("dimensionality", 2)), 2)


def brillouin_zone(reciprocal, dimensionality):
    """Corners (M, 2) of the first Brillouin zone in the plane: the region
    closer to the origin than to any reciprocal lattice point; for a 3D
    lattice the cut of its zone by the plane (every reciprocal lattice
    vector clips it, not only b1 and b2)."""
    b = np.asarray(reciprocal, dtype=float).reshape(3, 3)
    if dimensionality == 1:
        half = plane(b)[0] / 2
        return np.array([-half, half])
    size = 4 * float(np.max(np.linalg.norm(plane(b), axis=1)))
    polygon = [np.array(p) for p in ((-size, -size), (size, -size), (size, size),
                                      (-size, size))]
    basis = plane_basis(b)
    for n in itertools.product(range(-2, 3), range(-2, 3),
                               range(-2, 3) if dimensionality == 3 else (0,)):
        if any(n):
            g = np.array(n) @ b
            polygon = _clip(polygon, basis @ g, g.dot(g) / 2)
    return np.array(polygon)


def _clip(polygon, normal, offset):
    """Sutherland-Hodgman: the part of a polygon where x.normal <= offset."""
    out = []
    for i, current in enumerate(polygon):
        previous = polygon[i - 1]
        inside_now, inside_before = current.dot(normal) <= offset, previous.dot(normal) <= offset
        if inside_now != inside_before:
            t = (offset - previous.dot(normal)) / (current - previous).dot(normal)
            out.append(previous + t * (current - previous))
        if inside_now:
            out.append(current)
    return out


def to_plane(reduced, reciprocal):
    """In-plane coordinates of reduced k-points (N, 3) -> (N, 2); a point
    off the plane (k3 != 0 in 3D) lands at its projection."""
    b = np.asarray(reciprocal, dtype=float).reshape(3, 3)
    return (np.asarray(reduced, dtype=float).reshape(-1, 3) @ b) @ plane_basis(b).T


def to_reduced(point, reciprocal):
    """Reduced coordinates [k1, k2, 0] of an in-plane point."""
    b = plane(reciprocal)
    k = np.linalg.lstsq(b.T, np.asarray(point, dtype=float), rcond=None)[0]
    return [float(k[0]), float(k[1]) if len(k) > 1 else 0.0, 0.0]


def plane_points(kspace):
    """{label: reduced} of the high-symmetry points in the plane drawn:
    for a 3D lattice those with k3 = 0 only (Z, at k3 = 1/2, projected onto
    the plane, sat on an image of another point, which a click stored)."""
    out = {}
    for name, k in kspace["special"].items():
        k = np.asarray(k, dtype=float)
        if kspace.get("dimensionality", 2) == 3:
            if abs(k[2] - round(k[2])) > 1e-9:
                continue
            k = np.array([k[0], k[1], 0.0])
        out[name] = k
    return out


def special_images(kspace):
    """{label: in-plane point} of the high-symmetry points in the plane,
    each taken at its image in the plane closest to the origin; pyqula has
    several names for some points (M, M1, X), and the first one it lists
    is kept."""
    b = kspace["reciprocal"]
    out = {}
    for name, k in plane_points(kspace).items():
        k = kpaths.nearest_image(b, k, [0.0, 0.0, 0.0], in_plane(kspace))
        point = to_plane(k, b)[0]
        if not any(np.allclose(point, other, atol=1e-6) for other in out.values()):
            out[name] = point
    return out


def snap(point, kspace):
    """Reduced coordinates of a point, moved onto the high-symmetry point
    (the image of it in the plane) nearby, if any: the vertex stays where
    it is drawn, and the engine names it after the point it is an image of."""
    b = kspace["reciprocal"]
    unit = float(np.linalg.norm(plane(b)[0]))
    reduced = to_reduced(point, b)
    for k in plane_points(kspace).values():
        image = kpaths.nearest_image(b, k, reduced, in_plane(kspace))
        if np.linalg.norm(to_plane(image, b)[0] - np.asarray(point)) < SNAP * unit:
            return [round(float(c), 9) for c in image]
    return [round(c, 6) for c in reduced]


def path_vertices(kpath, kspace):
    """In-plane points of a normalized k-path's vertices."""
    special = kspace["special"]
    reduced = kpaths.resolve(kspace["reciprocal"], kspace.get("dimensionality", 2), kpath,
                             lambda name: special[name])
    return to_plane(reduced, kspace["reciprocal"])


class KSpaceView(QWidget):
    """The k-space tab: the zone, the points, the paths, the path tools."""

    path_edited = Signal(str, object)      # calculation id, vertices (or None: the default)
    calculation_chosen = Signal(str)
    kpoint_picked = Signal(object, object)  # reduced k [k1, k2, k3], the menu's global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kspaceView")
        self.figure = Figure(figsize=(6, 5), dpi=100, layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setObjectName("kspaceCanvas")
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.calc_box = QComboBox()
        self.calc_box.setObjectName("kpathCalculation")
        self.calc_box.setToolTip("the calculation whose k-path is drawn and edited")
        self.calc_box.activated.connect(
            lambda i: self.calculation_chosen.emit(self.calc_box.itemData(i) or ""))
        self.add = QToolButton()
        self.add.setText("Add points")
        self.add.setObjectName("kpathAdd")
        self.add.setCheckable(True)
        self.add.setToolTip("click in the zone to add a vertex at the end of the path (it snaps "
                            "to a high-symmetry point nearby); click a vertex to pass through "
                            "it again; drag a vertex to move it")
        self.add.toggled.connect(lambda on: self.stop_navigating() if on else None)
        self.remove_last = QPushButton("Remove last")
        self.remove_last.setObjectName("kpathRemoveLast")
        self.remove_last.clicked.connect(self._remove_last)
        self.default = QPushButton("Default path")
        self.default.setObjectName("kpathDefault")
        self.default.setToolTip("pyqula's own path for this geometry")
        self.default.clicked.connect(lambda: self._edited(None))
        self.caption = QLabel("")
        self.caption.setObjectName("kspaceCaption")
        self.caption.setWordWrap(True)
        top = QHBoxLayout()
        top.addWidget(self.toolbar, 1)
        top.addWidget(QLabel("path of"))
        top.addWidget(self.calc_box)
        top.addWidget(self.add)
        top.addWidget(self.remove_last)
        top.addWidget(self.default)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.caption)
        self.kspace = self.kpath = self.ax = self._line = None
        self.calc = None
        self.vertices = np.zeros((0, 2))
        self._drag = None
        self._press = None         # where a press on a vertex started, until it moves
        self._click = None         # (x, y, button) of any press, for a pick on its release
        # pan or zoom takes the clicks: Add points shows off meanwhile (checking it again
        # turns them off), once the toolbar's own slot has switched the mode
        self.toolbar.actionTriggered.connect(lambda action: QTimer.singleShot(
            0, lambda: self.add.setChecked(False) if self.toolbar.mode else None))
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)

    # ---- drawing
    def show_kspace(self, kspace, calculations, calc, kpath, surface=None, caption=""):
        """kspace: the build's (with dimensionality); calculations: [(id,
        label)] with a k-path; kpath: calc's (normalized, None: default);
        surface: (points (N, 2) in the plane, weights) or None. Drawn in the
        active theme."""
        with theme.drawing(self.figure):
            self._show_kspace(kspace, calculations, calc, kpath, surface, caption)

    def _show_kspace(self, kspace, calculations, calc, kpath, surface, caption):
        self.kspace, self.calc, self.kpath = kspace, calc, kpath
        self.calc_box.blockSignals(True)
        self.calc_box.clear()
        for calc_id, label in calculations:
            self.calc_box.addItem(label, calc_id)
        self.calc_box.setCurrentIndex(max(self.calc_box.findData(calc), 0))
        self.calc_box.blockSignals(False)
        editable = calc is not None
        for widget in (self.add, self.remove_last, self.default):
            widget.setEnabled(editable)
        self.figure.clear()
        ax = self.ax = self.figure.add_subplot(111)
        b, dimensionality = kspace["reciprocal"], kspace.get("dimensionality", 2)
        if surface is not None:
            points, weights = surface
            weights = np.asarray(weights, dtype=float)
            ax.scatter(points[:, 0], points[:, 1], c=weights, s=10, marker="s", cmap="Oranges",
                       vmin=0.0, vmax=float(weights.max()) or 1.0, linewidths=0, zorder=0)
        zone = brillouin_zone(b, dimensionality)
        if dimensionality == 1:
            ax.plot(zone[:, 0], zone[:, 1], color=theme.CELL, linewidth=2)
        else:
            ax.add_patch(Polygon(zone, closed=True, fill=False, edgecolor=theme.CELL,
                                 linewidth=1.5, zorder=1))
        default = to_plane(kspace["default_path"], b)
        ax.plot(default[:, 0], default[:, 1], "--", color=theme.MUTED, linewidth=1, zorder=2,
                label="default path")
        for name, point in special_images(kspace).items():
            ax.plot(*point, "o", color=theme.POINT, markersize=4, zorder=3)
            ax.annotate(NAMES.get(name, name), point, textcoords="offset points",
                        xytext=(4, 4), fontsize=9)
        self.vertices = path_vertices(kpath, kspace) if kpath else np.zeros((0, 2))
        self._line, = ax.plot(self.vertices[:, 0], self.vertices[:, 1], "-o",
                              color=theme.SELECTED, linewidth=2, markersize=6, zorder=4)
        ax.set_aspect("equal", adjustable="box")
        extent = np.concatenate([zone, default, self.vertices]) if len(self.vertices) else \
            np.concatenate([zone, default])
        low, high = extent.min(axis=0), extent.max(axis=0)
        margin = 0.15 * float(np.max(high - low)) + 1e-9
        ax.set_xlim(low[0] - margin, high[0] + margin)
        ax.set_ylim(low[1] - margin, high[1] + margin)
        in_xy = np.allclose(plane_basis(b), np.eye(3)[:2])
        ax.set_xlabel("kx" if in_xy else "k along b1")
        ax.set_ylabel("ky" if in_xy else "k across b1, in the plane of b1 and b2")
        if dimensionality == 3:
            caption += (" · the k3 = 0 cut of the zone (the plane of b1 and b2) and the "
                        "points in it; a path leaving it is drawn projected")
        self.caption.setText(caption)
        self.canvas.draw()

    def clear(self, caption=""):
        self.kspace = self.ax = self._line = None
        self.figure.clear()
        theme.set_figure(self.figure)
        self.caption.setText(caption)
        self.canvas.draw_idle()

    # ---- editing
    def _vertex_labels(self):
        """The stored vertices (labels kept) of the current path."""
        return list(self.kpath) if self.kpath else []

    def add_point(self, point):
        """Append a vertex at an in-plane point (snapped); emits the path
        (a new path starts at Gamma)."""
        vertex = snap(point, self.kspace)
        vertices = self._vertex_labels() or [[0.0, 0.0, 0.0]]
        self._edited(vertices + [vertex])

    def move_vertex(self, index, point):
        vertices = self._vertex_labels()
        vertices[index] = snap(point, self.kspace)
        self._edited(vertices)

    def _remove_last(self):
        vertices = self._vertex_labels()[:-1]
        self._edited(vertices if len(vertices) >= 2 else None)

    def _edited(self, vertices):
        if self.calc is not None:
            self.path_edited.emit(self.calc, vertices)

    def stop_navigating(self):
        """Turn off the toolbar's pan or zoom mode, which takes the clicks."""
        mode = str(getattr(self.toolbar, "mode", ""))
        if mode == "pan/zoom":
            self.toolbar.pan()
        elif mode == "zoom rect":
            self.toolbar.zoom()

    def _pixel_near(self, event):
        if not len(self.vertices):
            return None
        xy = self.ax.transData.transform(self.vertices)
        d = np.hypot(xy[:, 0] - event.x, xy[:, 1] - event.y)
        i = int(np.argmin(d))
        return i if d[i] <= GRAB_PIXELS else None

    def _on_press(self, event):
        self._click = (event.x, event.y, event.button) if self.kspace is not None and \
            event.inaxes is self.ax else None
        if self.kspace is None or event.inaxes is not self.ax or event.button != 1 \
                or getattr(self.toolbar, "mode", "") or self.calc is None:
            return
        index = self._pixel_near(event)
        if index is not None:
            self._drag, self._press = index, (event.x, event.y)
        elif self.add.isChecked():
            self.add_point((event.xdata, event.ydata))

    def _on_motion(self, event):
        if self._drag is None or event.inaxes is not self.ax or event.xdata is None:
            return
        if self._press is not None:
            if np.hypot(event.x - self._press[0], event.y - self._press[1]) <= CLICK_PIXELS:
                return                             # not a drag yet
            self._press = None
        self.vertices[self._drag] = (event.xdata, event.ydata)
        self._line.set_data(self.vertices[:, 0], self.vertices[:, 1])
        self.canvas.draw_idle()

    def pick_at(self, point):
        """The reduced k of an in-plane point, snapped as a vertex would be."""
        return [float(c) for c in snap(point, self.kspace)]

    def _picked(self, event, point):
        gui = getattr(event, "guiEvent", None)
        try:
            position = gui.globalPosition().toPoint()
        except AttributeError:
            position = QCursor.pos()
        self.kpoint_picked.emit(self.pick_at(point), position)

    def _on_release(self, event):
        click, self._click = self._click, None
        is_click = click is not None and click[2] == event.button and \
            np.hypot(event.x - click[0], event.y - click[1]) <= CLICK_PIXELS
        if self._drag is None:
            if is_click and event.inaxes is self.ax and event.xdata is not None and (
                    event.button == 3 or (event.button == 1 and not self.add.isChecked()
                                          and not getattr(self.toolbar, "mode", ""))):
                self._picked(event, (event.xdata, event.ydata))
            return
        index, self._drag = self._drag, None
        if self._press is None:                    # it was dragged: move it
            self.move_vertex(index, self.vertices[index])
            return
        self._press = None
        if self.add.isChecked():                   # a click on it: pass through it again
            self.add_point(self.vertices[index])
        else:                                      # a pick of the vertex's k
            self._picked(event, self.vertices[index])
