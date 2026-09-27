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
  selection}.
- ``{"kind": "profile", "name": "gaussian", "params": {...}}``: a named
  shape with its parameters (PROFILES: gaussian, step, disk, plane wave,
  Aubry-Andre, domain wall), which is an expression once its numbers are
  filled in, and compiles, exports and previews as one;
- ``{"kind": "interpolated", "points": [[x, y, value], ...], "length":
  2.0}``: control points, smoothed with Gaussian weights of that length
  (interpolated_field);
- ``{"kind": "painted", "sites": [[x, y, z, value], ...], "tol": 0.1,
  "default": 0.0}``: values painted on sites, by position, and the default
  elsewhere (painted_field; the structure canvas has a brush).
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
from guiqula.core.nearest import nearest_indices, nearest_site
from guiqula.core.expressions import Expression, ExpressionError

LATER_KINDS = ()
RESULT_KEYS = ("kind", "calculation", "array", "component", "scale", "tol")
# name: (parameters with their defaults, template); numbers go in parenthesized
PROFILES = {
    "gaussian": ({"amplitude": 1.0, "x0": 0.0, "y0": 0.0, "width": 2.0},
                 "{amplitude}*exp(-((x - {x0})**2 + (y - {y0})**2)/(2*{width}**2))"),
    "step": ({"amplitude": 1.0, "position": 0.0, "angle": 0.0, "smoothing": 0.5},
             "{amplitude}*0.5*(1 + tanh((x*cos({angle}) + y*sin({angle}) - {position})"
             "/{smoothing}))"),
    "disk": ({"amplitude": 1.0, "x0": 0.0, "y0": 0.0, "radius": 5.0, "smoothing": 0.5},
             "{amplitude}*0.5*(1 - tanh((sqrt((x - {x0})**2 + (y - {y0})**2) - {radius})"
             "/{smoothing}))"),
    "plane_wave": ({"amplitude": 1.0, "kx": 1.0, "ky": 0.0, "phase": 0.0},
                   "{amplitude}*cos({kx}*x + {ky}*y + {phase})"),
    "aubry_andre": ({"strength": 2.0, "beta": 0.6180339887, "phase": 0.0},
                    "{strength}*cos(2*pi*{beta}*x + {phase})"),
    "domain_wall": ({"amplitude": 1.0, "position": 0.0, "width": 2.0},
                    "{amplitude}*tanh((x - {position})/{width})"),
}
POSITIVE = {"width", "smoothing", "radius"}     # profile parameters that must be positive


class FieldError(ValueError):
    """The value is not a valid Field; the message says why."""


def normalize(value):
    """Return the canonical JSON form of a scalar Field, or raise FieldError."""
    if isinstance(value, dict) and value.get("kind") == "piecewise":
        return _normalize_piecewise(value)
    if isinstance(value, dict) and value.get("kind") == "from_result":
        return _normalize_result(value)
    if isinstance(value, dict) and value.get("kind") in NORMALIZERS:
        return NORMALIZERS[value["kind"]](value)
    return _normalize_simple(value)


def _finite(what, value):
    if isinstance(value, bool) or not isinstance(value, numbers.Real) or \
            not math.isfinite(float(value)):
        raise FieldError(f"{what} must be a finite number, not {value!r}")
    return float(value)


def _normalize_profile(value):
    extra = set(value) - {"kind", "name", "params"}
    if extra:
        raise FieldError(f"unknown keys {sorted(extra)} in a profile Field")
    name = value.get("name")
    if name not in PROFILES:
        raise FieldError(f"unknown profile {name!r}; profiles: {sorted(PROFILES)}")
    defaults = PROFILES[name][0]
    given = value.get("params") or {}
    unknown = set(given) - set(defaults)
    if unknown:
        raise FieldError(f"the {name} profile has no {sorted(unknown)}; it has {list(defaults)}")
    params = {}
    for key, default in defaults.items():
        params[key] = _finite(f"{name} {key}", given.get(key, default))
        if key in POSITIVE and not params[key] > 0:
            raise FieldError(f"{name} {key} must be positive")
    return {"kind": "profile", "name": name, "params": params}


def profile_expression(value):
    """The expression a normalized profile Field stands for."""
    template = PROFILES[value["name"]][1]
    return Expression(template.format(**{k: f"({v!r})" for k, v in
                                         value["params"].items()})).source


