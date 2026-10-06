"""The structure canvas (PLAN.md section 4): the geometry of one system as
the interactive worker built it (engine/structure.py), drawn with
matplotlib: atoms coloured by sublattice, first-neighbour bonds, the unit
cell and the neighbouring cells faded, and overlays for what the selected
entry touches (a region's sites, the positions a removal op deletes).
Drawn in the xy plane.

Three views (VIEWS), chosen with the box on the canvas bar: the sites
and bonds; the Hamiltonian (13.8: atoms coloured by onsite energy, every
hopping drawn with a width following its amplitude and a colour following
its phase, exchange fields as arrows for the in-plane part and dots inside
the atoms for the z part); and a Field preview (PLAN.md 3.8: a scalar
Field colours the atoms, a vector Field draws the same arrows and dots). A
colour bar is drawn only for values that vary. The window computes what to draw;
the pure functions below turn build arrays into artists.

Site selection (PLAN.md 13.2): the pick tool selects the atom under a
click (a click on nothing clears), the box and lasso tools select what
they enclose; with all three, shift adds and ctrl toggles. The drawing
moves as Inkscape's canvas does (ui/canvas_navigation.py): the wheel
scrolls, ctrl and the wheel zooms, the middle button or Space and the left
button drag it; the bar's Pan and Zoom still pan and zoom (while they do,
the tools are off). The bar (ui/canvasbar.py, PLAN.md phase 8, package P3)
holds Fit, Pan, Zoom, the selection tools and what acts on the selection,
what the canvas shows, the brush and Save image, over matplotlib's toolbar,
which is kept hidden for its modes.
The selection is kept as positions, so it survives a rebuild of the same
geometry. The window turns it into a region or a removal op; the pure
functions below do the geometry, so tests and drivers use them without a
mouse.

A geometry that is not flat (a three-dimensional lattice, buckled or
stacked layers) is drawn in 3D with the same overlays; the 3D box switches
between that and the xy projection, where the selection tools work (they
act on x and y only). The 3D drawing is matplotlib's mplot3d (drag to turn
it) or, when View > 3D drawing says so, pyvista's (ui/pyvista_view.py:
moved in space as Blender's viewport is), which takes the place of the
matplotlib canvas (its Reset view, View and Save image take the bar's Fit,
Pan, Zoom and Save image); a pyvista that cannot draw leaves the
drawing to mplot3d and the caption says why.
pyqtgraph's OpenGL view was the plan (PLAN.md section 2), but Qt refuses
OpenGL widgets on the offscreen platform the tests and tools/drive.py use,
and PyOpenGL is not a dependency.
"""
import itertools

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.collections import EllipseCollection, LineCollection
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from matplotlib.path import Path
from matplotlib.widgets import LassoSelector, RectangleSelector
from matplotlib import cm, colors as mcolors
from mpl_toolkits.mplot3d.art3d import Line3DCollection
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QLabel, QLineEdit, QMenu,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from guiqula.core.nearest import nearest_indices
from guiqula.ui import shortcuts, theme
from guiqula.ui.canvas_navigation import CanvasNavigation, bind_keys
from guiqula.ui.canvasbar import CanvasBar

IMAGE_LIMIT = 3000       # above this many sites the neighbouring cells are not drawn
RADIUS = 0.22            # of an atom, in pyqula's length unit (first neighbours at 1)
PICK_RADIUS = 0.5        # a click selects the nearest site within this distance
MIN_SPAN = 2.0           # the flat view spans at least this (the first neighbours of one site)
SAME_SITE = 1e-3         # positions closer than this are the same site
OUTLINE_PIXELS = 6       # circles narrower than this on the screen are drawn without outline
TOOLS = ("pick", "box", "lasso")
MODES = ("replace", "add", "toggle", "remove")
VIEWS = {"structure": "Sites and bonds", "hamiltonian": "Hamiltonian", "field": "Field preview"}
SELECTION_ZORDER = 6
VALUE_MAP = "coolwarm"       # site values, symmetric about zero
SEQUENTIAL_MAP = "viridis"   # site values of one sign (a density, an LDOS)
FLAT = 1e-6                  # heights spread less than this: a flat geometry
PROJECTIONS = ("auto", "xy", "3d")   # auto: 3D when the geometry is not flat


# ---- selection geometry (pure numpy)
def indices_in_box(xy, x0, y0, x1, y1):
    xy = np.asarray(xy)[:, :2]
    (xa, xb), (ya, yb) = sorted((x0, x1)), sorted((y0, y1))
    inside = (xy[:, 0] >= xa) & (xy[:, 0] <= xb) & (xy[:, 1] >= ya) & (xy[:, 1] <= yb)
    return np.nonzero(inside)[0]


def indices_in_polygon(xy, vertices):
    vertices = np.asarray(vertices, dtype=float).reshape(-1, 2)
    if len(vertices) < 3:
        return np.zeros(0, dtype=int)
    return np.nonzero(Path(vertices).contains_points(np.asarray(xy)[:, :2]))[0]


def nearest_index(xy, x, y, radius=PICK_RADIUS):
    """The site nearest to (x, y) within radius, or None."""
    xy = np.asarray(xy)[:, :2]
    if len(xy) == 0:
        return None
    d = np.hypot(xy[:, 0] - x, xy[:, 1] - y)
    i = int(np.argmin(d))
    return i if d[i] <= radius else None


def coordination(build):
    """First neighbours of each site, counting bonds to the neighbouring cells."""
    n = np.zeros(len(build["positions"]), dtype=int)
    for pairs in (np.asarray(build["bonds"]).reshape(-1, 2),
                  np.asarray(build["image_bonds"]).reshape(-1, 5)[:, :2]):
        np.add.at(n, pairs[:, 0], 1)
        np.add.at(n, pairs[:, 1], 1)
    return n


def edge_indices(build):
    """Sites with fewer first neighbours than the best-connected ones."""
    n = coordination(build)
    return np.nonzero(n < n.max())[0] if len(n) else np.zeros(0, dtype=int)


def sublattice_indices(build, sign):
    sublattice = build.get("sublattice")
    if sublattice is None:
        return np.zeros(0, dtype=int)
    return np.nonzero(np.sign(sublattice) == np.sign(sign))[0]


