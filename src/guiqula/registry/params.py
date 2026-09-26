"""Parameter types of registry entries (PLAN.md 3.2).

Each parameter normalizes a JSON value (filling the default, checking the
type) and says how the engine and the script exporter turn it into what
pyqula takes. Term parameters that are numbers are Fields (PLAN.md 3.8):
FieldParam and VectorFieldParam. ``native=False`` marks a pyqula argument
that does not accept a function of position; such a Field must be constant,
and the form says so.
"""
import math
import numbers

from guiqula.core import fields


class ParamError(ValueError):
    pass


class Param:
    type_name = "param"

    def __init__(self, name, default, label=None, doc=""):
        self.name = name
        self.default = default
        self.label = label or name
        self.doc = doc

    def normalize(self, value):
        return value

    def describe(self):
        return {"name": self.name, "type": self.type_name, "default": self.default,
                "label": self.label, "doc": self.doc}

    def __repr__(self):
        return f"{type(self).__name__}({self.name!r})"


class FieldParam(Param):
    """A scalar Field (constant, expression of position, piecewise).
    minimum and maximum bound its constant values (an expression is checked
    by pyqula when it runs)."""
    type_name = "field"

    def __init__(self, name, default=0.0, label=None, doc="", native=True, minimum=None,
                 maximum=None):
        super().__init__(name, default, label, doc)
        self.native = native
        self.minimum, self.maximum = minimum, maximum

    def _check_bounds(self, value):
        constants = [value] if fields.is_constant(value) else []
        if isinstance(value, dict) and value.get("kind") == "piecewise":
            constants = [v for v in [value["default"]] + [p["value"] for p in value["pieces"]]
                         if fields.is_constant(v)]
        for constant in constants:
            _number(self.name, constant, float, self.minimum, self.maximum)

    def normalize(self, value):
        try:
            value = fields.normalize(value)
        except fields.FieldError as error:
            raise ParamError(f"{self.name}: {error}") from None
        if not self.native and not fields.is_constant(value):
            raise ParamError(f"{self.name}: this parameter must be a constant; the pyqula call "
                             f"behind it does not take a function of position")
        self._check_bounds(value)
        return value

    def describe(self):
        return dict(super().describe(), native=self.native, minimum=self.minimum,
                    maximum=self.maximum)


class VectorFieldParam(FieldParam):
    """A vector Field: one scalar Field per component."""
    type_name = "vector_field"

    def __init__(self, name, default=(0.0, 0.0, 0.0), label=None, doc="", native=True, length=3):
        super().__init__(name, list(default), label, doc, native)
        self.length = length

    def normalize(self, value):
        try:
            value = fields.normalize_vector(value, self.length)
        except fields.FieldError as error:
            raise ParamError(f"{self.name}: {error}") from None
        if not self.native and not all(fields.is_constant(v) for v in value):
            raise ParamError(f"{self.name}: this parameter must be constant")
        for component in value:
            self._check_bounds(component)
        return value


