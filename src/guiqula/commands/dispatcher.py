"""The dispatcher: the single API that changes the Document (PLAN.md 3.5).

Two kinds of operation (decision 14.7):

- *mutations* change the Document. Each is a pure function applied to a
  deep copy; the dispatcher keeps the before and after snapshots, so undo
  and redo are exact. Registered in guiqula.commands.mutations.
- *actions* do something with the Document without changing it (run or
  cancel a calculation, save, export). They are journaled, not undoable.
  The host (the session, the UI) registers their handlers.

Every operation is appended to the journal as JSON-serializable data and
announced to the listeners, which is what the UI, autosave and the future
remote API bind to. Arguments must be JSON-serializable, so anything the UI
can do can be written down, replayed and sent over a socket.
"""
import inspect
import json
import time

from guiqula.core.document import Document, DocumentError, check

UNDO_LIMIT = 200


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

    def _emit(self, event):
        self.journal.append(dict(event, time=time.time()))
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
        self.document = after
        if merge is not None and merge == self._merge and self._undo:
            self._undo[-1] = (name, args, self._undo[-1][2], after)
        else:
            self._undo.append((name, args, before, after))
        self._merge = merge
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self._emit({"type": "mutation", "name": name, "args": args, "result": result})
        return result

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if not self._undo:
            raise CommandError("nothing to undo")
        self._merge = None
        name, args, before, after = self._undo.pop()
        self._redo.append((name, args, before, after))
        self.document = before
        self._emit({"type": "undo", "name": name, "args": args})

    def redo(self):
        if not self._redo:
            raise CommandError("nothing to redo")
        self._merge = None
        name, args, before, after = self._redo.pop()
        self._undo.append((name, args, before, after))
        self.document = after
        self._emit({"type": "redo", "name": name, "args": args})

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
