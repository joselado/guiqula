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
  stage does, plus everything it references (a term's region selection,
  the regions of its piecewise Fields; other systems and results once
  from_result Fields exist). Keys are DAG-aware (decision 14.9) and hash
  physics only: ids, names and the ui block never enter them. A disabled
  or invalid entry does nothing, so its key is the key before it. The key
  of a calculation is what a result is stamped with; a result whose key
  differs from the current one is stale.
- An entry that runs code from the document (a Python node, PLAN.md
  13.7) is invalid while the document is not trusted: skipped like any
  invalid entry and left out of the keys, so trusting the document makes
  the results that it changes stale. The flag is the Session's, never the
  Document's (a file cannot trust itself); every planner call of the UI
  goes through the Session's helpers so that its keys match the workers'.
- A classical system (decision 13.5) has, after its geometry, a "model"
  stage (the model built on the geometry, seeded: its initial
  configuration is random) and the model's terms; no construction, no
  mean field; its mode is its kind.
- The mean-field block is the last stage of a quantum system. It is
  expensive, so it runs with the calculations only: the interactive
  builds (canvas, outliner) stop before it and report it as deferred.
  They are still stamped with the system's full key, since their reports
  describe the whole plan (a mean-field edit costs them a cache hit).
"""
from dataclasses import dataclass, field

from guiqula.core import fields
from guiqula.core import regions as region_tools
from guiqula.core.document import DocumentError, terms_of
from guiqula.core.hashing import content_hash
from guiqula.registry import base as registry
from guiqula.registry import plugins
from guiqula.registry.params import FieldParam, ParamError

MODES = ("spinless", "spinful", "nambu")
KIND_LABELS = {"classical_spin": "classical spins", "lattice_gas": "lattice gas",
               "ising": "Ising"}
UNTRUSTED = ("Python code of a document opened from a file: it runs once the document is "
             "trusted")


@dataclass
class StagePlan:
    stage: str                  # "base", "op", "construction", "model", "term", "meanfield"
    id: str | None              # entry id (None for base and construction; <system>/meanfield)
    kind: str
    enabled: bool = True
    spec: object = None         # registry EntrySpec
    params: dict | None = None  # normalized parameters
    region: dict | None = None  # normalized region selection
    problem: str | None = None  # why the entry is invalid (skipped)
    key: str = ""
    applied: bool = False       # enabled and valid: the engine runs it
    regions: dict = field(default_factory=dict)   # {id: selection} of its piecewise Fields
    results: dict = field(default_factory=dict)   # {calculation id: ResultRef} it reads
    warnings: list = field(default_factory=list)  # what is worth knowing (a stale result read)
    turn_nambu: bool = False    # the Hamiltonian turns Nambu before this entry (the first
                                # that needs it, as pyqula does in the stack's order)

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

    @property
    def meanfield(self):
        """The mean-field stage, or None (a system that has no Hamiltonian)."""
        return next((s for s in self.stages if s.stage == "meanfield"), None)

    def stage(self, entry_id):
        for s in self.stages:
            if s.id == entry_id:
                return s
        raise KeyError(entry_id)


def _check_entry(family, entry_kind, params, system_kind, trusted=True, plugin=""):
    """Return (spec, normalized params, problem); plugin: the one the
    document records for the entry."""
    try:
        spec = registry.get(family, entry_kind)
    except registry.RegistryError:
        return None, None, plugins.missing(family, entry_kind, plugin)
    if system_kind not in spec.systems:
        return spec, None, f"{spec.label} does not apply to a {system_kind} system"
    try:
        params = spec.normalize_params(params)
    except ParamError as error:
        return spec, None, str(error)
    if spec.runs_code and not trusted:
        return spec, params, UNTRUSTED
    return spec, params, None


def code_entries(document):
    """Ids of the entries that run code from the document (Python nodes)."""
    found = []
    for system in document.systems:
        items = [("geometry_op", op) for op in system.geometry.ops]
        items += [("term", term) for term in terms_of(system)]
        found += [item.id for family, item in items if _runs_code(family, item.kind)]
    return found + [c.id for c in document.calculations if _runs_code("calculation", c.kind)]


def _runs_code(family, kind):
    try:
        return registry.get(family, kind).runs_code
    except registry.RegistryError:
        return False


def _field_regions(spec, params, regions):
    """({id: selection} of the regions the piecewise Fields of an entry
    name, problem or None)."""
    wanted = [r for p in spec.params if isinstance(p, FieldParam)
              for r in fields.regions_of(params[p.name])]
    out = {}
    for region_id in wanted:
        if region_id not in regions:
            return {}, f"region {region_id!r} does not exist"
        try:
            out[region_id] = region_tools.normalize(regions[region_id].select)
        except region_tools.RegionError as error:
            return {}, f"region {region_id!r}: {error}"
    return out, None


def _hashed(params, selections, results=None):
    """Parameters as a key hashes them: region ids replaced by selections,
    calculation ids by the keys of the results read."""
    if selections:
        params = {name: fields.resolve_regions(value, selections) for name, value in params.items()}
    if results:
        keys = {calc: ref.key for calc, ref in results.items()}
        params = {name: fields.resolve_results(value, keys) for name, value in params.items()}
    return params


def _reads(document, system):
    """Ids of the systems whose results a system's Fields read."""
    params = [term.params for term in terms_of(system)]
    if system.hamiltonian is not None:
        params.append(system.hamiltonian.meanfield.params)
    out = set()
    for calc_id in fields.results_of(params):
        try:
            out.add(document.calculation(calc_id).system)
        except DocumentError:
            pass
    return out


