"""What an undo step is called (PLAN.md phase 5, design item 10): the Edit
menu names the step Undo and Redo would take ("Undo set m of t1"), and the
undo history lists the steps. Also which entry a step touched, so the
selection can follow an undo.

describe() gets the mutation's name and arguments and the Document before
the step (the entry a removal deleted is still there to be named).
"""
from guiqula.registry import base as registry

FAMILY_OF_COMMAND = {"add_geometry_op": "geometry_op", "add_term": "term",
                     "add_calculation": "calculation", "add_system": "lattice"}
PARAM_NOUN = {"set_param": "set", "set_params": "change"}


def _label(family, kind):
    try:
        return registry.get(family, kind).label
    except registry.RegistryError:
        return kind


def _entry_name(document, entry):
    """"t1 (Zeeman / exchange field)" when the entry is found, else the id."""
    try:
        found = document.find(entry)
    except Exception:
        return str(entry)
    family, obj = found[0], found[-1]
    if family in ("system", "region") and getattr(obj, "name", "") not in ("", entry):
        return f"{entry} ({obj.name})"
    kind = getattr(obj, "kind", None)
    registry_family = {"op": "geometry_op", "term": "term",
                       "calculation": "calculation"}.get(family)
    if registry_family and kind:
        return f"{entry} ({_label(registry_family, kind).lower()})"
    return str(entry)


def describe(name, args, document):
    """A short text for an undo step."""
    entry = args.get("entry")
    if name == "add_system":
        kind = args.get("kind", "quantum")
        what = "system" if kind == "quantum" else kind.replace("_", " ") + " system"
        return f"new {what} on the {_label('lattice', args.get('lattice', '')).lower()}"
    if name in FAMILY_OF_COMMAND:
        noun = {"add_geometry_op": "op", "add_term": "term",
                "add_calculation": "calculation"}[name]
        return f"add {noun} {_label(FAMILY_OF_COMMAND[name], args.get('kind', '')).lower()}"
    if name == "add_region":
        return "add a region" + (f" {args['name']}" if args.get("name") else "")
    if name == "set_param":
        return f"set {args.get('name')} of {entry}"
    if name == "set_params":
        return f"change {', '.join(sorted(args.get('params', {}))) or 'the parameters'} of {entry}"
    if name == "set_enabled":
        return f"{'enable' if args.get('enabled') else 'disable'} {entry}"
    if name == "remove":
        return f"remove {_entry_name(document, entry)}"
    if name == "duplicate":
        return f"duplicate {_entry_name(document, entry)}"
    if name == "move":
        return f"move {entry}"
    if name == "rename":
        return f"rename {entry}"
    if name == "set_region":
        return f"restrict {entry} to {args['region']}" if args.get("region") else \
            f"lift the region of {entry}"
    if name == "set_selection":
        return f"change the sites of {entry}"
    if name == "set_lattice":
        return f"set the lattice of {args.get('system')} to " \
               f"{_label('lattice', args.get('lattice', '')).lower()}"
    if name == "set_construction":
        return f"change how the Hamiltonian of {args.get('system')} is built"
    if name == "set_meanfield":
        return f"change the mean field of {args.get('system')}"
    if name == "set_model":
        return f"change the model of {args.get('system')}"
    if name == "set_notes":
        return "edit the notes"
    if name == "lock":
        return f"lock {args.get('target')}"
    if name == "unlock":
        return f"unlock {args['target']}" if args.get("target") else "unlock everything"
    return name.replace("_", " ")


def touched(name, args, result):
    """The entry a step changed (a new entry's id, the entry it names, its
    system), for the selection to follow an undo or a redo; and the system,
    for when the entry no longer exists."""
    entry = result if isinstance(result, str) and name.startswith(("add_", "duplicate")) \
        else args.get("entry") or args.get("system")
    return entry, args.get("system")
