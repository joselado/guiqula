"""The help of an outliner item (decision 13.13, open point 3): put together
from what exists, never written again in guiqula.

For a registry entry: its label, group and one-line doc, its formula, the
Hilbert space it needs, its parameters (from the declarations), the pyqula
code it runs with the current values (quantum-lattice's "pyqula code"
view), the docstrings of the pyqula calls behind it (docstrings.py), the
sections of pyqula's user guide it names (``guide=``) and the reference
section of each of its calls ("h.add_zeeman()"), in full, and links to the
other sections whose code calls them. Items that are guiqula's own (a
system, a region, the calculations) show a section of guiqula's user guide.
Everything is Markdown with $...$ equations; ui/help.py draws it.
"""
from pathlib import Path
from urllib.parse import quote

from guiqula import vendoring
from guiqula.docs import docstrings, guide as guides
from guiqula.registry import base as registry

GUIQULA = "guiqula: "
GUIQULA_GUIDE = Path(__file__).resolve().parent / "user_guide.md"
REFERENCE = "Main functions and methods"
SHORT = {"classicalspin.SpinModel": "sm", "latticegas.LatticeGas": "lg",
         "latticeising.LatticeIsing": "li"}
FAMILY_NAMES = {"lattice": "lattice", "geometry_op": "geometry op", "term": "term",
                "meanfield": "mean field", "model": "classical model",
                "calculation": "calculation"}
# outliner items that are guiqula's own, and the section of its guide on them
OWN_SECTIONS = {"system": "Systems and geometry", "region": "Selections and regions",
                "calculations": "Calculations and results", "geometry": "Systems and geometry",
                "regions": "Selections and regions", "hamiltonian": "Terms and the Hamiltonian",
                "model_stack": "Classical systems"}
MORE = 8     # links to further sections whose code calls an entry's pyqula function


def pyqula_targets(spec):
    """The pyqula calls behind an entry: its Call's target, and what a
    custom entry declares (``pyqula=``)."""
    targets = list(spec.pyqula)
    if spec.call is not None and spec.call.target not in targets:
        targets.insert(0, spec.call.target)
    return targets


def pyqula_guide():
    """pyqula's user guide that goes with the pyqula in use, or None."""
    found = vendoring.find_guide()
    return guides.load(found[1]) if found else None


def guiqula_guide():
    return guides.load(GUIQULA_GUIDE)


def split(anchor):
    """(which guide, anchor): "guiqula: X" names guiqula's own guide."""
    if anchor.startswith(GUIQULA):
        return "guiqula", anchor[len(GUIQULA):]
    return "pyqula", anchor


def guide_of(which):
    return guiqula_guide() if which == "guiqula" else pyqula_guide()


def link(which, anchor, text=None):
    return f"[{text or anchor}](help:{which}/{quote(anchor, safe='')})"


def section_text(which, guide, anchor):
    """A section as the help shows it: in full, but a chapter (a top-level
    section with sections of its own, some hundreds of lines long) as its
    introduction and links to its sections."""
    section = guide.find(anchor)
    children = guide.children(anchor)
    if section.level > 1 or not children:
        return guide.text(anchor)
    return guide.own_text(anchor) + "\nIts sections: " + ", ".join(
        link(which, c.anchor, c.title) for c in children) + ".\n"


def reference_anchor(guide, target):
    """The heading of the guide's reference chapter on a call ("h.add_zeeman()",
    "sm.add_heisenberg()"), or None."""
    name = target
    for prefix, short in SHORT.items():
        if target.startswith(prefix + "."):
            name = f"{short}.{target[len(prefix) + 1:]}"
    wanted = f"{name}()"
    for section in guide.sections:
        if section.level >= 3 and wanted in [part.strip() for part in section.title.split(" / ")]:
            return section.anchor
    return None


def entry_anchors(spec, guide):
    """The sections of pyqula's guide an entry's help shows in full: those it
    names, then the reference sections of its calls."""
    anchors = [split(a)[1] for a in spec.guide if split(a)[0] == "pyqula"]
    for target in pyqula_targets(spec):
        reference = reference_anchor(guide, target) if guide else None
        if reference and reference not in anchors:
            anchors.append(reference)
    return anchors


def _parameters(spec):
    rows = ["| parameter | meaning | default |", "|---|---|---|"]
    for param in spec.params:
        meaning = param.doc or param.label
        if getattr(param, "native", True) is False:
            meaning += " (a constant: pyqula takes a number)"
        default = param.default if not isinstance(param.default, str) or "\n" not in \
            param.default else "(code)"
        rows.append(f"| `{param.name}` ({param.label}) | {meaning} | `{default}` |"
                    .replace("\n", " "))
    return "\n".join(rows) if spec.params else ""


def _code(spec, stage=None):
    """The pyqula lines an entry runs, with its current values (a stage of a
    plan: its parameters, regions and results) or its defaults."""
    from guiqula.io.script import ScriptContext, call_code
    if stage is not None and stage.params is not None:
        ctx = ScriptContext(spec, stage.params, region=getattr(stage, "region", None),
                            regions=getattr(stage, "regions", None),
                            results=getattr(stage, "results", None))
    else:
        ctx = ScriptContext(spec, spec.normalize_params({}))
    if spec.call is not None:
        return [call_code(spec, ctx)]
    lines = spec.script(ctx)
    return list(lines) if isinstance(lines, (list, tuple)) else [str(lines)]


