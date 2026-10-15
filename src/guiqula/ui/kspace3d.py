"""The Brillouin zone of a three-dimensional crystal, drawn in 3D (phase 9,
decision 236): the zone is the Wigner-Seitz cell of the reciprocal lattice
(kspace.brillouin_zone_3d), drawn with its high-symmetry points, pyqula's
default path and the k-path of the window, and turned with the mouse as the
3D structure is: by matplotlib's mplot3d (the left button rotates) or by
pyvista (ui/pyvista_view.py, Blender's controls), following View > 3D
drawing. A k-path leaving the plane k3 = 0, which the cut of the zone drew
projected, is drawn where it is.

A click (a press released where it started) near a high-symmetry point, or
near a vertex of the path, picks that point: Add points appends it to the
path by its label, otherwise the window offers what takes that k-point. A
click away from every point picks nothing, since a point of the screen is
a line through the zone. pyvista is imported at the first drawing only."""
import numpy as np

from guiqula.registry import kpaths
from guiqula.ui import theme

NAMES = {"G": "Γ"}
PICK_PIXELS = 12      # a click this close to a point picks it


def cartesian(reduced, reciprocal):
    """Cartesian k of reduced points (N, 3)."""
    return np.asarray(reduced, dtype=float).reshape(-1, 3) @ np.asarray(
        reciprocal, dtype=float).reshape(3, 3)


def special_points(kspace):
    """[(label, reduced, cartesian)] of the high-symmetry points, each at its
    image closest to the origin, once: pyqula lists some points under several
    labels (M, M1 and X), and the one shown is kpaths.point_name's (X in a
    cubic zone, M in a hexagonal one), a label pyqula knows."""
    b = kspace["reciprocal"]
    found = []                      # [labels, reduced, cartesian]
    for name, k in kspace["special"].items():
        reduced = kpaths.nearest_image(b, k, [0.0, 0.0, 0.0], 3)
        point = cartesian(reduced, b)[0]
        same = next((f for f in found if np.allclose(point, f[2], atol=1e-6)), None)
        if same is None:
            found.append([{name}, [float(c) for c in reduced], point])
        else:
            same[0].add(name)
    hexagonal = "K" in kspace["special"]
    out = []
    for labels, reduced, point in found:
        shown = kpaths.point_name(labels, hexagonal)
        label = "G" if shown == NAMES["G"] else shown if shown in labels else sorted(labels)[0]
        out.append((label, reduced, point))
    return out


def path_points(kpath, kspace):
    """Cartesian points of a normalized k-path's vertices (none for None)."""
    if not kpath:
        return np.zeros((0, 3))
    special = kspace["special"]
    reduced = kpaths.resolve(kspace["reciprocal"], 3, kpath, lambda name: special[name])
    return cartesian(reduced, kspace["reciprocal"])


def zone_edges(faces):
    """The edges of the zone, each once: [(start, end)] cartesian."""
    edges = []
    for face in faces:
        for a, b in zip(face, np.roll(face, -1, axis=0)):
            if not any((np.allclose(a, p) and np.allclose(b, q)) or
                       (np.allclose(a, q) and np.allclose(b, p)) for p, q in edges):
                edges.append((a, b))
    return edges


def bounds(faces):
    """(xmin, xmax, ymin, ymax, zmin, zmax) of the zone."""
    corners = np.concatenate(faces)
    low, high = corners.min(axis=0), corners.max(axis=0)
    return tuple(float(v) for pair in zip(low, high) for v in pair)


def nearest(points, screen, x, y):
    """The index of the point whose screen position (N, 2) is nearest to (x,
    y) within PICK_PIXELS, or None."""
    if not len(points):
        return None
    d = np.hypot(screen[:, 0] - x, screen[:, 1] - y)
    i = int(np.argmin(d))
    return i if d[i] <= PICK_PIXELS else None


