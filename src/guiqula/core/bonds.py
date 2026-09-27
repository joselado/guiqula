"""Fields known on the sites only, at the bonds (PLAN.md 3.8).

pyqula evaluates the Field of a bond term (Rashba, Haldane, Kane-Mele,
Kekule, a pairing, the hopping modulation) at the midpoint of every bond,
(r1 + r2)/2, with r1 a site of the cell and r2 a site of the cell or of a
neighbouring one. A painted or from_result Field, and a region by
positions (the region a term is restricted to, or a piece of a piecewise
Field), are known on the sites only: a midpoint is no site, so they gave
the default there, and a term restricted to a region made from a canvas
selection did nothing while its report said ok.

For such a parameter (``FieldParam(bond=True)``) the engine and the
exported script hand pyqula bond_field(f, g, rule) instead, which takes a
bond's value from the values of f at its two ends:

- ``"mean"``: their mean (painted and from_result Fields);
- ``"both"``: their minimum, the region's 1 when both ends are inside (a
  term restricted to a region acts on the bonds between its sites).

The ends of the bond through a midpoint are the nearest pair of sites (of
the cell, or of the cells around) symmetric about it. Where bonds share a
midpoint pyqula gives them one value, and the shortest of them decide (the
two diagonals of a square plaquette: its four corners). At a site itself
(an onsite element, which the hopping modulation and an s-wave pairing
have) the value is f's there.
"""


def bond_field(site, g, rule="mean", reach=2.1, far=6.0, tol=1e-6):
    """A function of a bond's midpoint for pyqula, from site, a function of
    a site's position: the mean of site at the bond's two ends (rule
    "mean") or their minimum ("both"); at a site, site there. The bonds up
    to reach long (pyqula's terms reach second neighbours, whose squared
    length is below 4.1) are tabled at once; a longer one, up to far (a
    long hopping, between layers), is looked for when asked; a point that
    is no bond's midpoint gets site's value there. g: the geometry, whose
    sites and lattice vectors give the sites of the cells around (exported
    scripts define this same function)."""
    import numpy as np
    from scipy.spatial import cKDTree
    cell = np.array(g.r, dtype=float).reshape(-1, 3)
    if not len(cell):
        return site
    values = np.array([site(r) for r in cell], dtype=float)
    combine = np.mean if rule == "mean" else np.min
    lattice = np.array([g.a1, g.a2, g.a3], dtype=float)[:g.dimensionality]
    shifts = np.zeros((1, 3))
    if len(lattice):             # the cells that can hold an end of a bond of the cell
        extent = far + np.linalg.norm(cell.max(axis=0) - cell.min(axis=0))
        steps = np.ceil(extent * np.linalg.norm(np.linalg.pinv(lattice), axis=0)).astype(int)
        grid = np.meshgrid(*[np.arange(-n, n + 1) for n in steps], indexing="ij")
        shifts = np.stack([n.ravel() for n in grid], axis=1) @ lattice
    points = (cell[None, :, :] + shifts[:, None, :]).reshape(-1, 3)
    owner = np.tile(np.arange(len(cell)), len(shifts))
    in_cell = np.repeat(~shifts.any(axis=1), len(cell))
    near = np.all(np.abs(points - np.clip(points, cell.min(axis=0), cell.max(axis=0))) <= far,
                  axis=1)
    points, owner, in_cell = points[near], owner[near], in_cell[near]
    sites = cKDTree(points)

    def at_site(r):
        return bool(np.isfinite(sites.query(r, distance_upper_bound=tol)[0]))

    # the table: every pair (a site of the cell, a site within reach; a pair
    # inside the cell once), its midpoint unless a site is there, grouped by
    # midpoint, and the shortest pairs of each midpoint kept
    lists = sites.query_ball_point(cell, reach)
    first = np.repeat(np.arange(len(cell)), [len(found) for found in lists])
    second = np.array([k for found in lists for k in found], dtype=int)
    middle = (cell[first] + points[second]) / 2
    length = np.linalg.norm(points[second] - cell[first], axis=1)
    keep = (length > tol) & (~in_cell[second] | (first < owner[second]))
    keep &= ~np.isfinite(sites.query(middle, distance_upper_bound=tol)[0])
    first, second, middle, length = first[keep], second[keep], middle[keep], length[keep]
    keys, group = np.unique(np.round(middle / tol), axis=0, return_inverse=True)
    group = group.ravel()
    shortest = np.full(len(keys), np.inf)
    np.minimum.at(shortest, group, length)
    kept = length <= shortest[group] + tol
    ends = np.concatenate([values[first[kept]], values[owner[second[kept]]]])
    groups = np.concatenate([group[kept], group[kept]])
    if rule == "mean":
        table_values = np.bincount(groups, ends, len(keys)) / np.bincount(groups,
                                                                           minlength=len(keys))
    else:
        table_values = np.full(len(keys), np.inf)
        np.minimum.at(table_values, groups, ends)
    midpoints = np.zeros((len(keys), 3))
    midpoints[group] = middle
    table = cKDTree(midpoints) if len(keys) else None

    def longer(m):
        """The value of a bond longer than reach through m, or None."""
        found = np.array(sites.query_ball_point(m, far / 2), dtype=int)
        if not len(found):
            return None
        half = np.linalg.norm(points[found] - m, axis=1)
        distance, other = sites.query(2 * m - points[found], distance_upper_bound=tol)
        pair = np.isfinite(distance) & (half > tol)
        if not pair.any():
            return None
        best = pair & (half <= half[pair].min() + tol)
        return float(combine(np.concatenate([values[owner[found[best]]],
                                             values[owner[other[best]]]])))

    def f(r):
        m = np.array(r, dtype=float)
        if table is not None:
            distance, i = table.query(m, distance_upper_bound=tol)
            if np.isfinite(distance):
                return float(table_values[i])
        if not at_site(m):
            value = longer(m)
            if value is not None:
                return value
        return site(r)
    return f
