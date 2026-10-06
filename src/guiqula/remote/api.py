"""The methods of the remote API (PLAN.md 3.7): what a client of the
server (remote/server.py) or of the MCP bridge (remote/mcp.py) can ask of
a running guiqula. Everything goes through the Session, as for the window
and tools/drive.py: a command is a dispatcher mutation or action, so it is
undoable, journaled, refused by locks, and seen by the window at once.

Methods (parameters as keywords; every reply is JSON):

- ``hello``: who answers (the server calls it once the token is checked);
- ``status``: the outline: systems with their entries, builds and invalid
  entries, calculations with their status and estimates, undo steps, the
  window's state;
- ``document``: the Document as JSON;
- ``commands``: the mutations and actions with their parameters;
- ``catalogue``: registry entries (lattices, ops, terms, calculations...)
  with their parameters, filtered by family, system kind or a search;
- ``do``: a command (``command``, ``args``), then waits for the builds it
  causes (``settle``), so the reply says what the new geometry is; an
  action that waits for its job (``console``, ``run_calculation`` with
  ``wait``) only starts it, and the reply waits for the job instead (at
  most ``timeout`` seconds), so the host goes on serving meanwhile;
- ``run``: runs a calculation, waiting for it (``wait``, ``timeout``);
  ``wait``: waits for a calculation already running; ``cancel``;
- ``result``: a result's summary, its arrays' shapes and ranges, and the
  values of the arrays asked for (at most ``max_values`` numbers each:
  longer arrays are thinned along their first axis);
- ``plot``: the figure of a result as a PNG (base64), its title marking a
  result that is not current as the window's tab does, and its state;
- ``screenshot``: the window or one of its widgets as a PNG (base64);
  ``widgets``: the names a screenshot accepts (both need the window);
- ``help``: an item's, an entry's or a guide section's help, as Markdown;
- ``script``: the pyqula script of a calculation;
- ``console``: Python in the console worker (g, h, doc, np, pyqula);
- ``journal``: the last commands and actions, and the window's log.

Without a window (``guiqula serve``, the MCP bridge's own Session) the API
asks for the builds itself after every change, as the window would.
Qt-free, except for the figure of ``plot``, drawn with matplotlib's Agg
through ui/plots.py, which is imported only then.
"""
import base64
import io
import math

import numpy as np

import guiqula
from guiqula import registry, vendoring
from guiqula.registry import pipeline, plugins
from guiqula.core.document import terms_of
from guiqula.remote.server import INVALID_PARAMS, NO_METHOD, Pending, RemoteError

LONGEST_WAIT = 3600.0      # seconds: no request waits longer (remote/client.py knows it)
WAITING = ("do", "run", "wait", "console")      # the methods that may wait (client.py too)
METHODS = ("hello", "status", "document", "commands", "catalogue", "do", "run", "wait",
           "cancel", "result", "plot", "screenshot", "widgets", "help", "script", "console",
           "journal")
