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
  selection}. Profile, interpolated and painted are phase 4, part 4.
- ``{"kind": "from_result", "calculation": "c2", "array":
  "magnetization", "component": 2, "scale": 1.0, "tol": 0.1}``: the value
  of an array of another calculation's result at the site nearest to the
  position (within tol, 0 elsewhere), times scale; component picks a
  column of an array with one row per site (a vector per site). The
  result must be drawn on the sites (it carries their positions) and
  belong to another system, so that a classical texture can be the
  exchange field of a quantum system (PLAN.md 3.8, section 5). What the
  keys hash is the key of the result read, never the calculation's id:
  running the source again makes the systems that read it stale. The
  engine and the exporter get the results as {calculation id:
  core.results.ResultRef}.

A vector Field is a list of three scalar Fields, one per component.

compile_* turn a Field into what pyqula takes (a number or a callable of one
position, ``f(r)`` with r = (x, y, z)); code_* give the same thing as Python
source for script export. Both live here so they cannot disagree.
"""
import math
import numbers

from guiqula.core import regions as region_tools
from guiqula.core.expressions import Expression, ExpressionError

LATER_KINDS = ("profile", "interpolated", "painted")
RESULT_KEYS = ("kind", "calculation", "array", "component", "scale", "tol")


class FieldError(ValueError):
    """The value is not a valid Field; the message says why."""


def normalize(value):
    """Return the canonical JSON form of a scalar Field, or raise FieldError."""
    if isinstance(value, dict) and value.get("kind") == "piecewise":
        return _normalize_piecewise(value)
    if isinstance(value, dict) and value.get("kind") == "from_result":
        return _normalize_result(value)
    return _normalize_simple(value)


def _normalize_result(value):
    extra = set(value) - set(RESULT_KEYS)
    if extra:
        raise FieldError(f"unknown keys {sorted(extra)} in a from_result Field")
    calculation, array = value.get("calculation"), value.get("array")
    if not isinstance(calculation, str) or not calculation:
        raise FieldError("a from_result Field names a calculation by id")
    if not isinstance(array, str) or not array:
        raise FieldError("a from_result Field names an array of the result")
    component = value.get("component")
    if component is not None and (isinstance(component, bool) or component not in (0, 1, 2)):
        raise FieldError("component is 0, 1, 2 (x, y, z) or null")
    try:
        scale, tol = float(value.get("scale", 1.0)), float(value.get("tol", 0.1))
    except (TypeError, ValueError):
        raise FieldError("scale and tol are numbers") from None
    if not math.isfinite(scale) or not tol > 0:
        raise FieldError("scale is a finite number and tol a positive one")
    return {"kind": "from_result", "calculation": calculation, "array": array,
            "component": component, "scale": scale, "tol": tol}


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
        if kind in ("piecewise", "from_result"):
            raise FieldError(f"a piecewise Field cannot hold a {kind} Field")
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


def results_of(value):
    """Ids of the calculations whose results a Field reads, for any JSON
    value (a Field, a vector of them, a dict of parameters)."""
    if isinstance(value, dict) and value.get("kind") == "from_result":
        return [value.get("calculation")]
    if isinstance(value, dict):
        return [c for v in value.values() for c in results_of(v)]
    if isinstance(value, (list, tuple)):
        return [c for v in value for c in results_of(v)]
    return []


def resolve_results(value, keys):
    """The Field with each calculation id replaced by the key of the result
    it reads: what a stage key hashes (decision 14.9)."""
    if isinstance(value, dict) and value.get("kind") == "from_result":
        return dict({k: v for k, v in value.items() if k != "calculation"},
                    result=keys[value["calculation"]])
    if isinstance(value, list):
        return [resolve_results(v, keys) for v in value]
    return value


def site_values(ref, array, component):
    """The values per site a from_result Field reads from a ResultRef."""
    import numpy as np
    if ref.positions is None:
        raise FieldError("the result is not drawn on the sites, it has no positions")
    if array not in ref.arrays:
        raise FieldError(f"the result has no array {array!r}; it has {sorted(ref.arrays)}")
    values = np.asarray(ref.arrays[array], dtype=float)
    n = len(ref.positions)
    if component is not None:
        if values.ndim != 2 or values.shape[0] != n or values.shape[1] <= component:
            raise FieldError(f"{array} has no component {component} per site")
        values = values[:, component]
    if values.shape != (n,):
        raise FieldError(f"{array} is not one number per site (shape {values.shape}); "
                         f"choose a component")
    return values


def site_field(positions, values, tol, scale=1.0):
    """A function of position: scale times the value of the site nearest to
    it, when that site is closer than tol, else 0 (a from_result Field;
    exported scripts define this same function)."""
    import numpy as np
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    values = np.asarray(values, dtype=float).reshape(-1)

    def f(r):
        d = np.linalg.norm(positions - np.asarray(r, dtype=float), axis=1)
        i = int(np.argmin(d))
        return scale * float(values[i]) if d[i] < tol else 0.0
    return f


def _result_function(value, results):
    if results is None or value["calculation"] not in results:
        raise FieldError(f"the result of {value['calculation']} is not available")
    ref = results[value["calculation"]]
    return site_field(ref.positions, site_values(ref, value["array"], value["component"]),
                      value["tol"], value["scale"])


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


def compile_scalar(value, weight=None, regions=None, results=None):
    """A number, or a callable f(position) for pyqula.

    weight: optional callable of position multiplying the Field (the
    indicator of a region); a constant then becomes a callable too.
    regions: {id: selection} for the regions a piecewise Field names;
    results: {calculation id: ResultRef} for the results it reads.
    """
    value = normalize(value)
    if isinstance(value, float):
        if weight is None:
            return value
        return lambda r, c=value, w=weight: c * w(r)
    if isinstance(value, dict) and value["kind"] == "from_result":
        function = _result_function(value, results)
    elif isinstance(value, dict):
        function = _piecewise_function(value, regions)
    else:
        function = Expression(value).at
    if weight is None:
        return function
    return lambda r, f=function, w=weight: f(r) * w(r)


def compile_vector(value, weight=None, regions=None, results=None):
    return [compile_scalar(v, weight, regions, results) for v in normalize_vector(value)]


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


def _code_result(value, results):
    """site_field(...) with the result's positions and values written out."""
    ref = results[value["calculation"]]
    values = site_values(ref, value["array"], value["component"])
    positions = [[float(c) for c in p] for p in ref.positions]
    return (f"site_field(np.array({positions!r}), np.array({[float(v) for v in values]!r}), "
            f"{value['tol']!r}, {value['scale']!r})")


