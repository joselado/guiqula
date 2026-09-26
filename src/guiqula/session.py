"""A Session: the Document with its command dispatcher, the workers, the
latest result of every calculation and the latest build of every system.
It is the one object the tests, the headless runner (``guiqula run``,
PLAN.md 13.3), tools/drive.py, the UI and the future remote API all drive;
none of them reaches the Document or the workers any other way.

With ``autosave=True`` (the window's session) it also autosaves the
Document from poll() and deletes the autosave on a clean close()
(guiqula.io.autosave); the ``recover`` action loads what a crashed session
left behind.

The Document's ``ui`` block is view state (the window's workspace,
selection, canvas selection): the window hands a ``view_state`` callable,
whose dict is written into ``ui`` of what is saved and autosaved, and reads
it back after a load. It is not physics: it never goes on the undo stack,
never enters a key, and does not count as an unsaved change.

Qt-free and pyqula-free: it runs in the UI process.
"""
import json
from pathlib import Path

from guiqula.commands import CommandError, Dispatcher
from guiqula.core.document import Document
from guiqula.io import autosave as autosave_files
from guiqula.io import project
from guiqula.io import results as result_files
from guiqula.io.script import export_script
from guiqula.registry import cost, pipeline
from guiqula.worker.client import JobManager


def _content(document):
    """The Document without its view state, for the modified flag."""
    return json.dumps(document.model_dump(mode="json", exclude={"ui"}), sort_keys=True)


def _project_path(path_or_name):
    """Where Save writes back to after opening this: None for a preset."""
    resolved = project.resolve(path_or_name)
    return None if resolved.parent == project.PRESETS else resolved