def combine(current, new, mode="replace"):
    """Apply a selection gesture to a set of indices."""
    current, new = set(map(int, current)), set(map(int, new))
    if mode == "replace":
        out = new
    elif mode == "add":
        out = current | new
    elif mode == "toggle":
        out = current ^ new
    elif mode == "remove":
        out = current - new
    else:
        raise ValueError(f"unknown selection mode {mode!r}; modes: {list(MODES)}")
    return np.array(sorted(out), dtype=int)


def match_positions(positions, stored, tol=SAME_SITE):
    """Indices of the sites at the stored positions (those still there)."""
    stored = np.asarray(stored, dtype=float).reshape(-1, 3)
    return np.nonzero(nearest_indices(stored, positions, tol) >= 0)[0]


class DataCircles(EllipseCollection):
    """Circles of a radius in data units, whose outlines are drawn only
    while a circle is at least OUTLINE_PIXELS wide on the screen: zoomed
    out, an outline is a smudge, and stroking thousands of them was half of
    a redraw of a large geometry (PLAN.md phase 5, part 3)."""

    def __init__(self, radius, **kwargs):
        super().__init__(2 * radius, 2 * radius, 0.0, units="xy", **kwargs)
        self.radius = radius
        self.outline = self.get_linewidths()

    def draw(self, renderer):
        if self.axes is not None:
            x0, x1 = self.axes.transData.transform([(0.0, 0.0), (self.radius, 0.0)])[:, 0]
            wide = 2 * abs(x1 - x0) >= OUTLINE_PIXELS
            self.set_linewidths(self.outline if wide else 0.0)
        super().draw(renderer)


def circles(ax, xy, radius, zorder, autolim=False, **style):
    """Circles of a radius in data units (they grow when zooming in), one
    per row of xy; set_offsets() moves them later."""
    collection = DataCircles(radius, offsets=np.asarray(xy, dtype=float).reshape(-1, 2),
                             offset_transform=ax.transData, zorder=zorder, **style)
    ax.add_collection(collection, autolim=autolim)
    return collection


def image_cells(dimensionality):
    ranges = [(-1, 0, 1)] * dimensionality + [(0,)] * (3 - dimensionality)
    return [np.array(c) for c in itertools.product(*ranges) if any(c)]


def site_colors(build):
    sublattice = build.get("sublattice")
    n = len(build["positions"])
    if sublattice is None:
        return [theme.SUBLATTICE[None]] * n
    return [theme.SUBLATTICE[1.0] if s > 0 else theme.SUBLATTICE[-1.0] for s in sublattice]


def atom_edge(site_values):
    """The outline of the atoms: the background's colour between the
    sublattice colours, which it separates, and the bonds' grey on atoms
    coloured by a value, whose zero is the pale middle of a diverging scale
    and would otherwise be lost on the light background."""
    return theme.ATOM_EDGE if site_values is None else theme.BOND


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


def hopping_segments(build, view):
    """Segments (K, 2, 2) of the hoppings of a Hamiltonian view that touch
    the central cell, with their amplitude and phase (the mirrored copy of
    a bond to a neighbouring cell carries the conjugate phase)."""
    r = np.asarray(build["positions"])[:, :2]
    lattice = np.asarray(build["lattice"])[:, :2]
    rows = np.asarray(view["hoppings"]).reshape(-1, 5)
    amplitude, phase = np.asarray(view["amplitude"]), np.asarray(view["phase"])
    i, j, cells = rows[:, 0], rows[:, 1], rows[:, 2:5]
    shift = cells @ lattice if len(rows) else np.zeros((0, 2))
    segments = np.stack([r[i], r[j] + shift], axis=1) if len(rows) else np.zeros((0, 2, 2))
    image = np.any(cells != 0, axis=1)
    mirrored = np.stack([r[j[image]], r[i[image]] - shift[image]], axis=1)
    return (np.concatenate([segments, mirrored]).reshape(-1, 2, 2),
            np.concatenate([amplitude, amplitude[image]]),
            np.concatenate([phase, -phase[image]]))