def _reaches(document, start, target):
    """Whether system start reads, directly or through others, a result of
    system target."""
    seen, todo = set(), [start]
    while todo:
        current = todo.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        try:
            todo += list(_reads(document, document.system(current)))
        except DocumentError:
            pass
    return False


def _field_results(spec, params, document, system, results, trusted):
    """({calculation id: ResultRef} of the results an entry's from_result
    Fields read, problem or None, warnings)."""
    values = [params[p.name] for p in spec.params if isinstance(p, FieldParam)]
    wanted = fields.results_of(values)
    out, warnings = {}, []
    for calc_id in wanted:
        try:
            calc = document.calculation(calc_id)
        except DocumentError:
            return {}, f"calculation {calc_id!r} does not exist", []
        if calc.system == system.id:
            return {}, (f"{calc_id} runs on this system: a Field cannot read a result of its "
                        f"own system"), []
        if _reaches(document, calc.system, system.id):
            return {}, (f"{calc_id} runs on {calc.system}, which reads results of "
                        f"{system.id}: the references go round in a circle"), []
        ref = (results or {}).get(calc_id)
        if ref is None:
            return {}, f"a Field reads the result of {calc_id}: run {calc_id} first", []
        out[calc_id] = ref
        try:
            if ref.key != calculation_key(document, calc_id, trusted, results):
                warnings.append(f"reads a stale result of {calc_id} (run {calc_id} again)")
        except Exception:
            pass
    for value in values:
        for component in value if isinstance(value, list) else [value]:
            if isinstance(component, dict) and component.get("kind") == "from_result":
                try:
                    fields.site_values(out[component["calculation"]], component["array"],
                                       component["component"])
                except fields.FieldError as error:
                    return {}, f"{component['calculation']}: {error}", []
    return out, None, sorted(set(warnings))


# terms whose pyqula call builds another matrix with sparse storage when its
# Field depends on the position (measured 2026-09-27, PLAN.md phase 5, part 3)
SPARSE_DIFFERS = {"haldane", "rashba", "kane_mele", "anti_kane_mele", "modified_haldane"}


def _field_values(spec, params):
    """The scalar Fields among an entry's parameters (vector components too)."""
    out = []
    for param in spec.params:
        if isinstance(param, FieldParam):
            value = params.get(param.name)
            out += list(value) if isinstance(value, list) else [value]
    return out


