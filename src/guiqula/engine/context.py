"""What a registry entry sees while the engine applies it: its parameters,
compiled to what pyqula takes (Fields become numbers or callables of one
position, restricted to the entry's region; piecewise Fields look up the
regions they name in ``regions``), a progress reporter, and ``note`` for
what the entry wants reported (the mean field's total energy)."""
import importlib

from guiqula.core import fields
from guiqula.core import regions as region_tools
from guiqula.registry.base import G, H
from guiqula.registry.params import (ChoiceParam, ConditionParam, FieldParam, ParamError,
                                     VectorFieldParam)


class ApplyContext:
    def __init__(self, spec, params, region=None, progress=None, regions=None):
        self.spec = spec
        self.params = params
        self.weight = region_tools.compile_indicator(region) if region else None
        self.regions = regions or {}
        self.notes = {}
        self._progress = progress

    def value(self, name):
        param = self.spec.param_map[name]
        value = self.params[name]
        if isinstance(param, VectorFieldParam):
            return fields.compile_vector(value, self.weight if param.native else None,
                                         self.regions)
        if isinstance(param, FieldParam):
            return fields.compile_scalar(value, self.weight if param.native else None,
                                         self.regions)
        if isinstance(param, ConditionParam):
            return param.compile(value)
        if isinstance(param, ChoiceParam) and param.source and value is not None:
            _check_source(param, value)
        return value

    def note(self, name, value):
        """Something to report with the stage (JSON data)."""
        self.notes[name] = value

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


def source_names(source):
    """The names pyqula itself lists for a ChoiceParam source (CLAUDE.md)."""
    if source == "operators":
        from pyqula import operatorlist
        return list(operatorlist.get_operator_names())
    if source == "guesses":
        from pyqula import meanfield
        return list(meanfield.get_guess_names())
    if source == "jax_solvers":
        from pyqula.scftk import densitydensity_jax
        return list(densitydensity_jax.get_jax_solver_names())
    if source == "pairing_modes":
        from pyqula.sctk import pairing
        return list(pairing.get_pairing_modes())
    raise ParamError(f"unknown name source {source!r}")


SOURCES = ("operators", "guesses", "jax_solvers", "pairing_modes")


def _check_source(param, value):
    names = source_names(param.source)
    if value not in names:
        what = param.source[:-1].replace("_", " ")     # operators -> operator
        raise ParamError(f"{param.name}: pyqula has no {what} {value!r}; it has {names}")


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