def _number(name, value, kind, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ParamError(f"{name}: expected a number, got {value!r}")
    if kind is int:
        if float(value) != int(value):
            raise ParamError(f"{name}: expected an integer, got {value!r}")
        value = int(value)
    else:
        value = float(value)
        if not math.isfinite(value):
            raise ParamError(f"{name}: {value} is not finite")
    if minimum is not None and value < minimum:
        raise ParamError(f"{name}: must be at least {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ParamError(f"{name}: must be at most {maximum}, got {value}")
    return value


class IntParam(Param):
    """An integer; optional: None is allowed too (and means "pyqula's
    default", which the entry then does not pass)."""
    type_name = "int"

    def __init__(self, name, default, label=None, doc="", minimum=None, maximum=None,
                 optional=False):
        super().__init__(name, default, label, doc)
        self.minimum, self.maximum = minimum, maximum
        self.optional = optional

    def normalize(self, value):
        if value is None and self.optional:
            return None
        return _number(self.name, value, int, self.minimum, self.maximum)

    def describe(self):
        return dict(super().describe(), optional=self.optional)


class FloatParam(IntParam):
    """A plain number: for calculation settings, never for term parameters."""
    type_name = "float"

    def normalize(self, value):
        if value is None and self.optional:
            return None
        return _number(self.name, value, float, self.minimum, self.maximum)


class SeedParam(IntParam):
    """Seed of a stochastic entry; the engine seeds numpy with it right
    before applying the entry (PLAN.md 3.3)."""
    type_name = "seed"

    def __init__(self, name="seed", default=1, label="seed", doc="random seed"):
        super().__init__(name, default, label, doc, minimum=0, maximum=2**32 - 1)


class IntVectorParam(Param):
    type_name = "int_vector"

    def __init__(self, name, default, label=None, doc="", minimum=None):
        super().__init__(name, list(default), label, doc)
        self.length = len(default)
        self.minimum = minimum

    def normalize(self, value):
        if not isinstance(value, (list, tuple)) or len(value) != self.length:
            raise ParamError(f"{self.name}: expected a list of {self.length} integers")
        return [_number(self.name, v, int, self.minimum, None) for v in value]


class BoolParam(Param):
    type_name = "bool"

    def normalize(self, value):
        if not isinstance(value, bool):
            raise ParamError(f"{self.name}: expected true or false")
        return value


class ChoiceParam(Param):
    """One of a set of names. With ``source``, the names come from pyqula
    itself (e.g. "operators": operatorlist.get_operator_names()) and are
    checked by the engine, which may import pyqula; here only the type is
    checked. ``optional`` allows null."""
    type_name = "choice"

    def __init__(self, name, default, choices=None, source=None, optional=False, label=None, doc=""):
        super().__init__(name, default, label, doc)
        self.choices = tuple(choices) if choices else None
        self.source = source
        self.optional = optional

    def normalize(self, value):
        if value is None and self.optional:
            return None
        if not isinstance(value, str):
            raise ParamError(f"{self.name}: expected a name, got {value!r}")
        if self.choices is not None and value not in self.choices:
            raise ParamError(f"{self.name}: {value!r} is not one of {list(self.choices)}")
        return value

    def describe(self):
        return dict(super().describe(), choices=self.choices, source=self.source,
                    optional=self.optional)


class PositionsParam(Param):
    """A list of [x, y, z] positions."""
    type_name = "positions"

    def __init__(self, name="positions", default=(), label=None, doc=""):
        super().__init__(name, list(default), label, doc)

    def normalize(self, value):
        if not isinstance(value, (list, tuple)):
            raise ParamError(f"{self.name}: expected a list of [x, y, z]")
        out = []
        for p in value:
            if not isinstance(p, (list, tuple)) or len(p) != 3:
                raise ParamError(f"{self.name}: every position is [x, y, z], got {p!r}")
            out.append([_number(self.name, c, float, None, None) for c in p])
        return out


class FloatVectorParam(IntVectorParam):
    """A fixed-length list of plain numbers (a displacement, a direction)."""
    type_name = "float_vector"

    def normalize(self, value):
        if not isinstance(value, (list, tuple)) or len(value) != self.length:
            raise ParamError(f"{self.name}: expected a list of {self.length} numbers")
        return [_number(self.name, v, float, self.minimum, None) for v in value]


class TextParam(Param):
    """A short string, optionally checked against a regular expression
    (``pattern``, with ``hint`` saying what it wants)."""
    type_name = "text"

    def __init__(self, name, default, label=None, doc="", pattern=None, hint=""):
        super().__init__(name, default, label, doc)
        self.pattern, self.hint = pattern, hint

    def normalize(self, value):
        import re
        if not isinstance(value, str):
            raise ParamError(f"{self.name}: expected text, got {value!r}")
        value = value.strip()
        if self.pattern and not re.fullmatch(self.pattern, value):
            raise ParamError(f"{self.name}: {value!r} is not valid" +
                             (f"; {self.hint}" if self.hint else ""))
        return value

    def describe(self):
        return dict(super().describe(), pattern=self.pattern, hint=self.hint)


class ConditionParam(Param):
    """A condition on the position: an expression of x, y, z, r
    (guiqula.core.expressions) that is true, or nonzero, on the sites it
    selects. The engine hands pyqula a function of one position returning a
    boolean; the exporter writes the same function as a lambda."""
    type_name = "condition"

    def normalize(self, value):
        from guiqula.core.expressions import Expression, ExpressionError
        if not isinstance(value, str):
            raise ParamError(f"{self.name}: expected an expression of x, y, z, r")
        try:
            return Expression(value).source
        except ExpressionError as error:
            raise ParamError(f"{self.name}: {error}") from None

    @staticmethod
    def compile(value):
        from guiqula.core.expressions import Expression
        expression = Expression(value)
        return lambda r, e=expression: bool(e.at(r))

    @staticmethod
    def code(value):
        from guiqula.core.expressions import Expression
        return f"lambda r: bool({Expression(value).to_python('r')})"


class CodeParam(Param):
    """Python source of a Python node (PLAN.md 3.1, 13.7). Normalizing only
    checks the syntax; the code runs in the worker, and only in a trusted
    document."""
    type_name = "code"

    def normalize(self, value):
        import ast
        if not isinstance(value, str):
            raise ParamError(f"{self.name}: expected Python source text")
        value = value.replace("\r\n", "\n").rstrip() + "\n"
        try:
            ast.parse(value)
        except SyntaxError as error:
            raise ParamError(f"{self.name}: syntax error in line {error.lineno}: "
                             f"{error.msg}") from None
        return value
