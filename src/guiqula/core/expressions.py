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
instead of building a huge integer; a literal too large for a float is
refused. A function takes exactly its number of arguments: a numpy ufunc
would read one more as the array to write its result into.

One arithmetic holds everywhere, in the engine, the canvas previews and
the exported scripts alike: a comparison is the number 1.0 where it holds
and 0.0 elsewhere, so ``(x > 0) + (y > 0)`` counts and ``-(x > 0)``
negates; ``&``, ``|``, ``^`` and ``~`` are the logical and, or, exclusive
or and not of such truth values (any nonzero number is true), 1.0 or 0.0
as well. ``and``/``or``/``if`` are not available because they do not act
elementwise on arrays. A chained comparison ``-2 < x < 2``, which Python
evaluates with ``and``, is read as ``(-2 < x) & (x < 2)``. A value that is
not a real number (a negative number to a fractional power, as in
``(-8)**(1/3)``) is refused.
"""
import ast
import copy
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
# the number of arguments of each function: a ufunc takes the array to
# write into as its next positional argument ("hypot(x, y, z)" would
# overwrite z), so a call must give exactly these
ARITY = {name: 3 if name in ("clip", "where") else function.nin
         for name, function in FUNCTIONS.items()}
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
        try:
            finite = math.isfinite(float(node.value))
        except OverflowError:                 # an integer literal of more than 308 digits
            finite = False
        if not finite:
            raise ExpressionError("a number in the expression is too large (the largest is "
                                  "about 1.8e308)")
    elif isinstance(node, ast.Name):      # a called function's name is not visited
        if node.id in FUNCTIONS:
            raise ExpressionError(f"{node.id} is a function: call it, as in {node.id}(x)")
        if node.id not in VARIABLES and node.id not in CONSTANTS:
            raise ExpressionError(
                f"unknown name {node.id!r}; available: {', '.join(VARIABLES + tuple(CONSTANTS))} "
                f"and the functions {', '.join(sorted(FUNCTIONS))}")
    elif isinstance(node, ast.Attribute):
        if not (isinstance(node.value, ast.Name) and node.value.id == "np" and node.attr in FUNCTIONS):
            raise ExpressionError("attribute access is only allowed as np.<function> for the "
                                  "whitelisted functions")
        raise ExpressionError(f"np.{node.attr} is a function: call it, as in np.{node.attr}(x)")
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
        if any(isinstance(arg, ast.Starred) for arg in node.args):
            raise ExpressionError("*arguments are not allowed in an expression")
        name = _called(node)
        if len(node.args) != ARITY[name]:
            count = ARITY[name]
            raise ExpressionError(f"{name}() takes {count} argument{'s' * (count > 1)}, "
                                  f"not {len(node.args)}")
        for arg in node.args:
            _check(arg, source, depth + 1)
        return
    elif isinstance(node, ast.Compare) and len(node.ops) > MAX_DEPTH - depth:
        # a chain a < b < c < ... is read as one & per comparison, nested
        raise ExpressionError("too many comparisons in one chain")
    for child in ast.iter_child_nodes(node):
        _check(child, source, depth + 1)


def _called(node):
    """The name of the function a checked call calls."""
    return node.func.id if isinstance(node.func, ast.Name) else node.func.attr


class _ChainedComparisons(ast.NodeTransformer):
    """``a < b < c`` as ``(a < b) & (b < c)``: Python's own reading, with
    ``and``, fails on arrays."""
    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) == 1:
            return node
        operands = [node.left] + node.comparators
        out = None
        for i, op in enumerate(node.ops):
            left = operands[i] if i == 0 else copy.deepcopy(operands[i])
            part = ast.Compare(left, [op], [operands[i + 1]])
            out = part if out is None else ast.BinOp(out, ast.BitAnd(), part)
        return ast.copy_location(out, node)


_LOGICAL = {ast.BitAnd: "logical_and", ast.BitOr: "logical_or", ast.BitXor: "logical_xor"}


def _np_call(name, *args):
    return ast.Call(ast.Attribute(ast.Name("np", ast.Load()), name, ast.Load()), list(args), [])


def _is_truth(node):
    """Whether a node gives a truth value: a comparison, or &, |, ^, ~."""
    return isinstance(node, ast.Compare) or (
        isinstance(node, ast.BinOp) and type(node.op) in _LOGICAL) or (
        isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert))


class _RealArithmetic(ast.NodeTransformer):
    """One arithmetic for the whole expression: a truth value is the number
    1.0 or 0.0 wherever it is used as a number. Without this, a comparison
    between literals is a Python bool and one at a position a numpy bool,
    whose + is a logical or and whose - fails: "(1 > 0) + (1 > 0)" was 2
    and "(x > 0) + (y > 0)" 1. Inside &, |, ^, ~ and the condition of where
    a truth value stays a boolean, since only its truth is read there."""

    def visit(self, node):
        """node, rewritten as a number."""
        if _is_truth(node):
            return ast.copy_location(_np_call("float64", self._truth(node)), node)
        return super().visit(node)

    def _truth(self, node):
        """node, rewritten as a truth value (a boolean, or a number whose
        truth is read)."""
        if isinstance(node, ast.Compare):
            node.left = self.visit(node.left)
            node.comparators = [self.visit(c) for c in node.comparators]
            return node
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
            return ast.copy_location(_np_call("logical_not", self._truth(node.operand)), node)
        if isinstance(node, ast.BinOp) and type(node.op) in _LOGICAL:
            return ast.copy_location(_np_call(_LOGICAL[type(node.op)], self._truth(node.left),
                                              self._truth(node.right)), node)
        return self.visit(node)

    def visit_Call(self, node):
        if _called(node) == "where":
            node.args = [self._truth(node.args[0])] + [self.visit(a) for a in node.args[1:]]
            return node
        return self.generic_visit(node)


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
        self.names = frozenset(n.id for n in ast.walk(tree) if isinstance(n, ast.Name))
        try:
            tree = _RealArithmetic().visit(_ChainedComparisons().visit(tree))
            self.tree = ast.fix_missing_locations(_FloatConstants().visit(tree))
            self._code = compile(self.tree, "<expression>", "eval")
        except RecursionError:
            raise ExpressionError("expression nested too deeply") from None

    def __repr__(self):
        return f"Expression({self.source!r})"

    def depends_on_position(self):
        return bool(self.names & set(VARIABLES))

    def __call__(self, x, y=0.0, z=0.0):
        """Evaluate at coordinates (scalars or broadcastable arrays)."""
        namespace = dict(FUNCTIONS)
        namespace.update(CONSTANTS)
        namespace["np"] = _NP
        # numpy scalars, not Python floats, so that an evaluation at one
        # position (pyqula's, per site) computes as one on arrays does
        x, y, z = (_as_numpy(v) for v in (x, y, z))
        namespace.update(x=x, y=y, z=z)
        if "r" in self.names:
            namespace["r"] = np.sqrt(np.asarray(x) ** 2 + np.asarray(y) ** 2 + np.asarray(z) ** 2)
        try:
            # a value that is not finite is NaN or inf, without a warning: a warning
            # raised from this frame, whose builtins are empty, is KeyError('__import__')
            # (Python 3.14, NumPy 2.4)
            with np.errstate(all="ignore"):
                value = eval(self._code, {"__builtins__": {}}, namespace)
        except (ArithmeticError, ValueError, TypeError) as error:
            raise ExpressionError(f"evaluating {self.source!r}: {error}") from None
        if np.iscomplexobj(value):
            raise ExpressionError(f"evaluating {self.source!r}: the value is not a real number "
                                  f"(a negative number to a fractional power is complex)")
        return value

    def at(self, position):
        """Evaluate at one position (x, y, z): the pyqula callable convention."""
        return self(position[0], position[1], position[2])

    def evaluate_positions(self, positions):
        """Evaluate at an (N, 3) array of positions; returns an (N,) array."""
        p = np.asarray(positions, dtype=float)
        return np.broadcast_to(np.asarray(self(p[:, 0], p[:, 1], p[:, 2]), dtype=float), (len(p),)).copy()

    def to_python(self, var="r"):
        """Python source of the body of ``lambda <var>: ...`` with ``np`` imported."""
        tree = _ChainedComparisons().visit(ast.parse(self.source, mode="eval"))
        tree = _ToPython(var).visit(_RealArithmetic().visit(tree))
        return ast.unparse(ast.fix_missing_locations(tree))


def _as_numpy(value):
    # a copy: an expression never writes into the arrays it is given
    value = np.array(value, dtype=float)
    return value[()] if value.ndim == 0 else value


class _Namespace:
    """``np`` inside an expression: only the whitelisted functions."""
    def __init__(self, functions):
        self.__dict__.update(functions)


# np in an expression also has what _RealArithmetic writes, which the
# expression's own text cannot call (_check allows FUNCTIONS only)
_NP = _Namespace(dict(FUNCTIONS, **{name: getattr(np, name) for name in (
    "float64", "logical_and", "logical_or", "logical_xor", "logical_not")}))


def parse(source):
    """Parse and check an expression; raises ExpressionError."""
    return Expression(source)
