"""Locked parameters (decision 13.16's presets with locked parameters;
PLAN.md phase 5, design item 12): a teacher locks what the students should
leave alone, so that they change the rest. A guide, not a protection:
unlocking is one command (the ``unlock`` mutation, Edit > Unlock
everything), and the lock list is part of the Document, saved with it.

A lock (a string in ``Document.locks``) names
- an entry (a system, op, term, region or calculation): all of it;
- a parameter of one, ``"t1.m"`` (of a system: its base lattice's,
  ``"s1.n"``);
- a system's geometry, ``"s1/geometry"``: its lattice and its ops.

A lock of a calculation, or of its k-path parameter, covers the vertices
of the k-path it walks as well (phase 9, decision 234): a k-path is shared,
so an edit of it through another calculation, the zone window or a pick
changes the locked calculation too, and is refused.

The dispatcher refuses any mutation that changes what a lock covers,
comparing the Document before and after it (violations()), so every
mutation is covered, including those written later. lock and unlock are
mutations, so undo takes them back.
"""


class LockError(ValueError):
    pass


class _Missing:
    def __repr__(self):
        return "MISSING"


MISSING = _Missing()


def value(document, target):
    """The JSON of what a lock covers in a Document, or MISSING."""
    head, _, param = target.partition(".")
    system_id, slash, block = head.partition("/")
    if slash:
        if block != "geometry" or param:
            return MISSING
        system = next((s for s in document.systems if s.id == system_id), None)
        return MISSING if system is None else system.geometry.model_dump(mode="json")
    try:
        found = document.find(head)
    except Exception:
        return MISSING
    family, obj = found[0], found[-1]
    if not param:
        data = obj.model_dump(mode="json")
        if family == "calculation":
            data["kpaths"] = _walked(document, obj.params.values())
        return data
    params = obj.geometry.base.params if family == "system" else getattr(obj, "params", None)
    if not isinstance(params, dict) or param not in params:
        return MISSING
    if family == "calculation" and _walked(document, [params[param]]):
        return [params[param], _walked(document, [params[param]])]
    return params[param]


def _walked(document, values):
    """{id: vertices} of the k-paths among these parameter values."""
    kpaths = {k.id: k.vertices for k in document.kpaths}
    return {v: kpaths[v] for v in values if isinstance(v, str) and v in kpaths}


def check_target(document, target):
    """Raise LockError unless the target names something of the Document."""
    if not isinstance(target, str) or value(document, target) is MISSING:
        raise LockError(f"nothing to lock called {target!r}: name an entry (t1), a parameter "
                        f"of one (t1.m, s1.n for a lattice's) or a geometry (s1/geometry)")


def covering(locks, entry, param=None):
    """The locks among these that cover an entry, or one of its parameters
    (the entry's own lock, the parameter's; for an op or a lattice
    parameter, the geometry lock of its system is reported by the caller,
    which knows the system)."""
    out = [lock for lock in locks if lock == entry]
    if param is not None:
        out += [lock for lock in locks if lock == f"{entry}.{param}"]
    return out


def violations(before, after):
    """The locks of the Document before a mutation whose content the
    mutation changed (or removed)."""
    return [lock for lock in before.locks if value(before, lock) != value(after, lock)]