class Session:
    def __init__(self, document=None, batch=1, interactive=True, warm=True, timeout=None,
                 jobs=None, autosave=False):
        path = None
        if isinstance(document, (str, Path)):
            path = _project_path(document)
            document = project.load(document)
        self.dispatcher = Dispatcher(document or Document())
        self.jobs = jobs if jobs is not None else JobManager(
            batch=batch, interactive=interactive, warm=warm, timeout=timeout)
        self.results = {}        # calculation id -> latest Result
        self.calc_jobs = {}      # calculation id -> latest Job
        self.builds = {}         # system id -> latest build summary (engine/structure.py)
        self.build_errors = {}   # system id -> why the latest build failed
        self._build_times = {}   # system id -> submission time of the stored build
        self.path = path         # where the document was loaded from / saved to
        self.view_state = None   # callable -> dict saved as the document's ui block (the window)
        self._saved_json = _content(self.document)
        self.autosaver = autosave if isinstance(autosave, autosave_files.Autosaver) else \
            autosave_files.Autosaver() if autosave else None
        self._listeners = []
        self.jobs.subscribe(self._on_job_event)
        self.dispatcher.subscribe(self._on_document_event)
        for name in ("run_calculation", "cancel", "save", "load", "new", "export_script",
                     "save_result", "recover", "list_recoverable", "discard_recovery"):
            self.dispatcher.register_action(name, getattr(self, "_action_" + name))

    # ---- the command API
    @property
    def document(self):
        return self.dispatcher.document

    @property
    def modified(self):
        """Whether the Document differs from the file it was loaded from or
        last saved to (a new document: from the empty one); the view state
        does not count."""
        return _content(self.document) != self._saved_json

    def document_for_file(self):
        """The Document as saved: with the current view state as its ui."""
        if self.view_state is None:
            return self.document
        try:
            ui = self.view_state()
            json.dumps(ui)
        except Exception:            # a broken view state must not block a save
            return self.document
        return self.document.model_copy(update={"ui": ui})

    def do(self, name, /, **args):
        return self.dispatcher.do(name, **args)

    def act(self, name, /, **args):
        return self.dispatcher.act(name, **args)

    def run(self, name, /, **args):
        return self.dispatcher.run(name, **args)

    def undo(self):
        self.dispatcher.undo()

    def redo(self):
        self.dispatcher.redo()

    def subscribe(self, listener):
        """listener(kind, payload): ("document", event) for every dispatcher
        event, ("job", Job) for job changes, ("worker", info)."""
        self._listeners.append(listener)
        unsubscribe = self.dispatcher.subscribe(lambda event: listener("document", event))
        return lambda: (self._listeners.remove(listener), unsubscribe())

    # ---- results
    def result(self, calculation):
        return self.results.get(calculation)

    def is_stale(self, calculation):
        result = self.results.get(calculation)
        if result is None:
            return False
        try:
            return result.key != pipeline.calculation_key(self.document, calculation)
        except Exception:
            return True

    def status(self, calculation):
        """none, queued, running, done, stale, failed or cancelled."""
        job = self.calc_jobs.get(calculation)
        if job is not None and not job.done:
            return job.status
        if calculation in self.results:
            return "stale" if self.is_stale(calculation) else "done"
        return job.status if job is not None else "none"

    def run_calculation(self, calculation, wait=False, timeout=None, cores=1):
        """Submit a calculation to a batch worker; returns the Job (or waits
        for it and returns the finished Job)."""
        self.document.calculation(calculation)
        job = self.jobs.run(self.document.to_json(), calculation, cores=cores)
        self.calc_jobs[calculation] = job
        if wait:
            self.jobs.wait(job, timeout)
        return job

    # ---- builds (the interactive worker)
    def build(self, system, wait=True, timeout=None):
        """Ask the interactive worker to build a system: its geometry arrays,
        stage reports and Hilbert space land in ``builds[system]``. A request
        still queued for the same system is superseded, so a burst of edits
        costs one build, not one per edit."""
        self.document.system(system)
        self.jobs.supersede("build", system)
        job = self.jobs.build(self.document.to_json(), system)
        if wait:
            self.jobs.wait(job, timeout)
        return job

    def build_all(self):
        return [self.build(system.id, wait=False) for system in self.document.systems]

    def build_is_current(self, system):
        """Whether builds[system] was built from the current Document (it
        stops before the mean field, which runs with the calculations)."""
        build = self.builds.get(system)
        if build is None:
            return False
        try:
            return build["key"] == pipeline.plan_system(self.document, system).key
        except Exception:
            return False

    def estimate(self, calculation):
        """The cost guard (PLAN.md 13.12): the rough duration of a
        calculation from the latest build of its system, or None."""
        try:
            return cost.estimate(self.document, calculation, self.builds)
        except Exception:
            return None

    def cancel(self, calculation_or_job):
        job = self.calc_jobs.get(calculation_or_job) or self.jobs.jobs.get(calculation_or_job)
        if job is None:
            raise CommandError(f"no job for {calculation_or_job!r}")
        return self.jobs.cancel(job)

    def poll(self, timeout=0.0):
        """Process worker messages; autosave if due. The window calls this
        from a timer, headless code through wait()."""
        count = self.jobs.poll(timeout)
        if self.autosaver is not None and self.autosaver.due():
            self.autosaver.write(self.document_for_file(), self.path, self.modified)
        return count

    def wait(self, calculation=None, timeout=None):
        jobs = [self.calc_jobs[calculation]] if calculation else list(self.calc_jobs.values())
        for job in jobs:
            self.jobs.wait(job, timeout)
        return jobs[0] if calculation else jobs

    def close(self):
        """A clean close: stop the workers and delete the autosave."""
        self.jobs.shutdown()
        if self.autosaver is not None:
            self.autosaver.discard()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _on_document_event(self, event):
        """Forget results and builds of entries that no longer exist: ids
        are reused after a removal, and a new c1 must not show the old
        c1's result."""
        if self.autosaver is not None and (event["type"] != "action" or event["name"] == "save"):
            self.autosaver.changed()        # save: the file now records no unsaved changes
        if event["type"] == "reset":
            self.builds.clear()
            self.build_errors.clear()
            self._build_times.clear()
        present = {c.id for c in self.document.calculations}
        for calc in [c for c in self.results if c not in present]:
            del self.results[calc]
        for calc in [c for c, job in self.calc_jobs.items() if c not in present and job.done]:
            del self.calc_jobs[calc]
        systems = {s.id for s in self.document.systems}
        for table in (self.builds, self.build_errors, self._build_times):
            for system in [s for s in table if s not in systems]:
                del table[system]

    def _on_job_event(self, kind, payload):
        if kind == "job" and payload.kind == "run" and payload.status == "done":
            if any(c.id == payload.label for c in self.document.calculations):
                self.results[payload.label] = payload.value
        if kind == "job" and payload.kind == "build" and payload.done:
            self._store_build(payload)
        for listener in list(self._listeners):
            listener(kind, payload)

    def _store_build(self, job):
        system = job.payload.get("system")
        exists = any(s.id == system for s in self.document.systems)
        if exists and job.status == "done" and job.submitted >= self._build_times.get(system, 0):
            self.builds[system] = job.value
            self._build_times[system] = job.submitted
            self.build_errors.pop(system, None)
        elif exists and job.status == "failed":
            self.build_errors[system] = job.error
        self.jobs.forget(job)

    def _replace_document(self, document, path, saved_json):
        """New, open, recover: a whole new Document (not undoable)."""
        self.path = path
        self._saved_json = saved_json
        self.results.clear()
        self.calc_jobs.clear()
        self.dispatcher.reset(document)

    # ---- actions (journaled through the dispatcher, not undoable)
    def _action_run_calculation(self, calculation, wait=False, timeout=None, cores=1):
        job = self.run_calculation(calculation, wait=wait, timeout=timeout, cores=cores)
        return job.summary()

    def _action_cancel(self, target):
        return self.cancel(target).summary()

    def _action_save(self, path):
        self.path = project.save(self.document_for_file(), path)
        self._saved_json = _content(self.document)
        return str(self.path)

    def _action_load(self, path):
        document = project.load(path)
        self._replace_document(document, _project_path(path), _content(document))
        return str(project.resolve(path))

    def _action_new(self):
        self._replace_document(Document(), None, _content(Document()))

    def _action_recover(self, path=None):
        """Load what a session that did not close cleanly left behind (the
        newest one, or the autosave file at path). The recovered Document
        counts as unsaved, Save writes back to its project file, and the
        autosave file is taken over, so it stays recoverable until saved."""
        if path is None:
            candidates = [e for e in autosave_files.recoverable() if "error" not in e]
            if not candidates:
                raise CommandError("there is nothing to recover")
            path = candidates[0]["path"]
        document, info = autosave_files.read(path)
        source = Path(info["source"]) if info.get("source") else None
        self._replace_document(document, source, None)
        if self.autosaver is not None:     # claimed at once: not offered again meanwhile
            self.autosaver.adopt(path)
            self.autosaver.write(self.document_for_file(), self.path, self.modified)
        return {"path": str(path), "source": info.get("source"),
                "systems": [s.id for s in document.systems]}

    def _action_list_recoverable(self, include_unmodified=False):
        return autosave_files.recoverable(include_unmodified=include_unmodified)

    def _action_discard_recovery(self, path):
        autosave_files.discard(path)

    def _action_export_script(self, calculation, path=None):
        result = self.results.get(calculation)
        skipped = {r["id"]: r["message"] for r in result.skipped} if result else None
        source = export_script(self.document, calculation, skipped)
        if path is None:
            return source
        Path(path).write_text(source)
        return str(path)

    def _action_save_result(self, calculation, path):
        result = self.results.get(calculation)
        if result is None:
            raise CommandError(f"no result for {calculation!r}")
        return [str(p) for p in result_files.save(result, path)]