def _normalize_interpolated(value):
    extra = set(value) - {"kind", "points", "length"}
    if extra:
        raise FieldError(f"unknown keys {sorted(extra)} in an interpolated Field")
    points = value.get("points") or []
    if not isinstance(points, (list, tuple)) or not points:
        raise FieldError("an interpolated Field needs control points [x, y, value]")
    out = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 3:
            raise FieldError(f"a control point is [x, y, value], not {point!r}")
        out.append([_finite("a control point", c) for c in point])
    length = _finite("length", value.get("length", 2.0))
    if not length > 0:
        raise FieldError("the length of an interpolated Field must be positive")
    return {"kind": "interpolated", "points": out, "length": length}


def _sites(sites):
    """[[x, y, z, value]] as floats, checked (fast for the plain numbers a
    Document holds: a painted Field can have one row per site of a large
    system)."""
    import numpy as np
    for site in sites:
        if not isinstance(site, (list, tuple)) or len(site) != 4:
            raise FieldError(f"a painted site is [x, y, z, value], not {site!r}")
    plain = all(type(c) is float or type(c) is int for site in sites for c in site)
    if not plain:
        return [[_finite("a painted site", c) for c in site] for site in sites]
    array = np.asarray(sites, dtype=float).reshape(-1, 4)
    if not np.isfinite(array).all():
        bad = next(site for site in sites if not np.isfinite(site).all())
        raise FieldError(f"a painted site must be finite numbers, not {bad!r}")
    return array.tolist()


def _normalize_painted(value):
    extra = set(value) - {"kind", "sites", "tol", "default"}
    if extra:
        raise FieldError(f"unknown keys {sorted(extra)} in a painted Field")
    sites = value.get("sites") or []
    if not isinstance(sites, (list, tuple)):
        raise FieldError("the sites of a painted Field are a list of [x, y, z, value]")
    out = _sites(sites)
    tol = _finite("tol", value.get("tol", 0.1))
    if not tol > 0:
        raise FieldError("tol must be positive")
    return {"kind": "painted", "sites": out, "tol": tol,
            "default": _finite("default", value.get("default", 0.0))}