MAX_VALUES = 5000          # numbers per array a result reply carries by default
# the Session's actions that can wait for the job they start, with the default of their
# wait (session.py): do starts the job, and its reply waits for it (a Pending)
JOB_ACTIONS = {"console": True, "run_calculation": False}
# the window's own actions (ui/mainwindow.py registers them; tests/remote checks the list),
# with their parameters, for the command tool's description
WINDOW_ACTIONS = {
    "select": "entry: the outliner item to select and show",
    "workspace": "name: geometry, hamiltonian or calculate",
    "tool": "name: the canvas tool, pick, box or lasso",
    "select_sites": "mode=replace|add|toggle|remove and one of indices, box=[x0, y0, x1, y1], "
                    "polygon=[[x, y], ...], point=[x, y], positions, sublattice=1|-1, "
                    "edge=true, all=true",
    "region_from_selection": "name: a region of the selected sites",
    "remove_selected": "removes the selected sites (a geometry op)",
    "canvas_view": "name: structure, hamiltonian or field",
    "preview": "entry, param: a term's Field drawn on the structure",
    "auto_rerun": "enabled: re-run cheap stale results",
    "projection": "name: auto, xy or 3d (how the canvas and the results on the atoms draw "
                  "the geometry)",
    "overlay": "calc, other (None clears), mode=overlay|difference: two results on one axes",
    "plot_style": "calculation, reset=false and the options of its plot kind (lines: "
                  "linewidth, color, dots, fill; colored_scatter: size, cmap, saturate; "
                  "heatmap: cmap, saturate, smooth; structure_scalar: atom_size, cmap, "
                  "bonds; structure_vector: arrow_length, arrow_width, arrow_color, "
                  "atom_size, cmap, bonds): how the result is drawn, kept with the project "
                  "and used by export_bundle; returns what differs from the defaults",
    "paint": "value, indices or point=[x, y] and radius, entry, param, component: paint a "
             "Field on sites",
    "slider": "entry, param, component, minimum, maximum, on (a calculation: drawn on its "
              "plot as a marker)",
    "set_slider": "index, value",
    "remove_slider": "index",
    "theme": "name: system, light or dark",
    "export_bundle": "calculation, path: figure, data and script in one folder",
    "help": "entry, or guide (pyqula, guiqula, plugins) and anchor, or search (a question "
            "in words): show help in the Help dock; search lists the entries and guide "
            "sections that answer it",
    "remote": "enabled: remote control on or off",
    "pick": "calculation, and x, y (data coordinates of its plot) or box=[x0, y0, x1, y1] or "
            "polygon (atoms of a result drawn on them): what the point stands for (an energy, "
            "a k-point, a parameter, sites) and the targets that take it",
    "pick_to": "calculation, target (an index into pick's targets for the same x, y, box or "
               "polygon, or the target itself): start or move a calculation there",
    "run_at_once": "enabled: a calculation runs as soon as it is added or one of its "
                   "parameters is set",
    "renderer_3d": "name: matplotlib or pyvista, what draws in 3D (pyvista: moved as in "
                   "Blender's viewport)",
    "view_3d": "name: front, back, right, left, top, bottom, perspective, orthographic, "
               "flip, all, selected or reset, and calculation (a result view; the canvas "
               "when left out): move the pyvista view",
    "plot_text": "name: small, normal or large, the size of the text of every drawing",
    "ui_text": "name: normal or large, the size of the text of the menus, the panels and "
               "the forms",
    "reset_layout": "the panels back in their default arrangement",
    "log": "enabled: show or hide the bottom area (the Log and the Console)",
    "panel": "name (outlinerDock, propertiesDock, helpDock, slidersDock, jobsDock, logDock, "
             "consoleDock, or the panel's title), shown=true|false: show and raise a panel, "
             "or hide it",
    "add_menu": "section (<system>/geometry, <system>/regions, <system>/hamiltonian, "
                "<system>/model, calculations or systems; left out: the workspace's family on "
                "the current system), search: open an Add menu as its \"+\" does, the text "
                "typed in its search line; returns the entries it lists and the best match, "
                "which Enter adds",
    "run_stale": "run every calculation whose result is stale (the slow ones after one "
                 "question in the cost bar); returns their ids",
    "start": "search: the start page's filter (the page shows while the document has no "
             "system), every band narrowed to the lattices, examples and recent files "
             "matching every word; returns the object names of the cards in sight "
             "(startLattice_<kind>, startClassical_<kind>, startPreset_<name>, "
             "startRecent_<n>)",
    "run": "calculation (left out: the selected one, as the Run button and F5): run it "
           "through the cost guard; returns its job at once, or null when the cost bar asks "
           "first (the run method skips the cost guard and waits for the result)",
}


def plot_title(session, calculation, result):
    """(title, state) of a result's figure sent alone: the title the result
    view draws ("c1 · bands · spinful"), followed by the mark of its state
    when the window would show it in the tab and the status row above the
    plot (ui/plots.py's ROW_STATES: stale, queued, running, failed, marked
    as ui/marks.py marks them everywhere), since a figure sent to a client
    has neither; the state is marks.calculation_state's, which the window
    reads too. Imported here, as plot() imports ui/plots.py: the rest of
    this module stays free of Qt."""
    from guiqula.ui.marks import calculation_state, mark
    from guiqula.ui.plots import ROW_STATES
    state, progress = calculation_state(session, calculation)
    title = f"{calculation} · {result.kind} · {result.mode}"
    sign = mark(state, progress) if state in ROW_STATES else ""
    return title + (f" {sign}" if sign else ""), state


def jsonable(value):
    """value as JSON data: arrays to lists, NaN and infinities to None,
    complex numbers to [real, imag], anything unknown to its repr."""
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, complex):
        return [jsonable(value.real), jsonable(value.imag)]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return repr(value)


