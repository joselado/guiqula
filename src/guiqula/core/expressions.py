"""Expressions of position, evaluated as data (PLAN.md 3.8, decision 14.8).

An expression is a string such as ``0.3*tanh(x/4)`` or ``where(x < 0, 1, -1)``.
It is parsed once, checked against a whitelist of syntax nodes, compiled,
and then evaluated as often as needed, with scalars (pyqula calls a Field
once per site or bond) or with arrays (canvas previews). Because nothing
outside the whitelist can be expressed (no attribute access except
``np.<function>``, no subscripts, no keywords, no calls except to the
functions below), expressions need no trust prompt; only Python nodes do.

Names available in an expression:

- ``x``, ``y``, ``z``: the Cartesian coordinates of the position;
- ``r``: the distance from the origin, ``sqrt(x**2 + y**2 + z**2)``;
- ``pi``;
- the functions in FUNCTIONS, also as ``np.<name>``.

Integer literals are read as floats, so ``9**9**9`` overflows to an error
instead of building a huge integer. Comparisons give booleans that combine
with ``&``, ``|`` and ``~`` and multiply as 0 and 1; ``and``/``or``/``if``
are not available because they do not act elementwise on arrays.
"""
import ast
import math

import numpy as np

VARIABLES = ("x", "y", "z", "r")
CONSTANTS = {"pi": math.pi}
FUNCTIONS = {name: getattr(np, name) for name in (
    "sin", "cos", "tan", "arcsin", "arccos", "arctan", "arctan2", "hypot",
    "sinh", "cosh", "tanh", "arcsinh", "arccosh", "arctanh",
    "exp", "log", "log10", "log2", "sqrt", "abs", "sign", "heaviside",
    "floor", "ceil", "minimum", "maximum", "clip", "where", "mod",
)}
MAX_LENGTH = 1000
MAX_DEPTH = 40

_ALLOWED = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Call, ast.Name,
    ast.Load, ast.Constant, ast.Attribute,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.BitAnd, ast.BitOr, ast.BitXor, ast.USub, ast.UAdd, ast.Invert,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
)


class ExpressionError(ValueError):
    """The text is not a valid expression; the message says why."""


def _check(node, source, depth=0):
    if depth > MAX_DEPTH:
        raise ExpressionError("expression nested too deeply")
    if not isinstance(node, _ALLOWED):
        what = type(node).__name__
        hint = {"BoolOp": "use & and | with parentheses instead of and/or",
                "IfExp": "use where(condition, a, b) instead of a if condition else b",
                "Subscript": "indexing is not available; use x, y, z",
                "Lambda": "write the expression itself, without lambda"}.get(what, "")
        raise ExpressionError(f"{what} is not allowed in an expression" + (f"; {hint}" if hint else ""))
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExpressionError(f"only numbers are allowed as constants, not {node.value!r}")
    elif isinstance(node, ast.Name):
        if node.id not in VARIABLES and node.id not in CONSTANTS and node.id not in FUNCTIONS:
            raise ExpressionError(
                f"unknown name {node.id!r}; available: {', '.join(VARIABLES + tuple(CONSTANTS))} "
                f"and the functions {', '.join(sorted(FUNCTIONS))}")
    elif isinstance(node, ast.Attribute):
        if not (isinstance(node.value, ast.Name) and node.value.id == "np" and node.attr in FUNCTIONS):
            raise ExpressionError("attribute access is only allowed as np.<function> for the "
                                  "whitelisted functions")
        return
    elif isinstance(node, ast.Call):
        if node.keywords:
            raise ExpressionError("keyword arguments are not allowed in an expression")
        func = node.func
        is_function = (isinstance(func, ast.Name) and func.id in FUNCTIONS) or (
            isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and func.value.id == "np" and func.attr in FUNCTIONS)
        if not is_function:
            called = ast.unparse(func)
            raise ExpressionError(f"{called}() cannot be called; the functions are: "
                                  + ", ".join(sorted(FUNCTIONS)))
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                raise ExpressionError("*arguments are not allowed in an expression")
            _check(arg, source, depth + 1)
        return
    for child in ast.iter_child_nodes(node):
        _check(child, source, depth + 1)


