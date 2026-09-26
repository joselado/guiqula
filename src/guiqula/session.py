"""A Session: the Document with its command dispatcher, the workers, and
the latest result of every calculation. It is the one object the tests, the
headless runner (``guiqula run``, PLAN.md 13.3), tools/drive.py, the UI and
the future remote API all drive; none of them reaches the Document or the
workers any other way.

Qt-free and pyqula-free: it runs in the UI process.
"""
from pathlib import Path

from guiqula.commands import CommandError, Dispatcher
from guiqula.core.document import Document
from guiqula.io import project
from guiqula.io import results as result_files
from guiqula.io.script import export_script
from guiqula.registry import pipeline
from guiqula.worker.client import JobManager


class Session:
    def __init__(self, document=None, batch=1, interactive=True, warm=True, timeout=None,
                 jobs=None):
        if isinstance(document, (str, Path)):
            document = project.load(document)
        self.dispatcher = Dispatcher(document or Document())
        self.jobs = jobs if jobs is not None else JobManager(
            batch=batch, interactive=interactive, warm=warm, timeout=timeout)
        self.results = {}        # calculation id -> latest Result
        self.calc_jobs = {}      # calculation id -> latest Job
        self.path = None         # where the document was loaded from / saved to
        self._listeners = []
        self.jobs.subscribe(self._on_job_event)
        for name in ("run_calculation", "cancel", "save", "load", "new", "export_script",
                     "save_result"):
            self.dispatcher.register_action(name, getattr(self, "_action_" + name))

    # ---- the command API
    @property
    def document(self):
        return self.dispatcher.document

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

    def build(self, system, wait=True, timeout=None):
        job = self.jobs.build(self.document.to_json(), system)
        if wait:
            self.jobs.wait(job, timeout)
        return job

    def cancel(self, calculation_or_job):
        job = self.calc_jobs.get(calculation_or_job) or self.jobs.jobs.get(calculation_or_job)
        if job is None:
            raise CommandError(f"no job for {calculation_or_job!r}")
        return self.jobs.cancel(job)

    def poll(self, timeout=0.0):
        return self.jobs.poll(timeout)

    def wait(self, calculation=None, timeout=None):
        jobs = [self.calc_jobs[calculation]] if calculation else list(self.calc_jobs.values())
        for job in jobs:
            self.jobs.wait(job, timeout)
        return jobs[0] if calculation else jobs

    def close(self):
        self.jobs.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _on_job_event(self, kind, payload):
        if kind == "job" and payload.kind == "run" and payload.status == "done":
            self.results[payload.label] = payload.value
        for listener in list(self._listeners):
            listener(kind, payload)

    # ---- actions (journaled through the dispatcher, not undoable)
    def _action_run_calculation(self, calculation, wait=False, timeout=None, cores=1):
        job = self.run_calculation(calculation, wait=wait, timeout=timeout, cores=cores)
        return job.summary()

    def _action_cancel(self, target):
        return self.cancel(target).summary()

    def _action_save(self, path):
        self.path = project.save(self.document, path)
        return str(self.path)

    def _action_load(self, path):
        document = project.load(path)
        self.dispatcher.reset(document)
        self.results.clear()
        self.calc_jobs.clear()
        resolved = project.resolve(path)
        self.path = None if resolved.parent == project.PRESETS else resolved
        return str(resolved)

    def _action_new(self):
        self.dispatcher.reset(Document())
        self.results.clear()
        self.calc_jobs.clear()
        self.path = None

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
