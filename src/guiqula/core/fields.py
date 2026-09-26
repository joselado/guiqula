"""Fields: every numeric term parameter (PLAN.md 3.8).

A Field is stored in the Document as plain JSON:

- a number: ``constant``;
- a string: ``expression`` of position (guiqula.core.expressions);
- an object ``{"kind": ..., ...}`` for the other kinds.
  ``{"kind": "constant", "value": v}`` and ``{"kind": "expression",
  "expr": s}`` are stored in the short forms above;
- ``{"kind": "piecewise", "default": F, "pieces": [{"region": "r1",
  "value": F}, ...]}``: one value per region (13.2) plus a default for the
  sites in none of them, each value a constant or an expression. Where
  regions overlap, the later piece wins, as a later term does in the stack.
  A piecewise Field names regions by id; the pipeline resolves the ids to
  the regions' selections (which is what enters the stage key, never the
  ids) and hands the engine and the exporter a ``regions`` map {id:
  selection}. Profile, interpolated, painted and from_result are phase 4.

A vector Field is a list of three scalar Fields, one per component.

compile_* turn a Field into what pyqula takes (a number or a callable of one
position, ``f(r)`` with r = (x, y, z)); code_* give the same thing as Python
source for script export. Both live here so they cannot disagree.
"""
import math
import numbers

from guiqula.core import regions as region_tools
from guiqula.core.expressions import Expression, ExpressionError

LATER_KINDS = ("profile", "interpolated", "painted", "from_result")


class FieldError(ValueError):
    """The value is not a valid Field; the message says why."""


def normalize(value):
    """Return the canonical JSON form of a scalar Field, or raise FieldError."""
    if isinstance(value, dict) and value.get("kind") == "piecewise":
        return _normalize_piecewise(value)
    return _normalize_simple(value)


def _normalize_simple(value):
    """A constant or an expression."""
    if isinstance(value, bool):
        raise FieldError("a Field is a number or an expression, not a boolean")
    if isinstance(value, numbers.Real):
        value = float(value)
        if not math.isfinite(value):
            raise FieldError(f"{value} is not a finite number")
        return value
    if isinstance(value, str):
        try:
            expression = Expression(value)
        except ExpressionError as error:
            raise FieldError(str(error)) from None
        if not expression.depends_on_position():
            constant = expression(0.0, 0.0, 0.0)
            return normalize(float(constant))
        return expression.source
    if isinstance(value, dict):
        kind = value.get("kind")
        if kind == "constant" and set(value) == {"kind", "value"}:
            return _normalize_simple(value["value"])
        if kind == "expression" and set(value) == {"kind", "expr"}:
            return _normalize_simple(str(value["expr"]))
        if kind == "piecewise":
            raise FieldError("a piecewise Field cannot hold another piecewise Field")
        if kind in LATER_KINDS:
            raise FieldError(f"{kind} Fields are not implemented yet (PLAN.md 3.8)")
        raise FieldError(f"unknown Field {value!r}")
    raise FieldError(f"a Field is a number or an expression string, not {type(value).__name__}")


def _normalize_piecewise(value):
    extra = set(value) - {"kind", "default", "pieces"}
    if extra:
        raise FieldError(f"unknown keys {sorted(extra)} in a piecewise Field")
    pieces = value.get("pieces", [])
    if not isinstance(pieces, (list, tuple)):
        raise FieldError("the pieces of a piecewise Field are a list of {region, value}")
    out = []
    for piece in pieces:
        if not isinstance(piece, dict) or set(piece) != {"region", "value"}:
            raise FieldError("every piece of a piecewise Field is {\"region\": id, \"value\": v}")
        if not isinstance(piece["region"], str) or not piece["region"]:
            raise FieldError("a piece names its region by id")
        out.append({"region": piece["region"], "value": _normalize_simple(piece["value"])})
    return {"kind": "piecewise", "default": _normalize_simple(value.get("default", 0.0)),
            "pieces": out}


def normalize_vector(value, length=3):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise FieldError(f"a vector Field is a list of {length} Fields")
    return [normalize(v) for v in value]


def is_constant(value):
    return isinstance(value, float)


def kind_of(value):
    """constant, expression or piecewise (of a normalized scalar Field)."""
    if isinstance(value, dict):
        return value["kind"]
    return "constant" if isinstance(value, float) else "expression"