def thinned(array, max_values):
    """(values, step): the array, every step-th row of it when it holds more
    than max_values numbers."""
    array = np.asarray(array)
    if array.size <= max_values or array.ndim == 0:
        return array, 1
    per_row = max(array.size // max(len(array), 1), 1)
    step = math.ceil(len(array) * per_row / max_values)
    return array[::step], step


def _seconds(value, name="timeout"):
    """A timeout parameter in seconds, at most LONGEST_WAIT; one that is not
    a number of seconds is refused before anything is done."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = math.nan
    if not value >= 0:                   # NaN too
        raise RemoteError(INVALID_PARAMS, f"{name} must be a number of seconds")
    return min(value, LONGEST_WAIT)


def _range(array):
    try:
        array = np.asarray(array)
        if array.size == 0 or not np.issubdtype(array.dtype, np.number):
            return None
        values = np.abs(array) if np.iscomplexobj(array) else array
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            return None
        return [float(finite.min()), float(finite.max())]
    except (TypeError, ValueError):
        return None


def _anchor(guide, asked):
    """The anchor of a guide a client means: the heading as written, else the
    one heading that starts with (or else contains) what it asked for,
    ignoring case ("Fields" for "Fields: parameters that depend on...")."""
    if guide is None:
        raise RemoteError(INVALID_PARAMS, "that user guide was not found")
    anchors = guide.anchors()
    if asked in anchors:
        return asked
    lower = asked.lower()
    for match in (lambda a: a.lower().startswith(lower), lambda a: lower in a.lower()):
        found = [a for a in anchors if match(a)]
        if len(found) == 1:
            return found[0]
        if found:
            raise RemoteError(INVALID_PARAMS, f"{asked!r} matches several sections: "
                                              f"{found[:12]}")
    raise RemoteError(INVALID_PARAMS, f"no section {asked!r}; the guide's contents list them")


class RemoteAPI:
    """The methods, over a Session; window: the window's hooks
    (remote/window.py), or None without a window."""

    def __init__(self, session, window=None):
        self.session = session
        self.window = window
        self._unsubscribe = None
        if window is None:
            self._unsubscribe = session.subscribe(self._on_session_event)

    def close(self):
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def __call__(self, method, params):
        if method not in METHODS:
            raise RemoteError(NO_METHOD, f"unknown method {method!r}; known: {list(METHODS)}")
        return getattr(self, method)(**params)

    # ---- builds without a window
    def _on_session_event(self, kind, payload):
        """Rebuild after a change, as the window does (it asks after a pause);
        trust changes the plans as an edit does (Python nodes run or not),
        and so does a new result that a from_result Field reads."""
        if kind == "document":
            changed = payload["type"] in ("mutation", "undo", "redo", "reset") or \
                payload["type"] == "action" and payload.get("name") == "trust"
        else:
            changed = kind == "job" and payload.kind == "run" and payload.status == "done" \
                and payload.label in pipeline.result_references(self.session.document)
        if changed and "interactive" in self.session.jobs.workers:
            self.session.build_all()

    def settled(self):
        """Whether no build is waiting (and the window asks for none)."""
        if self.window is not None and self.window.busy():
            return False
        return all(job.done for job in self.session.jobs.jobs.values() if job.kind == "build")

    # ---- what is open
    def hello(self):
        session = self.session
        registry.entries()                  # loads the plugins
        return {"guiqula": guiqula.__version__, "pyqula": vendoring.describe(),
                "window": self.window is not None,
                "document": str(session.path) if session.path else None,
                "methods": list(METHODS), "plugins": plugins.describe()}

    def status(self):
        session = self.session
        document = session.document
        systems = [self._system_status(system) for system in document.systems]
        calculations = []
        for calc in document.calculations:
            item = {"id": calc.id, "kind": calc.kind, "system": calc.system,
                    "status": session.status(calc.id)}
            try:
                problem = session.plan_calculation(calc.id).problem
            except Exception as error:
                problem = str(error)
            if problem:
                item["problem"] = problem
            estimate = session.estimate(calc.id)
            if estimate is not None:
                item["estimate_seconds"] = jsonable(estimate["seconds"])
            job = session.calc_jobs.get(calc.id)
            if job is not None and job.status == "failed":
                item["error"] = job.error
            calculations.append(item)
        history = session.dispatcher.history()
        out = {"document": {"path": str(session.path) if session.path else None,
                            "modified": session.modified, "trusted": session.trusted,
                            "notes": document.notes, "locks": list(document.locks)},
               "systems": systems, "calculations": calculations,
               "undo": history["undo"][:5], "redo": history["redo"][:5],
               "settled": self.settled(), "window": None}
        if self.window is not None:
            out["window"] = self.window.state()
        return jsonable(out)

    def _system_status(self, system):
        session = self.session
        item = {"id": system.id, "name": system.name, "kind": system.kind,
                "lattice": system.geometry.base.kind,
                "lattice_params": system.geometry.base.params,
                "ops": [self._entry(op) for op in system.geometry.ops],
                "regions": [{"id": r.id, "name": r.name} for r in system.regions],
                "terms": [self._entry(t) for t in terms_of(system)]}
        if system.hamiltonian is not None:
            item["construction"] = system.hamiltonian.construction.model_dump()
            meanfield = system.hamiltonian.meanfield
            if meanfield.enabled:
                item["meanfield"] = {"kind": meanfield.kind, "params": meanfield.params}
        if system.model is not None:
            item["model"] = {"kind": system.model.kind, "params": system.model.params}
        try:
            plan = session.plan_system(system.id)
            invalid = [{"id": s.id or s.stage, "problem": s.problem}
                       for s in plan.stages if s.problem]
            warnings = [{"id": s.id or s.stage, "warning": w}
                        for s in plan.stages for w in s.warnings]
            if plan.problem:
                invalid.insert(0, {"id": system.id, "problem": plan.problem})
            item["mode"] = plan.mode
            if invalid:
                item["invalid"] = invalid
            if warnings:
                item["warnings"] = warnings
        except Exception as error:
            item["invalid"] = [{"id": system.id, "problem": str(error)}]
        build = session.builds.get(system.id)
        if build is not None:
            item["build"] = {k: build.get(k) for k in ("sites", "dimensionality", "mode",
                                                       "dimension")}
            item["build"]["current"] = session.build_is_current(system.id)
        if system.id in session.build_errors:
            item["build_error"] = session.build_errors[system.id]
        return item

    @staticmethod
    def _entry(entry):
        item = {"id": entry.id, "kind": entry.kind, "params": entry.params}
        if not entry.enabled:
            item["enabled"] = False
        if entry.region:
            item["region"] = entry.region
        return item

    def document(self):
        return self.session.document.model_dump(mode="json", exclude={"ui"})

    def commands(self):
        dispatcher = self.session.dispatcher
        return {"mutations": dispatcher.mutations(), "actions": dispatcher.actions()}

    def catalogue(self, family=None, system_kind=None, search=None, details=None):
        """Registry entries; with a family or a search (or details=true) each
        with its parameters, else one line each."""
        if family is not None and family not in registry.base.FAMILIES:
            raise RemoteError(INVALID_PARAMS, f"unknown family {family!r}; known: "
                                              f"{list(registry.base.FAMILIES)}")
        specs = registry.entries(family)
        if system_kind is not None:
            specs = [s for s in specs if system_kind in s.systems]
        if search:
            words = search.lower().split()
            specs = [s for s in specs if all(
                w in f"{s.kind} {s.label} {s.group} {s.doc}".lower() for w in words)]
        if details is None:
            details = family is not None or bool(search)
        if details:
            return jsonable([s.describe() for s in specs])
        return [{"family": s.family, "kind": s.kind, "label": s.label, "group": s.group,
                 "systems": list(s.systems), "doc": s.doc} for s in specs]

    # ---- commands
    def do(self, command, args=None, settle=True, timeout=60.0):
        """Run a mutation or an action; with settle, reply once the builds
        it causes are done (or timeout seconds went by). An action that
        waits for its job (JOB_ACTIONS) is run without waiting, and the
        reply waits for the job instead: waiting inside the action held up
        the host's loop (no other client served, not even one interrupting
        the console, and the window frozen)."""
        if not isinstance(command, str):
            raise RemoteError(INVALID_PARAMS, "command must be a name")
        if args is not None and not isinstance(args, dict):
            raise RemoteError(INVALID_PARAMS, "args must be an object")
        timeout = _seconds(timeout)
        args = dict(args or {})
        waits = False
        if command in JOB_ACTIONS:
            waits = args.pop("wait", JOB_ACTIONS[command])
            if waits and args.get("timeout") is not None:
                timeout = min(timeout, _seconds(args["timeout"]))
            args["wait"] = False
        value = self.session.run(command, **args)
        if waits:
            job = self.session.calc_jobs[args["calculation"]] if command == "run_calculation" \
                else self.session.jobs.jobs[value["job"]]
            return self._job_done(job, settle, timeout)
        value = jsonable(value)
        if not settle:
            return {"result": value}
        return Pending(self.settled, lambda timed_out: self._after(value, timed_out), timeout)

    def _job_done(self, job, settle, timeout):
        """The reply of do to an action whose job it waits for: what the
        action replies once the job is done (and the builds, with settle)."""
        def finish(timed_out):
            value = jsonable(self.session.console_reply(job) if job.kind == "console"
                             else job.summary())
            out = self._after(value, timed_out) if settle else {"result": value}
            if not job.done:
                out["note"] = f"still {job.status} after {timeout:g} s: " + (
                    "interrupt_console stops it" if job.kind == "console" else
                    "call wait, or cancel")
            return out
        return Pending(lambda: job.done and (not settle or self.settled()), finish, timeout)

    def _after(self, value, timed_out):
        out = {"result": value, "systems": {}}
        for system in self.session.document.systems:
            brief = self._system_status(system)
            out["systems"][system.id] = {k: brief[k] for k in ("mode", "build", "build_error",
                                                               "invalid", "warnings")
                                         if k in brief}
        if timed_out:
            out["note"] = "the builds are still running"
        return jsonable(out)

    # ---- calculations
    def run(self, calculation, wait=True, timeout=600.0, cores=1):
        timeout = _seconds(timeout)
        job = self.session.run_calculation(calculation, cores=cores)
        if not wait:
            return {"job": job.summary()}
        return self._waiting(calculation, job, timeout)

    def wait(self, calculation, timeout=600.0):
        timeout = _seconds(timeout)
        job = self.session.calc_jobs.get(calculation)
        if job is None:
            raise RemoteError(INVALID_PARAMS, f"{calculation!r} was not run")
        return self._waiting(calculation, job, timeout)

    def _waiting(self, calculation, job, timeout):
        def finish(timed_out):
            out = {"job": job.summary(), "status": self.session.status(calculation)}
            if job.status == "done" and self.session.result(calculation) is not None:
                out["result"] = self._summary(calculation)
            elif job.status == "failed":
                out["error"] = job.error
            if timed_out:
                out["note"] = f"still {job.status} after {timeout:g} s: call wait again, " \
                              f"or cancel"
            return jsonable(out)
        return Pending(lambda: job.done, finish, timeout)

    def cancel(self, calculation):
        return self.session.act("cancel", target=calculation)

    def _result(self, calculation):
        result = self.session.result(calculation)
        if result is None:
            status = self.session.status(calculation)
            raise RemoteError(INVALID_PARAMS, f"no result for {calculation!r} (status: "
                                              f"{status}); run it first")
        return result

    def _summary(self, calculation):
        result = self._result(calculation)
        out = result.summary()
        out["status"] = self.session.status(calculation)
        out["arrays"] = {name: {"shape": list(np.shape(array)),
                                "dtype": str(np.asarray(array).dtype),
                                "range": _range(array)}
                         for name, array in result.arrays.items()}
        out["params"] = result.params
        return out

    def result(self, calculation, arrays=None, max_values=MAX_VALUES):
        """The summary, and the values of the arrays named (a list, or
        "all"); arrays of a few numbers always come with their values."""
        try:
            limit = int(max_values)
        except (TypeError, ValueError):
            limit = 0
        if limit < 1:                 # 0 divided by zero, a negative one reversed the rows
            raise RemoteError(INVALID_PARAMS, "max_values must be a whole number, at least 1")
        result = self._result(calculation)
        out = self._summary(calculation)
        names = list(result.arrays) if arrays == "all" else list(arrays or [])
        unknown = [n for n in names if n not in result.arrays]
        if unknown:
            raise RemoteError(INVALID_PARAMS, f"{calculation} has no arrays {unknown}; it has "
                                              f"{list(result.arrays)}")
        values = {}
        for name, array in result.arrays.items():
            if name in names or np.size(array) <= 16:
                shown, step = thinned(array, limit)
                values[name] = shown
                if step > 1:
                    out["arrays"][name]["every"] = step
        out["values"] = values
        return jsonable(out)

    def plot(self, calculation, theme="light", width=7.0, height=4.5, dpi=100):
        """The figure of a result as the result view draws it (PNG, base64),
        with its title carrying the mark of a state that is not simply
        current (plot_title), and that state."""
        result = self._result(calculation)
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        from guiqula.ui import plots
        figure = Figure(figsize=(float(width), float(height)), dpi=int(dpi))
        FigureCanvasAgg(figure)
        title, state = plot_title(self.session, calculation, result)
        projection = self.window.projection() if self.window is not None else "auto"
        plots.draw(figure, result, title, theme_name=theme, projection=projection)
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png")
        return {"png": base64.b64encode(buffer.getvalue()).decode(), "calculation": calculation,
                "state": state}

    def script(self, calculation):
        return self.session.act("export_script", calculation=calculation)

    # ---- the window
    def _window(self, what):
        if self.window is None:
            raise RemoteError(INVALID_PARAMS, f"{what} needs the window: this guiqula runs "
                                              f"without one")
        return self.window

    def screenshot(self, widget=None):
        png, name, size = self._window("a screenshot").screenshot(widget)
        return {"png": base64.b64encode(png).decode(), "widget": name, "size": size}

    def widgets(self):
        return self._window("the widget list").widget_names()

    # ---- help, console, journal
    def help(self, item=None, kind=None, family=None, guide=None, anchor=None, search=None,
             limit=None):
        """An outliner item's help (item: an entry id, s1/base...), a registry
        entry's (kind, and family when the kind is ambiguous), a section of
        a guide (guide "pyqula" or "guiqula", anchor), a guide's contents,
        the plugins (guide "plugins"), or the entries and sections that
        answer a question (search, at most limit of them; decision 159),
        each with the item, kind and family, or guide and anchor, that
        shows it in full."""
        from guiqula.docs import entries as helptexts
        if search is not None:
            from guiqula.docs import search as helpsearch
            limit = int(limit) if limit is not None else helpsearch.LIMIT
            title, text = helpsearch.page(search, limit)
            hits = []
            for hit in helpsearch.search(search, limit):
                found = {"title": hit.title, "where": hit.where, "snippet": hit.snippet,
                         "score": hit.score}
                if hit.guide == "entry":
                    family_of, kind_of = hit.anchor.split(":", 1)
                    found.update(kind=kind_of, family=family_of)
                else:
                    found.update(guide=hit.guide, anchor=hit.anchor)
                hits.append(found)
            return {"title": title, "markdown": text, "hits": hits}
        if item is not None:
            try:
                title, text = helptexts.item_help(self.session, item)
            except (KeyError, ValueError) as error:
                raise RemoteError(INVALID_PARAMS, f"no item {item!r}: {error}") from None
            return {"title": title, "markdown": text}
        if kind is not None:
            specs = [s for s in registry.entries(family) if s.kind == kind]
            if not specs:
                raise RemoteError(INVALID_PARAMS, f"no registry entry {kind!r}")
            if len(specs) > 1:
                raise RemoteError(INVALID_PARAMS, f"{kind!r} is a " + " and a ".join(
                    s.family for s in specs) + ": give the family")
            return {"title": specs[0].label, "markdown": helptexts.entry_help(specs[0])}
        if guide == "plugins":
            return {"title": "Plugins",
                    "markdown": helptexts.plugins_page(self.session.document)}
        if guide is not None:
            if guide not in ("pyqula", "guiqula"):
                raise RemoteError(INVALID_PARAMS, "guide is pyqula, guiqula or plugins")
            if anchor:
                anchor = _anchor(helptexts.guide_of(guide), anchor)
                return {"title": anchor, "markdown": helptexts.section_page(guide, anchor)}
            return {"title": f"{guide} user guide", "markdown": helptexts.contents(guide)}
        return {"title": "guiqula", "markdown": helptexts.contents("guiqula")}

    def console(self, code, system=None, timeout=120.0):
        timeout = _seconds(timeout)
        job = self.session.console(code, system)

        def finish(timed_out):
            # the worker's reply is {"ok", "error"}: code that raised still ends the job
            # normally (its traceback is in the output), so the error is read from it
            value = job.value if isinstance(job.value, dict) else {}
            out = {"status": job.status, "output": list(job.log),
                   "error": job.error or value.get("error")}
            if timed_out:
                out["note"] = f"still running after {timeout:g} s"
            return jsonable(out)
        return Pending(lambda: job.done, finish, timeout)

    def journal(self, limit=30):
        events = self.session.dispatcher.journal[-int(limit):]
        out = {"commands": [{k: e.get(k) for k in ("type", "name", "args", "result", "time")}
                            for e in events]}
        if self.window is not None:
            out["log"] = self.window.log(int(limit))
        return jsonable(out)

