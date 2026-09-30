"""k-paths through the Brillouin zone (decision 13.9): the vertices of a
KPathParam turned into the k-points a band structure walks, with the
index of every vertex on it (the ticks of the plot). The points between
two vertices are spread evenly, their number proportional to the length
of the segment in reciprocal space, as pyqula's own k2path does; the
function below is written out in exported scripts, so the script walks
the same points."""


def path_points(reciprocal, vertices, nk):
    """(k-points (M, 3), vertex indices) of a path through vertices (reduced
    coordinates), about nk points per reciprocal lattice vector of length."""
    import numpy as np
    b = np.asarray(reciprocal, dtype=float).reshape(3, 3)
    vertices = np.asarray(vertices, dtype=float).reshape(-1, 3)
    unit = float(np.linalg.norm(b[0]))
    points, ticks = [], []
    for start, end in zip(vertices[:-1], vertices[1:]):
        ticks.append(len(points))
        length = float(np.linalg.norm((end - start) @ b))
        steps = max(int(round(nk * length / unit)), 1)
        points += [start + (end - start) * s for s in np.linspace(0.0, 1.0, steps,
                                                                    endpoint=False)]
    ticks.append(len(points))
    points.append(vertices[-1])
    return np.array(points), np.array(ticks)


def nearest_image(reciprocal, point, previous, dimensionality):
    """The image of a reduced point (shifted by reciprocal lattice vectors
    along the periodic directions) closest to previous."""
    import itertools

    import numpy as np
    b = np.asarray(reciprocal, dtype=float).reshape(3, 3)
    point, previous = np.asarray(point, dtype=float), np.asarray(previous, dtype=float)
    shifts = itertools.product(*([(-1, 0, 1)] * dimensionality + [(0,)] * (3 - dimensionality)))
    images = [point + np.array(n) for n in shifts]
    # equivalent images at the same distance (the corners of a hexagonal
    # zone): the one nearest to the origin, then the first in a fixed order
    return min(images, key=lambda k: (round(float(np.linalg.norm((k - previous) @ b)), 9),
                                      round(float(np.linalg.norm(k @ b)), 9), tuple(k)))


def resolve(reciprocal, dimensionality, kpath, label2k):
    """Reduced coordinates of the vertices of a normalized k-path: a label
    (label2k gives it) names a class of equivalent points, and takes the
    image closest to the vertex before it (pyqula's k2path does the same);
    a point stays as it is."""
    out = []
    for vertex in kpath:
        if isinstance(vertex, str):
            point = [float(c) for c in label2k(vertex)]
            if out:
                point = list(nearest_image(reciprocal, point, out[-1], dimensionality))
            out.append(point)
        else:
            out.append([float(c) for c in vertex])
    return out


def vertices_of(g, kpath):
    """resolve() for a pyqula geometry (labels through kpointstk.labels)."""
    import numpy as np
    from pyqula.kpointstk import labels
    return resolve(np.array([g.b1, g.b2, g.b3]), g.dimensionality, kpath,
                   lambda name: labels.label2k(g, name))


NAMES = {"G": "Γ"}


def tick_names(reciprocal, dimensionality, kpath, special):
    """The name of every vertex, for the plot's ticks: its label, or the
    label of the high-symmetry point it is an image of (special: {label:
    reduced}), or its coordinates."""
    import numpy as np
    out = []
    for vertex in kpath:
        if isinstance(vertex, str):
            out.append(NAMES.get(vertex, vertex))
            continue
        name = None
        for label, point in special.items():
            image = nearest_image(reciprocal, point, vertex, dimensionality)
            if np.allclose(image, vertex, atol=1e-6):
                name = NAMES.get(label, label)
                break
        out.append(name or "(" + ", ".join(f"{c:.3g}" for c in vertex[:dimensionality]) + ")")
    return out


