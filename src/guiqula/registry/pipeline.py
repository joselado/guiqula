"""How a system's pipeline is laid out according to the catalogue: the
planning half of the engine, with no pyqula, shared by the engine (which
executes the plan) and the UI (which shows modes, flags and staleness).

- Every entry is checked against its registry entry: unknown kind, bad
  parameters, a region on a term that cannot take one. A failing entry is
  *invalid*: flagged and skipped, never deleted (PLAN.md 3.1, decision
  14.3). pyqula may still reject a valid-looking entry when it is applied;
  the engine flags that the same way.
- The Hilbert space is fixed once, before the first term, from the
  ``requires`` of every enabled, valid term (PLAN.md 3.1): pyqula would
  otherwise upgrade it in the middle of the stack.
- Each stage has a content key: the key of the stage before, plus what this
  stage does, plus everything it references (a term's region selection;
  other systems and results once from_result Fields exist). Keys are
  DAG-aware (decision 14.9) and hash physics only: ids, names and the ui
  block never enter them. A disabled or invalid entry does nothing, so its
  key is the key before it. The key of a calculation is what a result is
  stamped with; a result whose key differs from the current one is stale.
"""
from dataclasses import dataclass, field

from guiqula.core import regions as region_tools
from guiqula.core.document import DocumentError
from guiqula.core.hashing import content_hash
from guiqula.registry import base as registry
from guiqula.registry.params import FieldParam, ParamError

MODES = ("spinless", "spinful", "nambu")


@dataclass
class StagePlan:
    stage: str                  # "base", "op", "construction", "term"
    id: str | None              # entry id (None for base and construction)
    kind: str
    enabled: bool = True
    spec: object = None         # registry EntrySpec
    params: dict | None = None  # normalized parameters
    region: dict | None = None  # normalized region selection
    problem: str | None = None  # why the entry is invalid (skipped)
    key: str = ""
    applied: bool = False       # enabled and valid: the engine runs it

    def describe(self):
        return {"stage": self.stage, "id": self.id, "kind": self.kind,
                "enabled": self.enabled, "problem": self.problem, "key": self.key}


@dataclass
class SystemPlan:
    system_id: str
    kind: str
    stages: list = field(default_factory=list)
    construction: dict = field(default_factory=dict)   # effective construction
    mode: str = "spinful"
    upgraded_by: list = field(default_factory=list)    # term ids that forced the mode
    problem: str | None = None                         # whole system unbuildable

    @property
    def key(self):
        return self.stages[-1].key if self.stages else ""

    def stage(self, entry_id):
        for s in self.stages:
            if s.id == entry_id:
                return s
        raise KeyError(entry_id)


def _check_entry(family, entry_kind, params, system_kind):
    """Return (spec, normalized params, problem)."""
    try:
        spec = registry.get(family, entry_kind)
    except registry.RegistryError as error:
        return None, None, str(error).strip("\"'")
    if system_kind not in spec.systems:
        return spec, None, f"{spec.label} does not apply to a {system_kind} system"
    try:
        return spec, spec.normalize_params(params), None
    except ParamError as error:
        return spec, None, str(error)


def plan_system(document, system_id):
    system = document.system(system_id)
    plan = SystemPlan(system_id=system.id, kind=system.kind)
    if system.kind != "quantum":
        plan.problem = f"{system.kind} systems arrive in phase 4"
        return plan

    base = system.geometry.base
    spec, params, problem = _check_entry("lattice", base.kind, base.params, system.kind)
    stage = StagePlan("base", None, base.kind, True, spec, params, None, problem)
    stage.key = content_hash({"stage": "base", "kind": base.kind,
                              "params": params if params is not None else base.params})
    stage.applied = problem is None
    if problem:
        plan.problem = f"base lattice: {problem}"
    plan.stages.append(stage)
    key = stage.key

    for op in system.geometry.ops:
        spec, params, problem = _check_entry("geometry_op", op.kind, op.params, system.kind)
        stage = StagePlan("op", op.id, op.kind, op.enabled, spec, params, None, problem)
        stage.applied = op.enabled and problem is None
        if stage.applied:
            key = content_hash({"prev": key, "stage": "op", "kind": op.kind, "params": params})
        stage.key = key
        plan.stages.append(stage)

    regions = {r.id: r for r in system.regions}
    term_stages = []
    for term in system.hamiltonian.terms:
        spec, params, problem = _check_entry("term", term.kind, term.params, system.kind)
        select = None
        if problem is None and term.region is not None:
            if term.region not in regions:
                problem = f"region {term.region!r} does not exist"
            elif not any(isinstance(p, FieldParam) and p.native for p in spec.params):
                problem = (f"{spec.label} cannot be restricted to a region: none of its "
                           f"parameters takes a function of position")
            else:
                try:
                    select = region_tools.normalize(regions[term.region].select)
                except region_tools.RegionError as error:
                    problem = f"region {term.region!r}: {error}"
        stage = StagePlan("term", term.id, term.kind, term.enabled, spec, params, select, problem)
        stage.applied = term.enabled and problem is None
        term_stages.append(stage)

    requested = system.hamiltonian.construction
    needs = {req for s in term_stages if s.applied for req in s.spec.requires}
    nambu = requested.nambu or "nambu" in needs
    has_spin = requested.has_spin or nambu or "spin" in needs
    plan.mode = "nambu" if nambu else ("spinful" if has_spin else "spinless")
    plan.upgraded_by = [s.id for s in term_stages if s.applied and (
        ("spin" in s.spec.requires and not requested.has_spin)
        or ("nambu" in s.spec.requires and not requested.nambu))]
    plan.construction = {"has_spin": has_spin, "nambu": nambu, "tij": list(requested.tij),
                         "is_sparse": requested.is_sparse}
    stage = StagePlan("construction", None, "construction", True, None, plan.construction)
    key = content_hash({"prev": key, "stage": "construction", **plan.construction})
    stage.key, stage.applied = key, True
    plan.stages.append(stage)

    for stage in term_stages:
        if stage.applied:
            key = content_hash({"prev": key, "stage": "term", "kind": stage.kind,
                                "params": stage.params, "region": stage.region})
        stage.key = key
        plan.stages.append(stage)
    return plan


@dataclass
class CalculationPlan:
    calc_id: str
    kind: str
    system_id: str
    spec: object = None
    params: dict | None = None
    problem: str | None = None
    key: str = ""
    system: SystemPlan | None = None


def plan_calculation(document, calc_id):
    calc = document.calculation(calc_id)
    plan = CalculationPlan(calc.id, calc.kind, calc.system)
    try:
        plan.system = plan_system(document, calc.system)
    except DocumentError as error:
        plan.problem = str(error)
        return plan
    system_kind = plan.system.kind
    plan.spec, plan.params, plan.problem = _check_entry("calculation", calc.kind, calc.params,
                                                        system_kind)
    if plan.problem is None and plan.system.problem:
        plan.problem = plan.system.problem
    plan.key = content_hash({"stage": "calculation", "kind": calc.kind,
                             "params": plan.params if plan.params is not None else calc.params,
                             "systems": [plan.system.key]})
    return plan


def calculation_key(document, calc_id):
    return plan_calculation(document, calc_id).key
