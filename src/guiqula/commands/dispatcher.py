"""The dispatcher: the single API that changes the Document (PLAN.md 3.5).

Two kinds of operation (decision 14.7):

- *mutations* change the Document. Each is a pure function applied to a
  deep copy; the dispatcher keeps the before and after snapshots, so undo
  and redo are exact. Registered in guiqula.commands.mutations.
- *actions* do something with the Document without changing it (run or
  cancel a calculation, save, export). They are journaled, not undoable.
  The host (the session, the UI) registers their handlers.

Each undo step keeps the Document before and after it, a short text
(commands/steps.py: "set m of t1", which the Edit menu and the undo
history show) and the entry it touched. undo(steps) and redo(steps) take
several steps at once, as one event. A mutation that changes what a lock
of the Document covers (core/locks.py) is refused, whichever it is.

Every operation is appended to the journal as JSON-serializable data and
announced to the listeners, which is what the UI, autosave and the future
remote API bind to. Arguments must be JSON-serializable, so anything the UI
can do can be written down, replayed and sent over a socket. The journal
keeps the last JOURNAL_LIMIT operations, and a merged mutation (a slider
drag, a brush stroke) replaces the one it joins, so a stroke that sets a
painted Field of every site at each mouse move keeps one copy, not one per
move.
"""
import inspect
import json
import time

from guiqula.commands import steps as step_texts
from guiqula.core import locks
from guiqula.core.document import Document, DocumentError, check

UNDO_LIMIT = 200
JOURNAL_LIMIT = 1000      # operations the journal keeps


class CommandError(ValueError):
    """A command was refused; the Document is unchanged."""


MUTATIONS = {}


def mutation(function):
    """Register ``function(document, **args) -> result`` as a mutation. It
    receives a private deep copy and may change it freely."""
    MUTATIONS[function.__name__] = function
    return function


def _signature(function, skip=1):
    params = list(inspect.signature(function).parameters.values())[skip:]
    return [p.name + ("" if p.default is inspect.Parameter.empty else f"={p.default!r}")
            for p in params]


class Dispatcher:
    def __init__(self, document=None):
        from guiqula.commands import mutations  # noqa: F401  (registers them)
        self.document = document.copy_deep() if document is not None else Document()
        check(self.document)
        self._undo = []
        self._redo = []
        self._merge = None       # the merge key of the last mutation (do_merged)
        self._merges = 0         # merged steps started: tags their journal records
        self._actions = {}
        self._listeners = []
        self.journal = []

    # ---- introspection
    def mutations(self):
        return {name: _signature(f) for name, f in sorted(MUTATIONS.items())}

    def actions(self):
        return {name: _signature(f, skip=0) for name, f in sorted(self._actions.items())}

    # ---- listeners
    def subscribe(self, listener):
        """listener(event) with event a dict: {"type": "mutation" | "undo" |
        "redo" | "action" | "reset", "name": ..., "args": ..., "result": ...}"""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _emit(self, event, merge=None):
        record = dict(event, time=time.time())
        if merge is not None:
            record["merge"] = merge
            if self.journal and self.journal[-1].get("merge") == merge:
                self.journal.pop()           # the mutation this one joins
        self.journal.append(record)
        del self.journal[:-JOURNAL_LIMIT]
        for listener in list(self._listeners):
            listener(event)

    # ---- mutations
    def do(self, name, /, **args):
        """Apply a mutation; returns its result (e.g. the id of a new entry)."""
        return self._do(name, args, None)

    def do_merged(self, key, name, /, **args):
        """A mutation that joins the one before it into a single undo step
        when both were done with the same key (the steps of a slider
        drag): undo goes back to before the first of them."""
        return self._do(name, args, key)

    def end_merge(self):
        """The next mutation starts an undo step of its own (a slider was
        released)."""
        self._merge = None

    def _do(self, name, args, merge):
        function = MUTATIONS.get(name)
        if function is None:
            raise CommandError(f"unknown command {name!r}; known: {sorted(MUTATIONS)}")
        _require_json(name, args)
        before = self.document
        after = before.copy_deep()
        try:
            result = function(after, **args)
            check(after)
        except (CommandError, DocumentError, ValueError, KeyError, TypeError) as error:
            raise CommandError(f"{name}: {_message(error)}") from None
        broken = locks.violations(before, after)
        if broken:
            raise CommandError(f"{name}: {', '.join(broken)} {'is' if len(broken) == 1 else 'are'}"
                               f" locked (unlock with the unlock command, or Edit > Unlock "
                               f"everything)")
        self.document = after
        merged = merge is not None and merge == self._merge and bool(self._undo)
        if merged:
            self._undo[-1] = dict(self._undo[-1], after=after)
        else:
            try:
                text = step_texts.describe(name, args, before)
            except Exception:           # a text must never refuse a mutation
                text = name.replace("_", " ")
            entry, system = step_texts.touched(name, args, result)
            self._undo.append({"name": name, "args": args, "before": before, "after": after,
                               "text": text, "entry": entry, "system": system})
            self._merges += merge is not None
        self._merge = merge
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self._emit({"type": "mutation", "name": name, "args": args, "result": result},
                   merge=None if merge is None else (merge, self._merges))
        return result

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo_text(self):
        """The step undo() would take back, or None."""
        return self._undo[-1]["text"] if self._undo else None

    def redo_text(self):
        return self._redo[-1]["text"] if self._redo else None

    def history(self):
        """{"undo": [texts, newest first], "redo": [texts, next first]}."""
        return {"undo": [step["text"] for step in reversed(self._undo)],
                "redo": [step["text"] for step in reversed(self._redo)]}

    def undo(self, steps=1):
        """Take back the last steps (one event); raises when there are fewer."""
        self._step(self._undo, self._redo, steps, "undo", "before")

    def redo(self, steps=1):
        self._step(self._redo, self._undo, steps, "redo", "after")

    def _step(self, source, target, steps, kind, side):
        if steps < 1 or steps > len(source):
            raise CommandError(f"nothing to {kind}" if not source else
                               f"cannot {kind} {steps} steps; there are {len(source)}")
        self._merge = None
        for _ in range(steps):
            step = source.pop()
            target.append(step)
        self.document = step[side]
        self._emit({"type": kind, "name": step["name"], "args": step["args"], "steps": steps,
                    "text": step["text"], "entry": step["entry"], "system": step["system"]})

    def reset(self, document):
        """Replace the whole Document (new, open, recover); clears undo."""
        self._merge = None
        document = document.copy_deep()
        check(document)
        self.document = document
        self._undo.clear()
        self._redo.clear()
        self._emit({"type": "reset", "name": "reset", "args": {}})

    # ---- actions
    def register_action(self, name, handler):
        """handler(**args) -> result; replaces an earlier handler."""
        self._actions[name] = handler

    def act(self, name, /, **args):
        handler = self._actions.get(name)
        if handler is None:
            raise CommandError(f"unknown action {name!r}; known: {sorted(self._actions)}")
        _require_json(name, args)
        result = handler(**args)
        self._emit({"type": "action", "name": name, "args": args,
                    "result": result if _is_json(result) else None})
        return result

    def run(self, name, /, **args):
        """do() for a mutation, act() for an action: one entry point for
        drivers that do not care which kind a name is."""
        if name in MUTATIONS:
            return self.do(name, **args)
        return self.act(name, **args)


def _message(error):
    text = str(error)
    return text.strip("\"'") if isinstance(error, KeyError) else text


def _is_json(value):
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


def _require_json(name, args):
    if not _is_json(args):
        raise CommandError(f"{name}: arguments must be JSON-serializable")