NORMALIZERS = {"profile": _normalize_profile, "interpolated": _normalize_interpolated,
               "painted": _normalize_painted}


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
    if component is not None:
        if isinstance(component, bool) or not isinstance(component, numbers.Real) or \
                component not in (0, 1, 2):
            raise FieldError("component is 0, 1, 2 (x, y, z) or null")
        component = int(component)           # 1.0 from a JSON client indexes as 1
    scale, tol = _finite("scale", value.get("scale", 1.0)), _finite("tol", value.get("tol", 0.1))
    if not tol > 0:
        raise FieldError("tol must be positive")
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
            try:
                constant = expression(0.0, 0.0, 0.0)
            except ExpressionError as error:     # 9**9**9, or a complex (-8)**(1/3)
                raise FieldError(str(error)) from None
            return normalize(float(constant))
        return expression.source
    if isinstance(value, dict):
        kind = value.get("kind")
        if kind == "constant" and set(value) == {"kind", "value"}:
            return _normalize_simple(value["value"])
        if kind == "expression" and set(value) == {"kind", "expr"}:
            return _normalize_simple(str(value["expr"]))
        if kind in ("piecewise", "from_result") or kind in NORMALIZERS:
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
    exported scripts define this same function, with nearest_site)."""
    values = [float(v) for v in values]
    find = nearest_site(positions, tol)

    def f(r):
        i = find(r)
        return scale * values[i] if i >= 0 else 0.0
    return f


def interpolated_field(points, length):
    """A function of position: the values of control points [x, y, value]
    averaged with Gaussian weights of the distance in the plane (an
    interpolated Field; exported scripts define this same function)."""
    import numpy as np
    points = np.asarray(points, dtype=float).reshape(-1, 3)

    def f(r):
        d2 = (points[:, 0] - r[0]) ** 2 + (points[:, 1] - r[1]) ** 2
        w = np.exp(-(d2 - d2.min()) / (2 * length ** 2))    # shifted: never all zero
        return float(np.dot(w, points[:, 2]) / w.sum())
    return f


def painted_field(sites, tol, default=0.0):
    """A function of position: the value painted on the site nearest to it,
    when that site is closer than tol, else the default (a painted Field;
    exported scripts define this same function)."""
    values = [float(site[3]) for site in sites]
    find = nearest_site(sites, tol)

    def f(r):
        i = find(r)
        return values[i] if i >= 0 else default
    return f


def paint(value, positions, indices, painted, regions=None, results=None):
    """A painted Field: value (a scalar Field) with the sites at indices of
    positions set to painted. A painted Field is extended; any other kind
    becomes one that keeps its values: a constant as the default, an
    expression (or another kind) baked into every site, 0 elsewhere."""
    import numpy as np
    value = normalize(value)
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    if isinstance(value, dict) and value["kind"] == "painted":
        sites, tol, default = [list(s) for s in value["sites"]], value["tol"], value["default"]
    elif isinstance(value, float):
        sites, tol, default = [], 0.1, value
    else:
        old = evaluate_positions(value, positions, regions, results)
        sites = [list(map(float, r)) + [float(v)] for r, v in zip(positions, old)]
        tol, default = 0.1, 0.0
    targets = positions[np.asarray(list(indices), dtype=int)].reshape(-1, 3)
    found = nearest_indices(np.asarray(sites, dtype=float).reshape(-1, 4), targets, tol)
    for i in found[found >= 0]:
        sites[i][3] = float(painted)
    new = targets[found < 0]
    for i in np.nonzero(nearest_indices(new, new, tol) == np.arange(len(new)))[0]:
        sites.append([float(c) for c in new[i]] + [float(painted)])     # one per site
    return {"kind": "painted", "sites": sites, "tol": tol, "default": default}


HELPERS = {"from_result": site_field, "interpolated": interpolated_field,
           "painted": painted_field}
NEEDS = {site_field: (nearest_site,), painted_field: (nearest_site,)}   # for exported scripts


def helpers_of(value):
    """The functions (of HELPERS) a Field's compiled form needs, for any
    JSON value (a Field, a vector of them, a dict of parameters)."""
    if isinstance(value, dict) and value.get("kind") in HELPERS:
        helper = HELPERS[value["kind"]]
        return {helper, *NEEDS.get(helper, ())}
    if isinstance(value, dict):
        return {f for v in value.values() for f in helpers_of(v)}
    if isinstance(value, (list, tuple)):
        return {f for v in value for f in helpers_of(v)}
    return set()


def _array_function(value):
    """The function of an interpolated or painted Field."""
    if value["kind"] == "interpolated":
        return interpolated_field(value["points"], value["length"])
    return painted_field(value["sites"], value["tol"], value["default"])


def _array_code(value):
    if value["kind"] == "interpolated":
        return f"interpolated_field({value['points']!r}, {value['length']!r})"
    return f"painted_field({value['sites']!r}, {value['tol']!r}, {value['default']!r})"


def _result_ref(value, results):
    """The ResultRef a from_result Field reads, or FieldError."""
    if results is None or value["calculation"] not in results:
        raise FieldError(f"the result of {value['calculation']} is not available")
    return results[value["calculation"]]


def _result_function(value, results):
    ref = _result_ref(value, results)
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


def _piecewise_function(value, regions, bond=None):
    default = _compile_simple(value["default"])
    pieces = []
    for p in value["pieces"]:
        selection = _selection(regions, p["region"])
        inside = region_tools.compile_indicator(selection)
        if bond is not None and selection["kind"] == "positions":
            inside = bond(inside, "both")              # known on the sites: both ends inside
        pieces.append((inside, _compile_simple(p["value"])))

    def f(r):
        for inside, piece in reversed(pieces):       # the last piece wins
            if inside(r):
                return piece(r) if callable(piece) else piece
        return default(r) if callable(default) else default
    return f


def compile_scalar(value, weight=None, regions=None, results=None, bond=None):
    """A number, or a callable f(position) for pyqula.

    weight: optional callable of position multiplying the Field (the
    indicator of a region); a constant then becomes a callable too.
    regions: {id: selection} for the regions a piecewise Field names;
    results: {calculation id: ResultRef} for the results it reads.
    bond: for a parameter pyqula evaluates at bond midpoints, a function
    of (a function of position, rule) giving the function of a midpoint
    (core/bonds.py): what is known on the sites only (painted and
    from_result Fields, regions by positions) goes through it.
    """
    value = normalize(value)
    if isinstance(value, float):
        if weight is None:
            return value
        return _weighted(lambda r: value, weight)
    if isinstance(value, dict) and value["kind"] == "from_result":
        function = _result_function(value, results)
    elif isinstance(value, dict) and value["kind"] == "profile":
        function = Expression(profile_expression(value)).at
    elif isinstance(value, dict) and value["kind"] in ("interpolated", "painted"):
        function = _array_function(value)
    elif isinstance(value, dict):
        function = _piecewise_function(value, regions, bond)
    else:
        function = Expression(value).at
    if bond is not None and kind_of(value) in ("from_result", "painted"):
        function = bond(function, "mean")
    if weight is None:
        return function
    return _weighted(function, weight)


def _weighted(function, weight):
    """function times weight, as a function of one position only: pyqula
    reads a callable of two or more parameters as a function of the two
    ends of a bond (add_kekule), so no default arguments here."""
    def f(r):
        return function(r) * weight(r)
    return f


def compile_vector(value, weight=None, regions=None, results=None, bond=None):
    return [compile_scalar(v, weight, regions, results, bond) for v in normalize_vector(value)]


def _code_simple(value):
    return repr(value) if isinstance(value, float) else f"({Expression(value).to_python('r')})"


def _code_body(value, regions, bond=None, bound=None):
    """Python expression of r for a normalized non-constant Field; with
    bond, a region by positions is a function of the bond's midpoint,
    appended to bound as (name, code) to be made once."""
    if not isinstance(value, dict):
        return Expression(value).to_python("r")
    body = _code_simple(value["default"])
    for piece in value["pieces"]:                      # later pieces are tested first
        selection = _selection(regions, piece["region"])
        inside = region_tools.code_indicator(selection)
        if bond is not None and selection["kind"] == "positions":
            name = f"inside{len(bound)}"
            bound.append((name, bond(f"lambda r: {inside}", "both")))
            inside = f"{name}(r)"
        body = f"{_code_simple(piece['value'])} if {inside} else ({body})"
    return body


def _lambda(bound, body):
    """lambda r: body, with the callables of bound [(name, code)] made once."""
    if not bound:
        return f"lambda r: {body}"
    return (f"(lambda {', '.join(name for name, _ in bound)}: lambda r: {body})"
            f"({', '.join(code for _, code in bound)})")


def _code_result(value, results):
    """site_field(...) with the result's positions and values written out."""
    ref = _result_ref(value, results)
    values = site_values(ref, value["array"], value["component"])
    positions = [[float(c) for c in p] for p in ref.positions]
    return (f"site_field(np.array({positions!r}), np.array({[float(v) for v in values]!r}), "
            f"{value['tol']!r}, {value['scale']!r})")