def entry_help(spec, stage=None):
    """The help of a registry entry as Markdown."""
    guide = pyqula_guide()
    parts = [f"# {spec.label}",
             f"*{FAMILY_NAMES.get(spec.family, spec.family)}"
             + (f" · {spec.group}" if spec.group else "") + f"* · `{spec.kind}`"]
    if spec.doc:
        parts.append(spec.doc)
    if spec.formula:
        parts.append(f"$${spec.formula}$$")
    needs = spec.requires_of(stage.params) if stage is not None and stage.params else \
        (spec.requires if not callable(spec.requires) else ())
    if needs:
        parts.append("Makes the Hamiltonian " + " and ".join(
            {"spin": "spinful", "nambu": "Nambu"}.get(n, n) for n in needs) + ".")
    if spec.runs_code:
        parts.append("Python code: it runs only in a trusted document "
                     + link("guiqula", "Python nodes, trust and the console", "(trust)") + ".")
    table = _parameters(spec)
    if table:
        parts += ["## Parameters", table]
    try:
        code = _code(spec, stage)
    except Exception as error:          # an entry whose values cannot be written yet
        code = [f"# ({type(error).__name__}: {error})"]
    if code:
        parts += ["## pyqula code", "```python\n" + "\n".join(code) + "\n```"]
    for target in pyqula_targets(spec):
        text = docstrings.docstring(target)
        parts.append(f"## pyqula: {target}")
        parts.append("```\n" + text + "\n```" if text else "(pyqula gives this function "
                                                            "no docstring)")
    shown = set()
    if guide is not None:
        for anchor in entry_anchors(spec, guide):
            try:
                parts.append(section_text("pyqula", guide, anchor))
                shown.add(anchor)
            except guides.GuideError as error:
                parts.append(f"*{error}*")
        more = []
        for target in pyqula_targets(spec):
            name = target.rsplit(".", 1)[-1]
            more += [a for a in guide.calls(name) if a not in shown and a not in more]
        if more:
            parts.append("Also in pyqula's user guide: " + ", ".join(
                link("pyqula", a) for a in more[:MORE]) + ".")
    own = [split(a)[1] for a in spec.guide if split(a)[0] == "guiqula"]
    if own:
        parts.append("In guiqula's user guide: " + ", ".join(link("guiqula", a) for a in own)
                     + ".")
    parts.append(source_note())
    return "\n\n".join(parts) + "\n"


def source_note():
    found = vendoring.find_guide()
    try:
        package = docstrings.package_dir()
    except vendoring.VendoringError as error:
        return f"*pyqula not found: {error}*"
    where = f"{found[1]} ({found[0]} copy)" if found else "not found"
    return f"*From pyqula at {package}; its user guide: {where}.*"


def section_page(which, anchor):
    """A section of a guide as Markdown, with links to its subsections."""
    guide = guide_of(which)
    if guide is None:
        return "pyqula's user guide was not found.\n"
    return section_text(which, guide, anchor) + "\n" + source_note() + "\n"


def contents(which):
    """The table of contents of a guide, as links."""
    guide = guide_of(which)
    if guide is None:
        return "pyqula's user guide was not found.\n"
    title = "pyqula user guide" if which == "pyqula" else "guiqula user guide"
    lines = [f"# {title}", ""]
    for section in guide.sections:
        if section.level == 1 and section.title.lower() == title or section.title == "Contents":
            continue
        indent = "  " * max(section.level - 1, 0)
        if section.level <= 3:
            lines.append(f"{indent}- {link(which, section.anchor, section.title)}")
    return "\n".join(lines) + "\n"


def item_help(session, item_id):
    """(title, Markdown) of the help of an outliner item."""
    document = session.document
    if not item_id:
        return "guiqula", contents("guiqula")
    if item_id == "calculations":
        return "Calculations", section_page("guiqula", OWN_SECTIONS["calculations"])
    system_id, slash, part = item_id.partition("/")
    if slash:
        system = document.system(system_id)
        if part == "base":
            spec = registry.get("lattice", system.geometry.base.kind)
            return spec.label, entry_help(spec, _stage(session, system_id, None, "base"))
        if part == "meanfield" and system.hamiltonian is not None:
            spec = registry.get("meanfield", system.hamiltonian.meanfield.kind)
            return spec.label, entry_help(spec, _stage(session, system_id, item_id))
        if part == "model" and system.model is not None:
            spec = registry.get("model", system.model.kind)
            return spec.label, entry_help(spec, _stage(session, system_id, None, "model"))
        section = OWN_SECTIONS.get(part, "Systems and geometry")
        return section, section_page("guiqula", section)
    family, owner, _, _, obj = document.find(item_id)
    if family in ("system", "region"):
        return OWN_SECTIONS[family], section_page("guiqula", OWN_SECTIONS[family])
    registry_family = {"op": "geometry_op", "term": "term", "calculation": "calculation"}[family]
    spec = registry.get(registry_family, obj.kind)
    if family == "calculation":
        try:
            stage = session.plan_calculation(item_id)
            stage = type("Stage", (), {"params": stage.params, "region": None,
                                       "regions": {}, "results": {}})()
        except Exception:
            stage = None
        return spec.label, entry_help(spec, stage)
    return spec.label, entry_help(spec, _stage(session, owner.id, item_id))


def _stage(session, system_id, entry_id, stage_kind=None):
    try:
        plan = session.plan_system(system_id)
    except Exception:
        return None
    for stage in plan.stages:
        if (entry_id is not None and stage.id == entry_id) or \
                (stage_kind is not None and stage.stage == stage_kind):
            return stage
    return None


def anchor_problems():
    """Anchors named by registry entries that a guide lacks (the tests and
    tools/update_vendor.sh report them)."""
    problems = []
    for spec in registry.entries():
        for anchor in spec.guide:
            which, name = split(anchor)
            guide = guide_of(which)
            try:
                guide.find(name)
            except (guides.GuideError, AttributeError) as error:
                problems.append(f"{spec.family} {spec.kind}: {error}")
    return problems