def code_scalar(value, weight_code=None, regions=None, results=None):
    """Python source equivalent to compile_scalar (numpy imported as np;
    a from_result Field calls site_field, which the script defines)."""
    value = normalize(value)
    if isinstance(value, float):
        if weight_code is None:
            return repr(value)
        return f"lambda r: {value!r} * ({weight_code})"
    if isinstance(value, dict) and value["kind"] == "from_result":
        function = _code_result(value, results)
        if weight_code is None:
            return function
        return f"(lambda f: lambda r: f(r) * ({weight_code}))({function})"
    body = _code_body(value, regions)
    if weight_code is None:
        return f"lambda r: {body}"
    return f"lambda r: ({body}) * ({weight_code})"


def code_vector(value, weight_code=None, regions=None, results=None):
    return "[" + ", ".join(code_scalar(v, weight_code, regions, results)
                           for v in normalize_vector(value)) + "]"


def _evaluate_simple(value, positions):
    import numpy as np
    if isinstance(value, float):
        return np.full(len(positions), value)
    return Expression(value).evaluate_positions(positions)


def evaluate_positions(value, positions, regions=None, results=None):
    """Evaluate a scalar Field on an (N, 3) array (canvas previews, tests)."""
    import numpy as np
    value = normalize(value)
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    if not isinstance(value, dict):
        return _evaluate_simple(value, positions)
    if value["kind"] == "from_result":
        f = _result_function(value, results)
        return np.array([f(r) for r in positions], dtype=float)
    out = _evaluate_simple(value["default"], positions)
    for piece in value["pieces"]:
        inside = region_tools.evaluate_positions(_selection(regions, piece["region"]), positions)
        out[inside] = _evaluate_simple(piece["value"], positions)[inside]
    return out