def draw_mpl(ax, faces, special, default, path):
    """The zone on an mplot3d axes: its edges, its faces faintly filled, the
    points with their names, the default path dashed and the path."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    ax.add_collection3d(Poly3DCollection(faces, facecolor=theme.CELL, alpha=0.06,
                                         edgecolor="none"))
    for a, b in zone_edges(faces):
        ax.plot(*np.array([a, b]).T, color=theme.CELL, linewidth=1.2)
    if len(default):
        ax.plot(*default.T, "--", color=theme.MUTED, linewidth=1)
    for name, _, point in special:
        ax.scatter(*point, color=theme.POINT, s=14, depthshade=False)
        ax.text(*point, " " + NAMES.get(name, name), fontsize="small")
    line, = ax.plot(*(path.T if len(path) else np.zeros((3, 0))), "-o", color=theme.SELECTED,
                    linewidth=2, markersize=5)
    xmin, xmax, ymin, ymax, zmin, zmax = bounds(faces)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_zlim(zmin, zmax)
    ax.set_box_aspect((xmax - xmin, ymax - ymin, zmax - zmin))
    ax.set_xlabel("kx")
    ax.set_ylabel("ky")
    ax.set_zlabel("kz")
    return line


def screen_mpl(ax, points):
    """Display pixels (N, 2) of cartesian points on an mplot3d axes, with
    the origin at the bottom left as matplotlib's events have it."""
    from mpl_toolkits.mplot3d import proj3d
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if not len(points):
        return np.zeros((0, 2))
    x, y, _ = proj3d.proj_transform(points[:, 0], points[:, 1], points[:, 2], ax.get_proj())
    return ax.transData.transform(np.column_stack([x, y]))


def draw_pyvista(plotter, faces, special, default, path, pixel_ratio=1.0):
    """The same with pyvista; returns the bounds the camera fits."""
    import pyvista as pv
    from guiqula.ui import pyvista_view
    plotter.clear()
    plotter.set_background(theme.AXES)
    corners = np.concatenate(faces)
    cells, start = [], 0
    for face in faces:
        cells += [len(face)] + list(range(start, start + len(face)))
        start += len(face)
    plotter.add_mesh(pv.PolyData(corners, faces=np.array(cells)), color=theme.CELL,
                     opacity=0.08, name="zoneFaces")
    plotter.add_mesh(pyvista_view._lines(pv, [p for edge in zone_edges(faces) for p in edge]),
                     color=theme.CELL, line_width=2 * pixel_ratio, name="zoneEdges")
    if len(default) > 1:
        segments = np.repeat(default, 2, axis=0)[1:-1]
        plotter.add_mesh(pyvista_view._lines(pv, segments), color=theme.MUTED,
                         line_width=1 * pixel_ratio, name="defaultPath")
    size = 0.02 * float(np.max(np.ptp(corners, axis=0)))
    if special:
        points = np.array([p for _, _, p in special])
        plotter.add_mesh(pyvista_view._spheres(pv, points, size), color=theme.POINT,
                         name="points")
        plotter.add_point_labels(points, [NAMES.get(n, n) for n, _, _ in special],
                                 font_size=int(12 * pixel_ratio), text_color=theme.TEXT,
                                 shape=None, show_points=False, always_visible=True,
                                 name="labels")
    if len(path):
        if len(path) > 1:
            plotter.add_mesh(pyvista_view._lines(pv, np.repeat(path, 2, axis=0)[1:-1]),
                             color=theme.SELECTED, line_width=3 * pixel_ratio, name="path")
        plotter.add_mesh(pyvista_view._spheres(pv, path, 1.4 * size), color=theme.SELECTED,
                         name="vertices")
    return bounds(faces)


def screen_pyvista(canvas, points):
    """Widget pixels (N, 2), origin at the top left, of cartesian points in a
    pyvista SceneCanvas as last drawn."""
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    renderer = canvas.plotter.renderer
    ratio = canvas.devicePixelRatioF()
    height = canvas.height()
    out = []
    for p in points:
        renderer.SetWorldPoint(float(p[0]), float(p[1]), float(p[2]), 1.0)
        renderer.WorldToDisplay()
        x, y, _ = renderer.GetDisplayPoint()
        out.append((x / ratio, height - y / ratio))
    return np.array(out).reshape(-1, 2)