def point_name(labels, hexagonal):
    """The name of a point that pyqula lists under several labels: M, M1 and
    X are all (1/2, 0), M2 and Y are (0, 1/2), M3 is (1/2, 1/2). In a
    hexagonal zone (the one with a K) every one of them is an M point; in
    any other, (1/2, 0) is X, (0, 1/2) is Y and (1/2, 1/2) is M, as in the
    one and three dimensional paths pyqula walks by default."""
    if "G" in labels:
        return NAMES["G"]
    for name in ("K", "K'"):
        if name in labels:
            return name
    if hexagonal and labels & {"M", "M1", "M2", "M3"}:
        return "M"
    for name in ("X", "Y", "Z", "R", "A", "B"):
        if name in labels:
            return name
    return "M" if "M3" in labels else sorted(labels)[0]


def default_path(g, nk):
    """The k-points (reduced, (N, 3)) that the bands walk when no k-path is
    given: pyqula's default path, with the opening Gamma that its two
    dimensional path leaves out put before it (pyqula stores each point after
    the step, bm (i + 1) / nk, so its first point is one step after Gamma; the
    one and three dimensional paths start on Gamma). Every other point is
    pyqula's, unchanged. Empty for a finite system, which has no k."""
    import numpy as np
    if int(g.dimensionality) == 0:
        return np.zeros((0, 3))
    ks = np.asarray(g.get_kpath(None, nk=nk, write=False), dtype=float).reshape(-1, 3)
    if int(g.dimensionality) == 2:
        ks = np.vstack([np.zeros((1, 3)), ks])
    return ks


def default_ticks(reciprocal, dimensionality, points, special):
    """[[position, name], ...] of the high-symmetry points that a path
    through points (reduced, (N, 3), as default_path gives the default one)
    goes through: the position is the index along the path, fractional
    between two points, and the name is the one of point_name. special:
    {label: reduced}, as special_points gives."""
    import itertools

    import numpy as np
    b = np.asarray(reciprocal, dtype=float).reshape(3, 3)
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(points) < 2:
        return []
    cart = points @ b
    step = cart[1:] - cart[:-1]
    length2 = np.sum(step * step, axis=1)
    tolerance = 1e-6 * float(np.linalg.norm(b[0]))
    shifts = list(itertools.product(*([range(-2, 3)] * int(dimensionality)
                                      + [(0,)] * (3 - int(dimensionality)))))
    found = []
    for label, point in special.items():
        for shift in shifts:
            q = (np.asarray(point, dtype=float) + np.array(shift)) @ b
            t = np.sum((q - cart[:-1]) * step, axis=1) / np.where(length2 > 0, length2, 1.0)
            off = np.linalg.norm(q - (cart[:-1] + t[:, None] * step), axis=1)
            for i in np.flatnonzero((length2 > 0) & (off < tolerance) & (t >= -1e-6)
                                    & (t <= 1.0 + 1e-6)):
                found.append((float(i + t[i]), label))
    found.sort()
    grouped = []                       # what lies at one position is one point
    for position, label in found:
        if grouped and position - grouped[-1][0] < 1e-6:
            grouped[-1][1].add(label)
        else:
            grouped.append([position, {label}])
    hexagonal = "K" in special
    return [[position, point_name(labels, hexagonal)] for position, labels in grouped]


def special_points(g):
    """{label: reduced} of the high-symmetry points pyqula names for g."""
    import numpy as np
    from pyqula.kpointstk import labels
    out = {}
    for name in labels.get_label_names():
        try:
            k = np.asarray(labels.label2k(g, name), dtype=float).real
        except Exception:          # a label this lattice has no point for
            continue
        if np.all(np.abs(k[int(g.dimensionality):]) < 1e-9):     # in the periodic directions
            out[name] = [float(c) for c in k]
    return out


def script(kpath, nk):
    """Lines of an exported script that set ks and ticks for a k-path."""
    import inspect
    return [inspect.getsource(function).rstrip() + "\n"
            for function in (nearest_image, resolve, path_points)] + [
            "from pyqula.kpointstk import labels",
            f"vertices = resolve(np.array([g.b1, g.b2, g.b3]), g.dimensionality, {kpath!r}, "
            f"lambda name: labels.label2k(g, name))",
            f"ks, ticks = path_points(np.array([g.b1, g.b2, g.b3]), vertices, {nk!r})"]
