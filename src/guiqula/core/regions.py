"""Region selections (PLAN.md 13.2): which sites a region contains.

A region's ``select`` is JSON:

- ``{"kind": "expression", "expr": "x < -2"}``: sites where the expression
  (guiqula.core.expressions) is true, or nonzero;
- ``{"kind": "positions", "positions": [[x, y, z], ...], "tol": 0.05}``:
  sites within ``tol`` of one of the stored positions (positions survive
  upstream changes of the supercell, indices would not).

Selections by sublattice, layer or edge distance come with the canvas tools
in phase 2. compile_indicator gives a callable of one position returning 1.0
inside and 0.0 outside, which is what restricting a Field to a region needs;
code_indicator gives the same as Python source for script export.
"""
import numpy as np

from guiqula.core.expressions import Expression, ExpressionError


class RegionError(ValueError):
    pass


def normalize(select):
    if not isinstance(select, dict):
        raise RegionError("a region selection is an object with a 'kind'")
    kind = select.get("kind")
    if kind == "expression":
        if set(select) != {"kind", "expr"}:
            raise RegionError("an expression selection has exactly 'kind' and 'expr'")
        try:
            return {"kind": "expression", "expr": Expression(select["expr"]).source}
        except ExpressionError as error:
            raise RegionError(str(error)) from None
    if kind == "positions":
        extra = set(select) - {"kind", "positions", "tol"}
        if extra:
            raise RegionError(f"unknown keys {sorted(extra)} in a positions selection")
        positions = np.asarray(select.get("positions", []), dtype=float)
        if positions.ndim != 2 or positions.shape[1] != 3:
            raise RegionError("positions must be a list of [x, y, z]")
        tol = float(select.get("tol", 0.05))
        if not tol > 0:
            raise RegionError("tol must be positive")
        return {"kind": "positions", "positions": positions.tolist(), "tol": tol}
    raise RegionError(f"unknown selection kind {kind!r}; phase 1 has 'expression' and 'positions'")


def compile_indicator(select):
    select = normalize(select)
    if select["kind"] == "expression":
        expression = Expression(select["expr"])
        return lambda r, e=expression: float(bool(e.at(r)))
    points = np.array(select["positions"])
    tol = select["tol"]
    if len(points) == 0:
        return lambda r: 0.0
    return lambda r, p=points, t=tol: float(np.min(np.linalg.norm(p - np.asarray(r), axis=1)) < t)


def code_indicator(select):
    select = normalize(select)
    if select["kind"] == "expression":
        return f"float(bool({Expression(select['expr']).to_python('r')}))"
    if not select["positions"]:
        return "0.0"
    return (f"float(np.min(np.linalg.norm(np.array({select['positions']!r}) - np.asarray(r), "
            f"axis=1)) < {select['tol']!r})")


def evaluate_positions(select, positions):
    """Boolean mask of the sites of an (N, 3) array inside the region."""
    select = normalize(select)
    positions = np.asarray(positions, dtype=float)
    if select["kind"] == "expression":
        values = Expression(select["expr"]).evaluate_positions(positions)
        return values.astype(bool)
    points = np.array(select["positions"])
    if len(points) == 0:
        return np.zeros(len(positions), dtype=bool)
    distances = np.linalg.norm(positions[:, None, :] - points[None, :, :], axis=2)
    return distances.min(axis=1) < select["tol"]