def code_scalar(value, weight_code=None, regions=None, results=None, bond=None,
                weight_function=None):
    """Python source equivalent to compile_scalar (numpy imported as np;
    a from_result Field calls site_field, which the script defines).
    bond: compile_scalar's, for source: a function of (the source of a
    function of position, rule) giving that of the function of a bond's
    midpoint; weight_function: the source of a callable weight, made once
    (a region by positions at the bonds), instead of weight_code."""
    value = normalize(value)
    bound = []
    if weight_function is not None:
        bound.append(("weight", weight_function))
        weight_code = "weight(r)"
    if isinstance(value, float):
        if weight_code is None:
            return repr(value)
        return _lambda(bound, f"{value!r} * ({weight_code})")
    if isinstance(value, dict) and value["kind"] == "profile":
        value = profile_expression(value)            # an expression from here on
    if isinstance(value, dict) and value["kind"] in ("from_result", "interpolated", "painted"):
        function = _code_result(value, results) if value["kind"] == "from_result" else \
            _array_code(value)
        if bond is not None and value["kind"] != "interpolated":
            function = bond(function, "mean")
        if weight_code is None:
            return function
        return _lambda([("f", function)] + bound, f"f(r) * ({weight_code})")
    body = _code_body(value, regions, bond, bound)
    if weight_code is None:
        return _lambda(bound, body)
    return _lambda(bound, f"({body}) * ({weight_code})")


def code_vector(value, weight_code=None, regions=None, results=None, bond=None,
                weight_function=None):
    return "[" + ", ".join(code_scalar(v, weight_code, regions, results, bond, weight_function)
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
        if results is None or value["calculation"] not in results:
            raise FieldError(f"the result of {value['calculation']} is not available")
        ref = results[value["calculation"]]
        values = site_values(ref, value["array"], value["component"])
        found = nearest_indices(ref.positions, positions, value["tol"])
        return np.where(found >= 0, value["scale"] * values[found], 0.0)
    if value["kind"] == "profile":
        return _evaluate_simple(profile_expression(value), positions)
    if value["kind"] == "painted":
        sites = np.asarray(value["sites"], dtype=float).reshape(-1, 4)
        found = nearest_indices(sites, positions, value["tol"])
        return np.where(found >= 0, sites[found, 3] if len(sites) else 0.0, value["default"])
    if value["kind"] == "interpolated":
        f = _array_function(value)
        return np.array([f(r) for r in positions], dtype=float)
    out = _evaluate_simple(value["default"], positions)
    for piece in value["pieces"]:
        inside = region_tools.evaluate_positions(_selection(regions, piece["region"]), positions)
        out[inside] = _evaluate_simple(piece["value"], positions)[inside]
    return out