def regions_of(value):
    """Ids of the regions a Field refers to, in order, for any JSON value
    (a scalar Field, a vector of them, or anything else: none)."""
    if isinstance(value, dict) and value.get("kind") == "piecewise":
        return [p.get("region") for p in value.get("pieces", []) if isinstance(p, dict)]
    if isinstance(value, (list, tuple)):
        return [r for v in value for r in regions_of(v)]
    return []


def rename_regions(value, mapping):
    """The Field with its region ids replaced through mapping (a copy)."""
    if isinstance(value, dict) and value.get("kind") == "piecewise":
        return dict(value, pieces=[dict(p, region=mapping.get(p["region"], p["region"]))
                                   for p in value["pieces"]])
    if isinstance(value, list):
        return [rename_regions(v, mapping) for v in value]
    return value


def resolve_regions(value, regions):
    """The Field with each region id replaced by the region's selection:
    what a stage key hashes (decision 14.9, ids never enter keys)."""
    if isinstance(value, dict) and value.get("kind") == "piecewise":
        return dict(value, pieces=[{"region": regions[p["region"]], "value": p["value"]}
                                   for p in value["pieces"]])
    if isinstance(value, list):
        return [resolve_regions(v, regions) for v in value]
    return value


def _selection(regions, region_id):
    try:
        return regions[region_id]
    except (KeyError, TypeError):
        raise FieldError(f"region {region_id!r} does not exist") from None


def _compile_simple(value):
    return value if isinstance(value, float) else Expression(value).at


def _piecewise_function(value, regions):
    default = _compile_simple(value["default"])
    pieces = [(region_tools.compile_indicator(_selection(regions, p["region"])),
               _compile_simple(p["value"])) for p in value["pieces"]]

    def f(r):
        for inside, piece in reversed(pieces):       # the last piece wins
            if inside(r):
                return piece(r) if callable(piece) else piece
        return default(r) if callable(default) else default
    return f


def compile_scalar(value, weight=None, regions=None):
    """A number, or a callable f(position) for pyqula.

    weight: optional callable of position multiplying the Field (the
    indicator of a region); a constant then becomes a callable too.
    regions: {id: selection} for the regions a piecewise Field names.
    """
    value = normalize(value)
    if isinstance(value, float):
        if weight is None:
            return value
        return lambda r, c=value, w=weight: c * w(r)
    function = _piecewise_function(value, regions) if isinstance(value, dict) \
        else Expression(value).at
    if weight is None:
        return function
    return lambda r, f=function, w=weight: f(r) * w(r)


def compile_vector(value, weight=None, regions=None):
    return [compile_scalar(v, weight, regions) for v in normalize_vector(value)]


def _code_simple(value):
    return repr(value) if isinstance(value, float) else f"({Expression(value).to_python('r')})"


def _code_body(value, regions):
    """Python expression of r for a normalized non-constant Field."""
    if not isinstance(value, dict):
        return Expression(value).to_python("r")
    body = _code_simple(value["default"])
    for piece in value["pieces"]:                      # later pieces are tested first
        inside = region_tools.code_indicator(_selection(regions, piece["region"]))
        body = f"{_code_simple(piece['value'])} if {inside} else ({body})"
    return body


def code_scalar(value, weight_code=None, regions=None):
    """Python source equivalent to compile_scalar (numpy imported as np)."""
    value = normalize(value)
    if isinstance(value, float):
        if weight_code is None:
            return repr(value)
        return f"lambda r: {value!r} * ({weight_code})"
    body = _code_body(value, regions)
    if weight_code is None:
        return f"lambda r: {body}"
    return f"lambda r: ({body}) * ({weight_code})"


def code_vector(value, weight_code=None, regions=None):
    return "[" + ", ".join(code_scalar(v, weight_code, regions)
                           for v in normalize_vector(value)) + "]"


def _evaluate_simple(value, positions):
    import numpy as np
    if isinstance(value, float):
        return np.full(len(positions), value)
    return Expression(value).evaluate_positions(positions)


def evaluate_positions(value, positions, regions=None):
    """Evaluate a scalar Field on an (N, 3) array (canvas previews, tests)."""
    import numpy as np
    value = normalize(value)
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    if not isinstance(value, dict):
        return _evaluate_simple(value, positions)
    out = _evaluate_simple(value["default"], positions)
    for piece in value["pieces"]:
        inside = region_tools.evaluate_positions(_selection(regions, piece["region"]), positions)
        out[inside] = _evaluate_simple(piece["value"], positions)[inside]
    return out