class _FloatConstants(ast.NodeTransformer):
    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(float(node.value)), node)


class _ToPython(ast.NodeTransformer):
    """Rewrite for a pyqula callable ``lambda r: ...`` where r is the position."""
    def __init__(self, var):
        self.var = var

    def visit_Name(self, node):
        index = {"x": 0, "y": 1, "z": 2}.get(node.id)
        if index is not None:
            return ast.Subscript(ast.Name(self.var, ast.Load()), ast.Constant(index), ast.Load())
        if node.id == "r":
            return ast.parse(f"np.linalg.norm({self.var})", mode="eval").body
        if node.id in CONSTANTS:
            return ast.parse(f"np.{node.id}", mode="eval").body
        if node.id in FUNCTIONS:
            return ast.Attribute(ast.Name("np", ast.Load()), node.id, ast.Load())
        return node

    def visit_Attribute(self, node):
        return node          # already np.<function>


class Expression:
    """A parsed, checked and compiled expression of position."""

    __slots__ = ("source", "tree", "_code", "names")

    def __init__(self, source):
        if not isinstance(source, str):
            raise ExpressionError(f"an expression is a string, not {type(source).__name__}")
        if len(source) > MAX_LENGTH:
            raise ExpressionError(f"expression longer than {MAX_LENGTH} characters")
        try:
            tree = ast.parse(source.strip(), mode="eval")
        except SyntaxError as error:
            raise ExpressionError(f"syntax error in {source!r}: {error.msg} "
                                  f"(column {error.offset})") from None
        except RecursionError:
            raise ExpressionError("expression nested too deeply") from None
        _check(tree, source)
        self.source = source.strip()
        self.tree = ast.fix_missing_locations(_FloatConstants().visit(tree))
        self._code = compile(self.tree, "<expression>", "eval")
        self.names = frozenset(n.id for n in ast.walk(tree) if isinstance(n, ast.Name))

    def __repr__(self):
        return f"Expression({self.source!r})"

    def depends_on_position(self):
        return bool(self.names & set(VARIABLES))

    def __call__(self, x, y=0.0, z=0.0):
        """Evaluate at coordinates (scalars or broadcastable arrays)."""
        namespace = dict(FUNCTIONS)
        namespace.update(CONSTANTS)
        namespace["np"] = _NP
        # numpy scalars, not Python floats: comparisons then give numpy
        # booleans, for which ~ is a logical not, as for arrays
        x, y, z = (_as_numpy(v) for v in (x, y, z))
        namespace.update(x=x, y=y, z=z)
        if "r" in self.names:
            namespace["r"] = np.sqrt(np.asarray(x) ** 2 + np.asarray(y) ** 2 + np.asarray(z) ** 2)
        try:
            return eval(self._code, {"__builtins__": {}}, namespace)
        except (ArithmeticError, ValueError, TypeError) as error:
            raise ExpressionError(f"evaluating {self.source!r}: {error}") from None

    def at(self, position):
        """Evaluate at one position (x, y, z): the pyqula callable convention."""
        return self(position[0], position[1], position[2])

    def evaluate_positions(self, positions):
        """Evaluate at an (N, 3) array of positions; returns an (N,) array."""
        p = np.asarray(positions, dtype=float)
        return np.broadcast_to(np.asarray(self(p[:, 0], p[:, 1], p[:, 2]), dtype=float), (len(p),)).copy()

    def to_python(self, var="r"):
        """Python source of the body of ``lambda <var>: ...`` with ``np`` imported."""
        tree = _ToPython(var).visit(ast.parse(self.source, mode="eval"))
        return ast.unparse(ast.fix_missing_locations(tree))


def _as_numpy(value):
    value = np.asarray(value, dtype=float)
    return value[()] if value.ndim == 0 else value


class _Namespace:
    """``np`` inside an expression: only the whitelisted functions."""
    def __init__(self, functions):
        self.__dict__.update(functions)


_NP = _Namespace(FUNCTIONS)


def parse(source):
    """Parse and check an expression; raises ExpressionError."""
    return Expression(source)