def plan_system(document, system_id, trusted=True, results=None):
    """The plan of a system; trusted: whether Python nodes may run;
    results: {calculation id: core.results.ResultRef} of the results the
    from_result Fields may read."""
    system = document.system(system_id)
    plan = SystemPlan(system_id=system.id, kind=system.kind)
    base = system.geometry.base
    spec, params, problem = _check_entry("lattice", base.kind, base.params, system.kind,
                                         plugin=base.plugin)
    stage = StagePlan("base", None, base.kind, True, spec, params, None, problem)
    stage.key = content_hash({"stage": "base", "kind": base.kind,
                              "params": params if params is not None else base.params})
    stage.applied = problem is None
    if problem:
        plan.problem = f"base lattice: {problem}"
    plan.stages.append(stage)
    key = stage.key

    for op in system.geometry.ops:
        spec, params, problem = _check_entry("geometry_op", op.kind, op.params, system.kind,
                                             trusted, op.plugin)
        stage = StagePlan("op", op.id, op.kind, op.enabled, spec, params, None, problem)
        stage.applied = op.enabled and problem is None
        if stage.applied:
            key = content_hash({"prev": key, "stage": "op", "kind": op.kind, "params": params})
        stage.key = key
        plan.stages.append(stage)

    regions = {r.id: r for r in system.regions}
    term_stages = []
    for term in terms_of(system):
        spec, params, problem = _check_entry("term", term.kind, term.params, system.kind,
                                             trusted, term.plugin)
        select = None
        if problem is None and term.region is not None:
            if term.region not in regions:
                problem = f"region {term.region!r} does not exist"
            elif not any(isinstance(p, FieldParam) and p.native for p in spec.params):
                problem = (f"{spec.label} cannot be restricted to a region: none of its "
                           f"parameters takes a function of position")
            elif not spec.regions:
                problem = (f"{spec.label} cannot be restricted to a region: it multiplies what "
                           f"is there, so outside the region it would remove it; use a "
                           f"piecewise Field (one value per region) instead")
            else:
                try:
                    select = region_tools.normalize(regions[term.region].select)
                except region_tools.RegionError as error:
                    problem = f"region {term.region!r}: {error}"
        selections, refs, warnings = {}, {}, []
        if problem is None:
            selections, problem = _field_regions(spec, params, regions)
        if problem is None:
            refs, problem, warnings = _field_results(spec, params, document, system, results,
                                                     trusted)
        stage = StagePlan("term", term.id, term.kind, term.enabled, spec, params, select, problem,
                          regions=selections, results=refs, warnings=warnings)
        stage.applied = term.enabled and problem is None
        term_stages.append(stage)

    if system.model is not None:
        return _plan_classical(plan, system, key, term_stages)
    block = system.hamiltonian.meanfield
    spec, params, problem = _check_entry("meanfield", block.kind, block.params, system.kind,
                                         plugin=block.plugin)
    selections, refs, warnings = {}, {}, []
    if problem is None:
        selections, problem = _field_regions(spec, params, regions)
    if problem is None:
        refs, problem, warnings = _field_results(spec, params, document, system, results, trusted)
    meanfield = StagePlan("meanfield", f"{system.id}/meanfield", block.kind, block.enabled, spec,
                          params, None, problem, regions=selections, results=refs,
                          warnings=warnings)
    meanfield.applied = block.enabled and problem is None
    term_stages.append(meanfield)

    requested = system.hamiltonian.construction
    needs = {req for s in term_stages if s.applied for req in s.spec.requires_of(s.params)}
    nambu = requested.nambu or "nambu" in needs
    has_spin = requested.has_spin or nambu or "spin" in needs
    plan.mode = "nambu" if nambu else ("spinful" if has_spin else "spinless")
    plan.upgraded_by = [s.id for s in term_stages if s.applied and (
        ("spin" in s.spec.requires_of(s.params) and not requested.has_spin)
        or ("nambu" in s.spec.requires_of(s.params) and not requested.nambu))]
    # spin is set before the first term; Nambu before the first entry that needs it (unless
    # the construction asks for it): the terms above a pairing term are applied as pyqula
    # applies them in this order, and some of them (a spin spiral, Kekule hopping) cannot
    # take a Nambu Hamiltonian
    plan.construction = {"has_spin": has_spin, "nambu": requested.nambu,
                         "tij": list(requested.tij), "is_sparse": requested.is_sparse}
    if nambu and not requested.nambu:
        next(s for s in term_stages if s.applied
             and "nambu" in s.spec.requires_of(s.params)).turn_nambu = True
    if requested.is_sparse:
        for term in term_stages:
            if term.applied and term.kind in SPARSE_DIFFERS and (term.region is not None or any(
                    not fields.is_constant(v) for v in _field_values(term.spec, term.params))):
                term.warnings = term.warnings + [
                    "pyqula builds this coupling differently with sparse matrices when it "
                    "depends on the position (not Hermitian for the Haldane coupling); build "
                    "the Hamiltonian dense (construction) to trust it"]
    stage = StagePlan("construction", None, "construction", True, None, plan.construction)
    key = content_hash({"prev": key, "stage": "construction", **plan.construction})
    stage.key, stage.applied = key, True
    plan.stages.append(stage)

    for stage in term_stages:
        if stage.applied:
            key = content_hash({"prev": key, "stage": stage.stage, "kind": stage.kind,
                                "params": _hashed(stage.params, stage.regions, stage.results),
                                "region": stage.region,
                                **({"turn_nambu": True} if stage.turn_nambu else {})})
        stage.key = key
        plan.stages.append(stage)
    return plan


