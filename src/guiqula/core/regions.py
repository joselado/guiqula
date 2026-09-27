"""Region selections (PLAN.md 13.2): which sites a region contains.

A region's ``select`` is JSON:

- ``{"kind": "expression", "expr": "x < -2"}``: sites where the expression
  (guiqula.core.expressions) is true, or nonzero;
- ``{"kind": "positions", "positions": [[x, y, z], ...], "tol": 0.05}``:
  sites within ``tol`` of one of the stored positions (positions survive
  upstream changes of the supercell, indices would not).

The structure canvas (phase 2) selects sites by click, box, lasso,
sublattice or edge (fewer neighbours than the rest) and stores the result
as a ``positions`` selection; a layer is an expression such as
``abs(z - 3) < 0.1``. Selections by rule that follow later changes of the
geometry (by sublattice, edge distance) would need the built geometry, not
just a position, and are not implemented. compile_indicator gives a
callable of one position returning 1.0 inside and 0.0 outside, which is
what restricting a Field to a region needs; code_indicator gives the same
as Python source for script export.
"""
import numpy as np

from guiqula.core.expressions import Expression, ExpressionError
from guiqula.core.nearest import nearest_indices, nearest_site


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
        try:
            positions = np.asarray(select.get("positions", []), dtype=float)
            tol = float(select.get("tol", 0.05))
        except (TypeError, ValueError):
            raise RegionError("positions must be a list of [x, y, z] and tol a number") from None
        if positions.ndim != 2 or positions.shape[1] != 3:
            raise RegionError("positions must be a list of [x, y, z]")
        if not np.isfinite(positions).all():
            raise RegionError("positions must be finite numbers")
        if not (np.isfinite(tol) and tol > 0):   # inf would not survive a save (JSON null)
            raise RegionError("tol must be a finite positive number")
        return {"kind": "positions", "positions": positions.tolist(), "tol": tol}
    raise RegionError(f"unknown selection kind {kind!r}; phase 1 has 'expression' and 'positions'")


def compile_indicator(select):
    select = normalize(select)
    if select["kind"] == "expression":
        expression = Expression(select["expr"])
        return lambda r, e=expression: float(bool(e.at(r)))
    if not select["positions"]:
        return lambda r: 0.0
    find = nearest_site(select["positions"], select["tol"])
    return lambda r: float(find(r) >= 0)


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
    return nearest_indices(select["positions"], positions.reshape(-1, 3), select["tol"]) >= 0
