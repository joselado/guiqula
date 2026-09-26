"""What a registry entry sees while the engine applies it: its parameters,
compiled to what pyqula takes (Fields become numbers or callables of one
position, restricted to the entry's region), and a progress reporter."""
import importlib

from guiqula.core import fields
from guiqula.core import regions as region_tools
from guiqula.registry.base import G, H
from guiqula.registry.params import ChoiceParam, FieldParam, ParamError, VectorFieldParam


class ApplyContext:
    def __init__(self, spec, params, region=None, progress=None):
        self.spec = spec
        self.params = params
        self.weight = region_tools.compile_indicator(region) if region else None
        self._progress = progress

    def value(self, name):
        param = self.spec.param_map[name]
        value = self.params[name]
        if isinstance(param, VectorFieldParam):
            return fields.compile_vector(value, self.weight if param.native else None)
        if isinstance(param, FieldParam):
            return fields.compile_scalar(value, self.weight if param.native else None)
        if isinstance(param, ChoiceParam) and param.source and value is not None:
            _check_source(param, value)
        return value

    def progress(self, fraction, text=""):
        if self._progress is not None:
            self._progress(min(max(float(fraction), 0.0), 1.0), text)

    def progress_callback(self, total):
        """A callback for pyqula loops that call back once per step."""
        count = [0]

        def callback(*args, **kwargs):
            count[0] += 1
            self.progress(count[0] / max(total, 1))
        return callback


def _check_source(param, value):
    if param.source == "operators":
        from pyqula import operatorlist
        names = operatorlist.get_operator_names()
        if value not in names:
            raise ParamError(f"{param.name}: pyqula has no operator {value!r}; it has {names}")
    else:
        raise ParamError(f"{param.name}: unknown name source {param.source!r}")


def resolve(call, h=None, g=None):
    """The Python callable behind a registry Call."""
    head, _, rest = call.target.partition(".")
    if head == "h":
        return getattr(h, rest)
    if head == "g":
        return getattr(g, rest)
    module_name, _, function = call.target.rpartition(".")
    return getattr(importlib.import_module("pyqula." + module_name), function)


def apply_call(spec, ctx, h=None, g=None):
    """Execute a declarative Call; returns what pyqula returns."""
    call = spec.call

    def arg(a):
        if a is H:
            return h
        if a is G:
            return g
        return ctx.value(a)
    function = resolve(call, h=h, g=g)
    return function(*[arg(a) for a in call.args], **{k: arg(v) for k, v in call.kwargs.items()})
