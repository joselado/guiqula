"""Fields: every numeric term parameter (PLAN.md 3.8).

A Field is stored in the Document as plain JSON:

- a number: ``constant``;
- a string: ``expression`` of position (guiqula.core.expressions);
- an object ``{"kind": ..., ...}`` for the other kinds. Phase 1 accepts
  ``{"kind": "constant", "value": v}`` and ``{"kind": "expression",
  "expr": s}`` and stores them in the short forms above; piecewise, profile,
  interpolated, painted and from_result arrive in phases 3 and 4.

A vector Field is a list of three scalar Fields, one per component.

compile_* turn a Field into what pyqula takes (a number or a callable of one
position, ``f(r)`` with r = (x, y, z)); code_* give the same thing as Python
source for script export. Both live here so they cannot disagree.
"""
import math
import numbers

from guiqula.core.expressions import Expression, ExpressionError

LATER_KINDS = ("piecewise", "profile", "interpolated", "painted", "from_result")


class FieldError(ValueError):
    """The value is not a valid Field; the message says why."""


def normalize(value):
    """Return the canonical JSON form of a scalar Field, or raise FieldError."""
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
            return normalize(value["value"])
        if kind == "expression" and set(value) == {"kind", "expr"}:
            return normalize(str(value["expr"]))
        if kind in LATER_KINDS:
            raise FieldError(f"{kind} Fields are not implemented yet (PLAN.md 3.8)")
        raise FieldError(f"unknown Field {value!r}")
    raise FieldError(f"a Field is a number or an expression string, not {type(value).__name__}")


def normalize_vector(value, length=3):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise FieldError(f"a vector Field is a list of {length} Fields")
    return [normalize(v) for v in value]


def is_constant(value):
    return isinstance(value, float)


def compile_scalar(value, weight=None):
    """A number, or a callable f(position) for pyqula.

    weight: optional callable of position multiplying the Field (the
    indicator of a region); a constant then becomes a callable too.
    """
    value = normalize(value)
    if isinstance(value, float):
        if weight is None:
            return value
        return lambda r, c=value, w=weight: c * w(r)
    expression = Expression(value)
    if weight is None:
        return expression.at
    return lambda r, e=expression, w=weight: e.at(r) * w(r)


def compile_vector(value, weight=None):
    return [compile_scalar(v, weight) for v in normalize_vector(value)]


def code_scalar(value, weight_code=None):
    """Python source equivalent to compile_scalar (numpy imported as np)."""
    value = normalize(value)
    if isinstance(value, float):
        if weight_code is None:
            return repr(value)
        return f"lambda r: {value!r} * ({weight_code})"
    body = Expression(value).to_python("r")
    if weight_code is None:
        return f"lambda r: {body}"
    return f"lambda r: ({body}) * ({weight_code})"


def code_vector(value, weight_code=None):
    return "[" + ", ".join(code_scalar(v, weight_code) for v in normalize_vector(value)) + "]"


def evaluate_positions(value, positions):
    """Evaluate a scalar Field on an (N, 3) array (canvas previews, tests)."""
    import numpy as np
    value = normalize(value)
    if isinstance(value, float):
        return np.full(len(positions), value)
    return Expression(value).evaluate_positions(positions)