def varies(values, tol=1e-9):
    """Whether the finite values differ (a colour bar is drawn only then)."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return len(values) > 0 and float(values.max() - values.min()) > tol


def value_colors(values, symmetric=True, cmap=VALUE_MAP):
    """Colours of site values and the mappable for a colour bar; symmetric:
    a colour scale centred at zero. The finite values set the scale; a
    value that is not finite (a Field's 1/x at x = 0) is grey (theme.MUTED)
    instead of turning every site black."""
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(values)
    good = values[finite]
    limit = float(np.max(np.abs(good))) if len(good) else 0.0
    if symmetric:
        limit = limit if limit > 1e-12 else 1.0
        norm = mcolors.Normalize(-limit, limit)
    else:
        low, high = (float(good.min()), float(good.max())) if len(good) else (0.0, 1.0)
        norm = mcolors.Normalize(low, high if high > low else low + 1.0)
    mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
    colors = [mcolors.to_hex(c) for c in mappable.to_rgba(np.where(finite, values, 0.0))]
    return [c if ok else theme.MUTED for c, ok in zip(colors, finite)], mappable


def value_range(values):
    """'from a to b' of the finite values, and how many are not finite (the
    captions of the Field preview)."""
    values = np.asarray(values, dtype=float)
    good = values[np.isfinite(values)]
    text = f"from {good.min():.4g} to {good.max():.4g}" if len(good) else "no finite value"
    bad = len(values) - len(good)
    if bad and len(good):
        text += f"; {bad} site{'s' if bad > 1 else ''} not finite (grey)"
    return text


def finite_vectors(vectors):
    """Which vectors (N, 3) are finite: those get an arrow, and the longest
    of them sets the scale of all."""
    vectors = np.asarray(vectors, dtype=float).reshape(-1, 3)
    return np.all(np.isfinite(vectors), axis=1)


def cell_outline(build):
    """Corners of the unit cell (2D: a parallelogram around the sites), or
    None for a finite or one-dimensional system."""
    if build["dimensionality"] != 2:
        return None
    a1, a2 = np.asarray(build["lattice"])[:2, :2]
    r = np.asarray(build["positions"])[:, :2]
    centre = r.mean(axis=0) if len(r) else np.zeros(2)      # every site removed
    corner = centre - (a1 + a2) / 2
    return np.array([corner, corner + a1, corner + a1 + a2, corner + a2])


SHORT_LABEL = 6       # a colour bar label this short is put upright above the bar


def colorbar(ax, mappable, label, **style):
    """A colour bar next to an axes, its label at the size of the axis
    labels: a short one (sz, LDOS) upright above the bar, where it reads
    at a glance, a long one along the bar; a horizontal bar keeps its
    label below it. Returns the bar."""
    import matplotlib
    bar = ax.figure.colorbar(mappable, ax=ax, **style)
    if label and len(label) <= SHORT_LABEL and style.get("orientation") != "horizontal":
        bar.ax.set_title(label, fontsize=matplotlib.rcParams["axes.labelsize"], pad=8)
    else:
        bar.set_label(label)
    return bar


def value_map(site_values):
    """The colour map of site values: the one they name (a plot's style),
    else diverging about zero when symmetric, sequential otherwise."""
    if site_values.get("cmap"):
        return site_values["cmap"]
    return VALUE_MAP if site_values.get("symmetric", True) else SEQUENTIAL_MAP


def arrow_style(arrows):
    """(length, width, colour, colour map) of a vector per site: the
    multiples of the usual length and width and the colour the arrows
    name (a plot's style, ui/plotstyle.py), else 1, 1, the theme's arrow
    colour and the diverging map."""
    return (float(arrows.get("length") or 1.0), float(arrows.get("width") or 1.0),
            arrows.get("color") or theme.ARROW, arrows.get("cmap") or VALUE_MAP)


def draw_structure(ax, build, highlight=None, selected=None, removed=None, images=True,
                   site_values=None, arrows=None, hoppings=None, atom_size=1.0, bonds=True):
    """Draw a build summary on a matplotlib Axes. highlight: boolean mask of
    sites (a region), selected: site indices, removed: (M, 3) positions;
    site_values: {"values": (N,), "label", "symmetric", "cmap"} colours the
    atoms (symmetric, the default: a diverging scale centred at zero; else
    a sequential one from the smallest to the largest value; cmap, a map
    of its own); arrows: {"vectors": (N, 3), "label", "length", "width",
    "color", "cmap"} draws the in-plane part at the sites, coloured by the
    z part (arrow_style); hoppings: a Hamiltonian view, whose hoppings
    replace the first-neighbour bonds; atom_size: a multiple of RADIUS;
    bonds: whether the first-neighbour bonds are drawn (the hoppings of a
    Hamiltonian view always are). Only the central cell sets the view (at
    least MIN_SPAN wide); the neighbouring cells show at its border.
    Returns the collection of the selection rings."""
    r = np.asarray(build["positions"])
    xy = r[:, :2]
    n = len(r)
    radius = RADIUS * float(atom_size)
    colors = site_colors(build)
    bars = []

    def add_bar(mappable, label, horizontal=False):
        if horizontal:
            colorbar(ax, mappable, label, orientation="horizontal", shrink=0.6, pad=0.1,
                     aspect=40)
        else:                     # a second vertical bar goes to the left
            colorbar(ax, mappable, label, shrink=0.7, pad=0.02 if not bars else 0.08,
                     location="right" if not bars else "left")
            bars.append(label)
    if site_values is not None:
        colors, mappable = value_colors(site_values["values"],
                                        symmetric=site_values.get("symmetric", True),
                                        cmap=value_map(site_values))
        if varies(site_values["values"]):
            add_bar(mappable, site_values.get("label", ""))
    lattice = np.asarray(build["lattice"])[:, :2]
    if hoppings is not None:
        central, amplitude, phase = hopping_segments(build, hoppings)
        top = float(amplitude.max()) if len(amplitude) else 1.0
        widths = 0.4 + 3.6 * amplitude / (top if top > 0 else 1.0)
        phase_map = cm.ScalarMappable(norm=mcolors.Normalize(-np.pi, np.pi),
                                      cmap=theme.PHASE_MAP)
        bond_colors = phase_map.to_rgba(phase)
        if len(phase) and np.any(np.abs(phase) > 1e-6):
            add_bar(phase_map, "hopping phase", horizontal=True)
    else:
        central = bond_segments(build) if bonds else np.zeros((0, 2, 2))
        widths, bond_colors = 1.2, theme.BOND
    cells = image_cells(build["dimensionality"]) if images and n <= IMAGE_LIMIT else []
    if cells:
        shifts = np.array([c @ lattice for c in cells])
        faded = (central[None, :, :, :] + shifts[:, None, None, :]).reshape(-1, 2, 2)
        faded_colors = bond_colors if isinstance(bond_colors, str) else \
            np.tile(bond_colors, (len(cells), 1))
        faded_widths = widths if np.isscalar(widths) else np.tile(widths, len(cells)) * 0.7
        ax.add_collection(LineCollection(faded, colors=faded_colors, linewidths=faded_widths,
                                         alpha=0.25, zorder=1), autolim=False)
        ghosts = (xy[None, :, :] + shifts[:, None, :]).reshape(-1, 2)
        circles(ax, ghosts, radius, 2, facecolors=colors * len(cells), alpha=0.2,
                linewidths=0)
    if len(central):
        if hoppings is not None:        # an outline, so that pale phase colours stay visible
            ax.add_collection(LineCollection(central, colors=theme.BOND, alpha=0.6,
                                             linewidths=np.asarray(widths) + 1.2, zorder=3),
                              autolim=False)
        ax.add_collection(LineCollection(central, colors=bond_colors, linewidths=widths,
                                         zorder=3), autolim=False)
    circles(ax, xy, radius, 4, autolim=True, facecolors=colors, edgecolors=atom_edge(site_values),
            linewidths=0.5)
    if arrows is not None:
        vectors = np.asarray(arrows["vectors"], dtype=float).reshape(-1, 3)
        length, width, color, cmap = arrow_style(arrows)
        if varies(vectors[:, 2]) or np.any(np.abs(vectors[:, 2]) > 1e-12):
            dots, mappable = value_colors(vectors[:, 2], cmap=cmap)
            circles(ax, xy, 0.5 * radius, 5, facecolors=dots, edgecolors=color,
                    linewidths=0.4)
            add_bar(mappable, f"{arrows.get('label', '')}, z (dots)")
        shown = finite_vectors(vectors)
        lengths = np.linalg.norm(vectors[shown, :2], axis=1)
        longest = float(lengths.max()) if len(lengths) else 0.0
        if longest > 1e-12:
            ax.quiver(xy[shown, 0], xy[shown, 1], vectors[shown, 0], vectors[shown, 1],
                      angles="xy", scale_units="xy", scale=longest / (0.8 * length),
                      pivot="middle", width=0.006 * width, color=color, zorder=8)
    outline = cell_outline(build)
    if outline is not None:
        ax.add_patch(Polygon(outline, closed=True, fill=False, edgecolor=theme.CELL,
                             linestyle="--", linewidth=1.0, zorder=0))
    if highlight is not None and np.any(highlight):
        circles(ax, xy[np.asarray(highlight, dtype=bool)], 1.7 * radius, 5, facecolors="none",
                edgecolors=theme.REGION, linewidths=1.8)
    idx = np.asarray(selected if selected is not None else [], dtype=int)
    selection = circles(ax, xy[idx], 1.45 * radius, SELECTION_ZORDER, facecolors="none",
                        edgecolors=theme.SELECTED, linewidths=2.0)
    if removed is not None and len(removed):
        p = np.asarray(removed, dtype=float).reshape(-1, 3)[:, :2]
        circles(ax, p, RADIUS, 7, facecolors="none", edgecolors=theme.REMOVED,
                linewidths=1.2, linestyles="--")
        ax.scatter(p[:, 0], p[:, 1], marker="x", c=theme.REMOVED, s=20, linewidths=1.5,
                   zorder=7)
    if n:                # one site (a chain's cell) is a point: show its neighbours too
        low, high = xy.min(axis=0), xy.max(axis=0)
        half = np.maximum(high - low, MIN_SPAN) / 2
        ax.update_datalim([(low + high) / 2 - half, (low + high) / 2 + half])
    ax.set_aspect("equal", adjustable="datalim")
    ax.margins(0.15 if cells else 0.08)
    ax.autoscale_view()
    return selection


def is_flat(build):
    """Whether a geometry lies in a plane of constant z (drawn in 2D)."""
    r = np.asarray(build["positions"])
    return int(build["dimensionality"]) < 3 and (len(r) == 0 or float(np.ptp(r[:, 2])) < FLAT)


def on_a_line(build):
    """Whether the sites lie on the x axis direction, with one y and one z
    (a chain): values on them read better as a curve against x."""
    r = np.asarray(build["positions"])
    return len(r) > 1 and float(np.ptp(r[:, 1])) < FLAT and float(np.ptp(r[:, 2])) < FLAT


def bond_segments_3d(build):
    """Segments (K, 2, 3) of the bonds touching the central cell."""
    r = np.asarray(build["positions"], dtype=float)
    lattice = np.asarray(build["lattice"], dtype=float)
    segments = [np.stack([r[i], r[j]]) for i, j in build["bonds"]]
    for i, j, *cell in build["image_bonds"]:
        shift = np.asarray(cell) @ lattice
        segments.append(np.stack([r[i], r[j] + shift]))
        segments.append(np.stack([r[j], r[i] - shift]))
    return np.array(segments).reshape(-1, 2, 3)


def cell_edges_3d(build):
    """Edges (E, 2, 3) of the unit cell: a parallelogram for a 2D lattice,
    a parallelepiped for a 3D one, none otherwise."""
    dimensionality = int(build["dimensionality"])
    if dimensionality < 2:
        return np.zeros((0, 2, 3))
    lattice = np.asarray(build["lattice"], dtype=float)[:dimensionality]
    r = np.asarray(build["positions"], dtype=float).reshape(-1, 3)
    centre = r.mean(axis=0) if len(r) else np.zeros(3)      # every site removed
    corner = centre - lattice.sum(axis=0) / 2
    codes = list(itertools.product((0, 1), repeat=dimensionality))
    corners = [corner + np.array(c) @ lattice for c in codes]
    return np.array([[corners[a], corners[b]] for a in range(len(codes))
                     for b in range(a + 1, len(codes))
                     if sum(x != y for x, y in zip(codes[a], codes[b])) == 1])


def draw_structure_3d(ax, build, highlight=None, selected=None, removed=None, images=True,
                      site_values=None, arrows=None, hoppings=None, atom_size=1.0, bonds=True):
    """draw_structure for a geometry that is not flat, on an mplot3d Axes
    (atom_size scales the area of the points, which is in points squared);
    returns the scatter of the selected sites (its _offsets3d moves them)."""
    r = np.asarray(build["positions"], dtype=float).reshape(-1, 3)
    n = len(r)
    size = float(np.clip(4000 / max(n, 1), 12, 120)) * float(atom_size) ** 2
    colors = site_colors(build)
    if site_values is not None:
        symmetric = site_values.get("symmetric", True)
        colors, mappable = value_colors(site_values["values"], symmetric=symmetric,
                                        cmap=value_map(site_values))
        if varies(site_values["values"]):
            colorbar(ax, mappable, site_values.get("label", ""), shrink=0.6)
    if hoppings is not None:
        rows = np.asarray(hoppings["hoppings"]).reshape(-1, 5)
        lattice = np.asarray(build["lattice"], dtype=float)
        shift = rows[:, 2:5] @ lattice if len(rows) else np.zeros((0, 3))
        segments = np.stack([r[rows[:, 0]], r[rows[:, 1]] + shift], axis=1) if len(rows) \
            else np.zeros((0, 2, 3))
        amplitude = np.asarray(hoppings["amplitude"])
        top = float(amplitude.max()) if len(amplitude) else 1.0
        widths = 0.4 + 3.6 * amplitude / (top if top > 0 else 1.0)
        phase_map = cm.ScalarMappable(norm=mcolors.Normalize(-np.pi, np.pi),
                                      cmap=theme.PHASE_MAP)
        bond_colors = phase_map.to_rgba(np.asarray(hoppings["phase"]))
    else:
        segments = bond_segments_3d(build) if bonds else np.zeros((0, 2, 3))
        widths, bond_colors = 1.2, theme.BOND
    if len(segments):
        ax.add_collection3d(Line3DCollection(segments, colors=bond_colors, linewidths=widths))
    if images and 0 < n <= IMAGE_LIMIT // 4 and int(build["dimensionality"]):
        lattice = np.asarray(build["lattice"], dtype=float)
        ghosts = np.concatenate([r + c @ lattice for c in image_cells(build["dimensionality"])])
        ax.scatter(ghosts[:, 0], ghosts[:, 1], ghosts[:, 2], s=size * 0.5, c=theme.MUTED,
                   alpha=0.15, depthshade=False, linewidths=0)
    ax.scatter(r[:, 0], r[:, 1], r[:, 2], s=size, c=colors, edgecolors=atom_edge(site_values),
               linewidths=0.4, depthshade=True)
    edges = cell_edges_3d(build)
    if len(edges):
        ax.add_collection3d(Line3DCollection(edges, colors=theme.CELL, linestyles="--",
                                             linewidths=0.8))
    if arrows is not None:
        vectors = np.asarray(arrows["vectors"], dtype=float).reshape(-1, 3)
        shown = finite_vectors(vectors)
        lengths = np.linalg.norm(vectors[shown], axis=1)
        longest = float(lengths.max()) if len(lengths) else 0.0
        if longest > 1e-12:
            length, width, color, _ = arrow_style(arrows)
            v, at = vectors[shown] * (0.8 * length / longest), r[shown]
            ax.quiver(at[:, 0] - v[:, 0] / 2, at[:, 1] - v[:, 1] / 2, at[:, 2] - v[:, 2] / 2,
                      v[:, 0], v[:, 1], v[:, 2], color=color, linewidth=1.2 * width,
                      arrow_length_ratio=0.3)
    if highlight is not None and np.any(highlight):
        h = r[np.asarray(highlight, dtype=bool)]
        ax.scatter(h[:, 0], h[:, 1], h[:, 2], s=size * 2.2, facecolors="none",
                   edgecolors=theme.REGION, linewidths=1.8, depthshade=False)
    if removed is not None and len(removed):
        p = np.asarray(removed, dtype=float).reshape(-1, 3)
        ax.scatter(p[:, 0], p[:, 1], p[:, 2], marker="x", c=theme.REMOVED, s=30,
                   depthshade=False)
    idx = np.asarray(selected if selected is not None else [], dtype=int)
    chosen = r[idx].reshape(-1, 3)
    selection = ax.scatter(chosen[:, 0], chosen[:, 1], chosen[:, 2], s=size * 1.8,
                           facecolors="none", edgecolors=theme.SELECTED, linewidths=2.0,
                           depthshade=False)
    points = np.concatenate([r, edges.reshape(-1, 3)]) if len(edges) else r
    if len(points):
        low, high = points.min(axis=0), points.max(axis=0)
        span = np.maximum(high - low, 1.0)
        middle = (low + high) / 2
        for setter, m, w in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), middle, span):
            setter(m - 0.55 * w, m + 0.55 * w)
        ax.set_box_aspect(tuple(span))
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_zlabel("z")
    return selection


def _same(a, b):
    """Equality of overlay values (dicts, lists, numpy arrays, numbers)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return np.shape(a) == np.shape(b) and bool(np.array_equal(a, b))
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


class StructureView(QWidget):
    """A matplotlib canvas with its bar (ui/canvasbar.py: Fit, Pan, Zoom,
    the site-selection tools, what the canvas shows, Save image)."""

    selection_changed = Signal(int)          # number of selected sites
    paint_stroke = Signal(object, bool)      # indices under the brush, the stroke is over
    view_chosen = Signal(str)                # a key of VIEWS, chosen by the user
    projection_chosen = Signal(str)          # "xy" or "3d", chosen with the 3D box
    navigation_changed = Signal(bool)        # the toolbar's pan or zoom mode went on or off
    # the bar's selection controls; the window acts on them (its actions tool,
    # select_sites, region_from_selection, remove_selected, Calculate on selection's menu)
    tool_chosen = Signal(str)                # a key of TOOLS
    select_requested = Signal(object)        # the arguments of select_sites
    region_requested = Signal()
    calculate_requested = Signal()
    remove_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("structureView")
        # constrained layout is redone at every draw, so the labels fit the size the canvas
        # has; the centring balances its margins after each one
        self.figure = Figure(figsize=(6, 5), dpi=100, layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setObjectName("structureCanvas")
        self.centring = theme.Centring(self.canvas, lambda: self.ax)
        # the bar (PLAN.md phase 8, package P3), over matplotlib's toolbar, hidden, whose
        # modes its Pan and Zoom turn on
        self.bar = CanvasBar(self.canvas, "structureBar", "structureToolbar", "structure{Key}",
                             fit=self.fit)
        self.toolbar = self.bar.toolbar
        for name, joined in (("tools", False), ("selection", True), ("view", False),
                             ("paint", True)):
            self.bar.group(name, joined=joined)
        self.tool_buttons = QButtonGroup(self)
        for tool, text, tip in (("pick", "Pick", "click an atom; shift adds, ctrl toggles"),
                                ("box", "Box", "drag a rectangle"),
                                ("lasso", "Lasso", "draw around the atoms")):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(f"select sites: {tip} ({shortcuts.text('tool_' + tool)} on "
                              f"the canvas)")
            button.setObjectName(f"tool_{tool}")
            button.setCheckable(True)
            button.setChecked(tool == "pick")
            button.clicked.connect(lambda checked=False, t=tool: self.tool_chosen.emit(t))
            self.tool_buttons.addButton(button)
            self.bar.add("tools", button, tool)
        self.select_button = QToolButton()
        self.select_button.setText("Select")
        self.select_button.setObjectName("selectSitesButton")
        self.select_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.select_button.setToolTip(
            f"select sites by rule (on the canvas: {shortcuts.text('select_all')} all, "
            f"{shortcuts.text('select_none')} nothing, {shortcuts.text('select_invert')} "
            f"invert)")
        menu = QMenu(self.select_button)
        for text, name, args in (("All", "selectAll", {"all": True}),
                                 ("Sublattice A", "selectSublatticeA", {"sublattice": 1}),
                                 ("Sublattice B", "selectSublatticeB", {"sublattice": -1}),
                                 ("Edge sites", "selectEdge", {"edge": True}),
                                 ("Invert", "selectInvert", {"all": True, "mode": "toggle"}),
                                 ("Nothing", "selectNone", {"indices": []})):
            action = menu.addAction(text)
            action.setObjectName(name)
            action.triggered.connect(
                lambda checked=False, a=args: self.select_requested.emit(dict(a)))
        self.select_button.setMenu(menu)
        self.bar.add("tools", self.select_button, "select")
        self.region_button = self._selection_button(
            "Region from selection", "regionFromSelectionButton",
            "a named region of the selected sites, which any term can be restricted to",
            self.region_requested, "region")
        self.calculate_button = self._selection_button(
            "Calculate on selection", "calculateOnSelectionButton",
            "what takes the selected sites: the density of states on them, and every "
            "calculation of sites", self.calculate_requested, "calculation")
        self.remove_button = self._selection_button(
            "Remove selected", "removeSelectedButton",
            f"remove the selected atoms (a Remove atoms op, by position; "
            f"{shortcuts.text('remove_selected')} on the canvas)", self.remove_requested,
            "remove")
        self.view_box = QComboBox()
        self.view_box.setObjectName("canvasView")
        self.view_box.setToolTip("what the canvas shows: the geometry, what the Hamiltonian "
                                 "puts on it, or the Field being edited")
        for key, text in VIEWS.items():
            self.view_box.addItem(text, key)
        self.view_box.activated.connect(
            lambda i: self.view_chosen.emit(self.view_box.itemData(i)))
        self.box_3d = QCheckBox("3D")
        self.box_3d.setObjectName("view3dBox")
        self.box_3d.setToolTip("draw the geometry in 3D (turn it with the middle button, or a drag "
                               "with matplotlib); a geometry that is "
                               "not flat is drawn in 3D unless this is unchecked. The site "
                               "selection tools work on the flat (xy) drawing")
        self.box_3d.clicked.connect(
            lambda checked: self.projection_chosen.emit("3d" if checked else "xy"))
        self.paint = QToolButton()
        self.paint.setText("Paint")
        self.paint.setObjectName("paintTool")
        self.paint.setCheckable(True)
        self.paint.setToolTip("paint the Field being previewed: the sites under the brush take "
                              "its value (the Field becomes a painted one)")
        self.brush_value = QLineEdit("1")
        self.brush_value.setObjectName("brushValue")
        self.brush_value.setToolTip("the value painted")
        self.brush_radius = QLineEdit("0.6")
        self.brush_radius.setObjectName("brushRadius")
        self.brush_radius.setToolTip("the radius of the brush")
        self.brush_component = QComboBox()
        self.brush_component.setObjectName("brushComponent")
        self.brush_component.setToolTip("the component painted, for a vector Field")
        for component, text in ((None, "—"), (0, "x"), (1, "y"), (2, "z")):
            self.brush_component.addItem(text, component)
        for widget in (self.brush_value, self.brush_radius):
            widget.setMaximumWidth(60)
        self.paint_widgets = (self.paint, QLabel("value"), self.brush_value, QLabel("radius"),
                              self.brush_radius, self.brush_component)
        show = QLabel("Show")
        show.setObjectName("canvasViewLabel")
        show.setToolTip("what the canvas shows, chosen beside")
        self.bar.add("view", show, "show")
        self.bar.add("view", self.view_box)
        self.bar.add("view", self.box_3d, "3d")
        for widget in self.paint_widgets:
            self.bar.add("paint", widget, "paint" if widget is self.paint else None)
        self.bar.groups["paint"].hide()          # the brush belongs to the Field preview
        self._painting = False
        self.caption = QLabel("No system yet: add one with New system, next to the "
                              "workspace tabs.")
        self.caption.setObjectName("structureCaption")
        self.caption.setWordWrap(True)
        self.caption.setMinimumHeight(3 * self.caption.fontMetrics().lineSpacing())
        from guiqula.ui.pyvista_view import SceneView     # it imports this module
        self.scene = SceneView("structureScene")          # pyvista loads at its first drawing
        self.bar.adopt_scene(self.scene)      # its Reset view, View and Save image, in the bar
        self.stack = QStackedWidget()
        self.stack.addWidget(self.canvas)
        self.stack.addWidget(self.scene)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.bar)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.caption)
        self.system_id = None
        self.build = None
        self.ax = None
        self.in_scene = False            # the geometry is drawn by pyvista (self.scene)
        self.projection = "auto"
        self.renderer_3d = "matplotlib"
        self.tool = "pick"
        self.selected_positions = np.zeros((0, 3))
        self._selection_artist = None
        self._selector = None
        self._press_key = None
        self._caption = ""
        self._drawn = self._overlays = None     # what the figure shows (show_structure)
        self._was_navigating = False
        # after the toolbar's mode changed (pan, zoom, or off again)
        self.bar.navigation_changed.connect(lambda navigating: self._check_navigation())
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_paint_motion)
        self.canvas.mpl_connect("button_release_event", self._on_paint_release)
        # Inkscape's controls: the wheel, the middle button, Space and the keys of "2D canvas"
        self.navigation = CanvasNavigation(
            self.canvas, lambda: self.ax, active=lambda: not self._is_3d(),
            fit=self._fit_2d, selection=self._selected_xy, on_hand=self._hand_changed)
        bind_keys(self.canvas, self.navigation.key_handlers())
        bind_keys(self.scene.canvas, self.scene.key_handlers())    # Blender's, in the scene

    def _selection_button(self, text, name, tooltip, signal, icon):
        """A control of the bar acting on the selected sites, enabled while
        some are selected (the window's _selection_changed)."""
        button = QToolButton()
        button.setText(text)
        button.setObjectName(name)
        button.setToolTip(tooltip)
        button.setEnabled(False)
        button.clicked.connect(lambda checked=False: signal.emit())
        self.bar.add("selection", button, icon)
        return button

    # ---- drawing
    def set_view(self, view):
        """Show which view is drawn (the window decides and redraws); the
        brush belongs to the Field preview."""
        self.bar.groups["paint"].setVisible(view == "field")
        if view != "field":
            self.paint.setChecked(False)
        index = self.view_box.findData(view)
        if index >= 0 and index != self.view_box.currentIndex():
            self.view_box.blockSignals(True)
            self.view_box.setCurrentIndex(index)
            self.view_box.blockSignals(False)

    def set_paintable(self, paintable):
        """Whether the brush can paint here: not when the Field previewed
        belongs to another system than the one drawn."""
        for widget in self.paint_widgets:
            widget.setEnabled(paintable)
        if not paintable:
            self.paint.setChecked(False)

    def set_projection(self, projection):
        """auto (3D when the geometry is not flat), xy or 3d; the window
        redraws."""
        if projection not in PROJECTIONS:
            raise ValueError(f"unknown projection {projection!r}; projections: "
                             f"{list(PROJECTIONS)}")
        self.projection = projection
        return projection

    def set_renderer_3d(self, renderer):
        """What draws in 3D: matplotlib (mplot3d) or pyvista; the window
        redraws."""
        from guiqula.ui.pyvista_view import RENDERERS
        if renderer not in RENDERERS:
            raise ValueError(f"unknown 3D drawing {renderer!r}; choices: {list(RENDERERS)}")
        self.renderer_3d = renderer
        return renderer

    def in_3d(self, build=None):
        """Whether a build is drawn in 3D with the current projection."""
        build = build if build is not None else self.build
        if self.projection != "auto":
            return self.projection == "3d"
        return build is not None and not is_flat(build)

    def show_structure(self, system_id, build, caption="", **overlays):
        """Redraw; keeps the zoom (or the 3D viewing angle) when the same
        geometry is shown again, and the selection when its sites are
        still there. Drawn in the active theme. When nothing drawn changed
        (an edit whose rebuild is on its way: only the caption says
        "updating…"), only the caption is updated."""
        drawing = (system_id, id(build), self.in_3d(build), self.renderer_3d, theme.name,
                   theme.text_size)
        if (self.ax is not None or self.in_scene) and drawing == self._drawn and \
                _same(overlays, self._overlays):
            self._caption = caption
            self._update_selection()
            return
        with theme.drawing(self.figure):
            self._show_structure(system_id, build, caption, **overlays)
        self._drawn, self._overlays = drawing, overlays

    def _show_structure(self, system_id, build, caption, **overlays):
        three_d = self.in_3d(build)
        was_3d = self.ax is not None and getattr(self.ax, "name", "") == "3d"
        was_scene = self.in_scene and system_id == self.system_id and self.build is not None
        limits = angles = None
        if self.ax is not None and system_id == self.system_id and self.build is not None:
            if was_3d and three_d:
                angles = (self.ax.elev, self.ax.azim)
            elif not was_3d and not three_d:
                limits = (self.ax.get_xlim(), self.ax.get_ylim())
        # the same geometry: the same positions (a Shift or a strain moves every site of a
        # flake without changing their number, and the kept view showed none of them)
        same_sites = self.build is not None and build is not None and \
            np.shape(self.build["positions"]) == np.shape(build["positions"]) and \
            np.allclose(self.build["positions"], build["positions"], rtol=0.0, atol=SAME_SITE)
        if system_id != self.system_id:
            self.selected_positions = np.zeros((0, 3))
        if system_id != self.system_id or not same_sites:
            self.navigation.history.clear()      # the earlier zooms belong to another drawing
        self.system_id, self.build = system_id, build
        self.box_3d.setChecked(three_d)
        self.figure.clear()
        self.bar.reset_history()             # matplotlib's remembered views had the old axes
        note = ""
        if three_d and self.renderer_3d == "pyvista":
            try:
                # the camera stays for the same system, and fits again when the sites changed
                self.scene.show_scene(build, keep=was_scene, fit=not same_sites,
                                      selected=self.selected(), **overlays)
            except Exception as error:
                self.scene.forget()
                note = f"drawn with matplotlib: pyvista could not draw ({error})"
            else:
                self._show_canvas(False)
                self.ax = self._selection_artist = None
                self._caption = caption
                self._install_tool()
                self._update_selection()
                return
        self._show_canvas(True)
        caption = " · ".join(filter(None, [caption, note]))
        if three_d:
            self.ax = self.figure.add_subplot(111, projection="3d")
            self._selection_artist = draw_structure_3d(self.ax, build, selected=self.selected(),
                                                       **overlays)
            if angles is not None:
                self.ax.view_init(*angles)
            self._caption = caption
            self._install_tool()
            self._update_selection()
            return
        self.ax = self.figure.add_subplot(111)
        self._selection_artist = draw_structure(self.ax, build, selected=self.selected(),
                                                **overlays)
        if limits is not None and same_sites:
            self.ax.get_xlim()               # settle the autoscaling of the new artists first
            self.ax.set_xlim(*limits[0])
            self.ax.set_ylim(*limits[1])
            self.ax.set_autoscale_on(True)   # the equal aspect may widen one of them
        self._caption = caption
        self._install_tool()
        self._update_selection()

    def _show_canvas(self, canvas):
        """The matplotlib canvas and its Fit, Pan, Zoom and Save image, or
        pyvista's scene and its Reset view, View and Save image."""
        self.in_scene = not canvas
        self.stack.setCurrentWidget(self.canvas if canvas else self.scene)
        self.bar.show_scene(not canvas)
        if not canvas:
            self.stop_navigating()

    def clear(self, caption=""):
        self._drawn, self._overlays = None, None
        self.navigation.history.clear()
        self.scene.forget()
        self._show_canvas(True)
        self.system_id, self.build, self.ax = None, None, None
        self._selector = self._selection_artist = None
        self.selected_positions = np.zeros((0, 3))
        self.figure.clear()
        self.bar.reset_history()
        theme.set_figure(self.figure)
        self._caption = caption
        self.caption.setText(caption)
        self.canvas.draw_idle()
        self.selection_changed.emit(0)

    # ---- selection
    def selected(self):
        """Indices of the selected sites in the geometry shown."""
        if self.build is None:
            return np.zeros(0, dtype=int)
        return match_positions(self.build["positions"], self.selected_positions)

    def select(self, indices, mode="replace"):
        """Apply a selection gesture (MODES) with site indices; returns the
        number of selected sites."""
        if self.build is None:
            raise ValueError("there is no geometry to select from")
        indices = combine(self.selected(), indices, mode)
        self.selected_positions = np.asarray(self.build["positions"])[indices].reshape(-1, 3)
        self._update_selection()
        return len(indices)

    def _update_selection(self):
        indices = self.selected()
        if self.in_scene and self.build is not None:
            self.scene.set_selection(np.asarray(self.build["positions"])[indices].reshape(-1, 3))
        elif self._selection_artist is not None and self.build is not None:
            chosen = np.asarray(self.build["positions"])[indices].reshape(-1, 3)
            if hasattr(self._selection_artist, "_offsets3d"):
                self._selection_artist._offsets3d = (chosen[:, 0], chosen[:, 1], chosen[:, 2])
            else:
                self._selection_artist.set_offsets(chosen[:, :2])
        n = len(indices)
        text = self._caption + (f" · {n} selected" if n else "")
        self.caption.setText(text)
        self.canvas.draw_idle()
        self.selection_changed.emit(n)

    # ---- tools
    def set_tool(self, tool):
        """Choose a selection tool; it also turns off the toolbar's pan or
        zoom mode, which would keep taking the clicks."""
        if tool not in TOOLS:
            raise ValueError(f"unknown tool {tool!r}; tools: {list(TOOLS)}")
        self.stop_navigating()
        self.tool = tool
        self._install_tool()
        self._show_tool()
        return tool

    def _show_tool(self):
        """The tool in use checked on the bar; none while Pan or Zoom takes
        the clicks."""
        navigating = self._navigating()
        self.tool_buttons.setExclusive(False)
        for button in self.tool_buttons.buttons():
            button.setChecked(not navigating and button.objectName() == f"tool_{self.tool}")
        self.tool_buttons.setExclusive(True)

    def stop_navigating(self):
        """Turn off the toolbar's pan or zoom mode: matplotlib keeps it on
        until its button is clicked again, and meanwhile no click selects."""
        self.bar.stop_navigating()
        self._check_navigation()

    def _check_navigation(self):
        navigating = self._navigating()
        if navigating != self._was_navigating:
            self._was_navigating = navigating
            self._show_tool()
            self.navigation_changed.emit(navigating)

    def _install_tool(self):
        if self._selector is not None:
            self._selector.set_active(False)
            self._selector = None
        if self.ax is None or self._is_3d():              # the tools work in xy
            return
        props = {"color": theme.SELECTED, "linewidth": 1.5}
        if self.tool == "box":
            # shift and ctrl add and toggle (_mode), so they must not make matplotlib's box
            # square or centred on the press
            self._selector = RectangleSelector(
                self.ax, self._on_box, useblit=False, button=[1], interactive=False,
                props={"edgecolor": theme.SELECTED, "fill": False, "linewidth": 1.5},
                state_modifier_keys={"square": "not-applicable", "center": "not-applicable"})
        elif self.tool == "lasso":
            self._selector = LassoSelector(self.ax, self._on_lasso, useblit=False, button=[1],
                                           props=props)

    def _is_3d(self):
        return self.in_scene or getattr(self.ax, "name", "") == "3d"

    def _navigating(self):
        return self.bar.navigating()

    @staticmethod
    def _mode(key):
        key = key or ""
        if "shift" in key:
            return "add"
        if "control" in key or "ctrl" in key:
            return "toggle"
        return "replace"

    # ---- the brush (the Field preview)
    def brush(self):
        """(value, radius, component) of the brush; ValueError when the value
        or the radius typed is not a number (it used to paint 1.0 then)."""
        def number(edit, what):
            try:
                return float(edit.text())
            except ValueError:
                raise ValueError(f"the brush {what} {edit.text()!r} is not a number") from None
        return (number(self.brush_value, "value"), number(self.brush_radius, "radius"),
                self.brush_component.currentData())

    def under_brush(self, x, y):
        """Indices of the sites within the brush's radius of (x, y)."""
        if self.build is None:
            return []
        xy = np.asarray(self.build["positions"])[:, :2]
        return [int(i) for i in np.nonzero(np.hypot(xy[:, 0] - x, xy[:, 1] - y)
                                           <= self.brush()[1])[0]]

    def _on_paint_motion(self, event):
        if self._painting and event.inaxes is self.ax and event.xdata is not None:
            self.paint_stroke.emit(self.under_brush(event.xdata, event.ydata), False)

    def _on_paint_release(self, event):
        if self._painting:
            self._painting = False
            self.paint_stroke.emit([], True)

    def _on_press(self, event):
        self._press_key = event.key          # the lasso's modifier (_on_lasso gets no event)
        if self.navigation.hand or event.button == 2:      # Space or the middle button drags
            return
        if self.paint.isChecked() and self.paint.isVisible() and self.build is not None \
                and event.inaxes is self.ax and event.button == 1 and not self._navigating() \
                and not self._is_3d():
            try:
                self.brush()
            except ValueError:        # a stroke that paints nothing; the window says why
                self.paint_stroke.emit([], True)
                return
            self._painting = True
            self.paint_stroke.emit(self.under_brush(event.xdata, event.ydata), False)
            return
        if self.tool != "pick" or self.build is None or event.inaxes is not self.ax \
                or event.button != 1 or self._navigating() or self._is_3d():
            return
        i = nearest_index(self.build["positions"], event.xdata, event.ydata)
        mode = self._mode(event.key)
        if i is None:
            if mode == "replace":
                self.select([], "replace")
            return
        self.select([i], mode)

    def _on_box(self, press, release):
        if self.build is None or self._navigating():
            return
        indices = indices_in_box(self.build["positions"], press.xdata, press.ydata,
                                 release.xdata, release.ydata)
        self.select(indices, self._mode(release.key))

    def _on_lasso(self, vertices):
        if self.build is None or self._navigating():
            return
        self.select(indices_in_polygon(self.build["positions"], vertices),
                    self._mode(self._press_key))

    def fit(self):
        """Show the whole geometry again (after zooming or panning)."""
        if self.in_scene:
            self.scene.fit()
            return
        if self.ax is None:
            return
        if self._is_3d():
            self.ax.autoscale_view()
            self.canvas.draw_idle()
        else:
            self.navigation.zoom_drawing()

    def _fit_2d(self):
        self.ax.set_autoscale_on(True)
        self.ax.autoscale_view()
        self.canvas.draw_idle()

    def _selected_xy(self):
        """The selected sites in the xy drawing (the zoom to the selection)."""
        return self.selected_positions[:, :2] if len(self.selected_positions) else None

    def _hand_changed(self, hand):
        """Space held: the left button drags the drawing, so the box and
        lasso stand aside."""
        if self._selector is not None:
            self._selector.set_active(not hand)