def _plan_classical(plan, system, key, term_stages):
    """The model stage and the terms of a classical system."""
    model = system.model
    spec, params, problem = _check_entry("model", model.kind, model.params, system.kind,
                                         plugin=model.plugin)
    stage = StagePlan("model", f"{system.id}/model", model.kind, True, spec, params, None,
                      problem)
    if problem:
        plan.problem = f"model: {problem}"
    stage.applied = problem is None
    key = content_hash({"prev": key, "stage": "model", "kind": model.kind,
                        "params": params if params is not None else model.params})
    stage.key = key
    plan.stages.append(stage)
    plan.mode = KIND_LABELS.get(system.kind, system.kind)
    for stage in term_stages:
        if stage.applied:
            key = content_hash({"prev": key, "stage": stage.stage, "kind": stage.kind,
                                "params": _hashed(stage.params, stage.regions, stage.results),
                                "region": stage.region,
                                **({"turn_nambu": True} if stage.turn_nambu else {})})
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


def plan_calculation(document, calc_id, trusted=True, results=None):
    calc = document.calculation(calc_id)
    plan = CalculationPlan(calc.id, calc.kind, calc.system)
    try:
        plan.system = plan_system(document, calc.system, trusted, results)
    except DocumentError as error:
        plan.problem = str(error)
        return plan
    system_kind = plan.system.kind
    plan.spec, plan.params, plan.problem = _check_entry("calculation", calc.kind, calc.params,
                                                        system_kind, trusted, calc.plugin)
    if plan.problem is None and plan.system.problem:
        plan.problem = plan.system.problem
    inner = None
    if plan.problem is None and plan.spec.document_level:
        plan.problem, inner = _plan_sweep(document, calc, plan.params, trusted, results)
    params = plan.params if plan.params is not None else calc.params
    if inner is not None:              # a sweep: ids out, the key of what it runs in
        params = {k: v for k, v in params.items() if k != "calculation"}
    plan.key = content_hash({"stage": "calculation", "kind": calc.kind, "params": params,
                             "systems": [plan.system.key], "inner": inner})
    return plan


def _owner(document, target):
    """The system a swept parameter belongs to."""
    if "/" in target:
        return target.split("/", 1)[0]
    family, owner, _, _, obj = document.find(target)
    if family == "system":
        return obj.id
    if family == "calculation":
        return obj.system
    return owner.id


def _plan_sweep(document, calc, params, trusted, results):
    """(problem or None, key of the calculation it runs) of a sweep."""
    from guiqula.registry import sweeps
    inner_id = params["calculation"]
    try:
        inner = document.calculation(inner_id)
    except DocumentError:
        return f"it runs {inner_id!r}, which is not a calculation of the document", None
    if inner.id == calc.id or registry.get("calculation", inner.kind).document_level:
        return "a sweep runs a calculation, not a sweep", None
    if inner.system != calc.system:
        return f"{inner_id} runs on {inner.system}, the sweep on {calc.system}", None
    axes = [(params["entry"], params["param"], params["component"])]
    if params["entry2"]:
        axes.append((params["entry2"], params["param2"], params["component2"]))
    for target, param, component in axes:
        problem = sweeps.check_target(document, target, param, component)
        if problem:
            return problem, None
        if _owner(document, target) != calc.system:
            return f"{target} is not part of {calc.system}, which the sweep runs on", None
    inner_plan = plan_calculation(document, inner_id, trusted, results)
    if inner_plan.problem:
        return f"{inner_id}: {inner_plan.problem}", None
    return None, inner_plan.key


def calculation_key(document, calc_id, trusted=True, results=None):
    return plan_calculation(document, calc_id, trusted, results).key


def result_references(document, system_id=None):
    """Ids of the calculations whose results the document's Fields read
    (of one system's Fields, given its id)."""
    params = []
    for system in document.systems:
        if system_id is not None and system.id != system_id:
            continue
        params += [term.params for term in terms_of(system)]
        if system.hamiltonian is not None:
            params.append(system.hamiltonian.meanfield.params)
    return sorted(set(fields.results_of(params)))
