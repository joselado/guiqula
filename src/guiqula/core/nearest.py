"""The stored point nearest to a position, within a tolerance, without
scanning all of them (PLAN.md phase 5, part 3). Regions by positions,
painted and from_result Fields and the canvas selection all ask this; a
scan of every stored point per site made them quadratic (a selection of
20,000 sites took 26 s, a painted Field of 20,000 sites 12 s per edit).

The points are hashed by cells of the size of the tolerance, so a point
within the tolerance of a position lies in the position's cell or one of
the 26 around it. nearest_site() is the lookup one position at a time
(what pyqula calls, one site after another; exported scripts define this
same function, so it uses nothing but Python); nearest_indices() does many
positions at once with numpy (previews, selections, regions).
"""
import numpy as np


def nearest_site(points, tol):
    """A function of a position r: the index of the point (rows of points,
    [x, y, z, ...]) nearest to r and closer than tol, or -1 (ties: the
    lowest index)."""
    points = [(float(p[0]), float(p[1]), float(p[2])) for p in points]
    cells = {}
    for i, (x, y, z) in enumerate(points):
        cells.setdefault((int(x // tol), int(y // tol), int(z // tol)), []).append(i)
    reach = (-1, 0, 1)

    def find(r):
        x, y, z = float(r[0]), float(r[1]), float(r[2])
        cx, cy, cz = int(x // tol), int(y // tol), int(z // tol)
        best, best_d = -1, tol * tol
        for dx in reach:
            for dy in reach:
                for dz in reach:
                    for i in cells.get((cx + dx, cy + dy, cz + dz), ()):
                        p = points[i]
                        d = (p[0] - x) ** 2 + (p[1] - y) ** 2 + (p[2] - z) ** 2
                        if d < best_d or (d == best_d and i < best):
                            best, best_d = i, d
        return best
    return find


def nearest_indices(points, positions, tol):
    """For each of positions (M, 3), the index of the nearest of points
    (N, 3 or more columns) closer than tol, or -1: nearest_site for many
    positions at once."""
    points = np.asarray(points, dtype=float).reshape(len(points), -1)[:, :3] if len(points) \
        else np.zeros((0, 3))
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    out = np.full(len(positions), -1, dtype=np.int64)
    if not len(points) or not len(positions):
        return out
    low = np.minimum(points.min(axis=0), positions.min(axis=0))
    extent = float(np.max(np.maximum(points.max(axis=0), positions.max(axis=0)) - low))
    cell = max(tol, extent / 2.0 ** 20)          # at most 2**20 cells per axis: no overflow
    span = int(extent // cell) + 4

    def keys(cells):
        return ((cells[:, 0] + 1) * span + cells[:, 1] + 1) * span + cells[:, 2] + 1

    point_cells = np.floor((points - low) / cell).astype(np.int64)
    point_keys = keys(point_cells)
    order = np.argsort(point_keys, kind="stable")
    sorted_keys = point_keys[order]
    position_cells = np.floor((positions - low) / cell).astype(np.int64)
    rows, candidates = [], []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                wanted = keys(position_cells + np.array([dx, dy, dz]))
                start = np.searchsorted(sorted_keys, wanted, "left")
                stop = np.searchsorted(sorted_keys, wanted, "right")
                counts = stop - start
                hit = np.nonzero(counts)[0]
                if not len(hit):
                    continue
                counts = counts[hit]
                first = np.repeat(start[hit], counts)
                within = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
                rows.append(np.repeat(hit, counts))
                candidates.append(order[first + within])
    if not rows:
        return out
    rows, candidates = np.concatenate(rows), np.concatenate(candidates)
    d2 = np.sum((positions[rows] - points[candidates]) ** 2, axis=1)
    close = d2 < tol * tol
    rows, candidates, d2 = rows[close], candidates[close], d2[close]
    ranked = np.lexsort((candidates, d2, rows))           # per row: nearest, then lowest index
    rows, candidates = rows[ranked], candidates[ranked]
    first = np.unique(rows, return_index=True)[1]
    out[rows[first]] = candidates[first]
    return out
