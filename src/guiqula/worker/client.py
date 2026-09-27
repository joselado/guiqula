"""The UI-process side of the workers (PLAN.md 3.3): starts worker
processes, hands them jobs, relays progress, cancels, and respawns a worker
that died or was killed. Qt-free and pyqula-free (it runs in the UI
process): the UI calls poll() from a timer, headless code calls wait().

Two roles (decision 14.6): the *interactive* worker builds systems for the
canvas and the outliner, the *batch* workers (default one) run
calculations, so a running calculation never blocks an edit. A third, the
*console* worker, runs the Python console (decision 14.1); it is started
at the first console command, so a session that never uses the console
never pays for it, and restarting it resets the console's namespace. Cancelling a
job kills only the worker running it, together with the pool pyqula may
have started inside it; the other workers and their caches are untouched
(the phase-1 reading of review item 8).

A worker that dies before it is ready (pyqula cannot be imported, say) is
started again after a pause, at most START_ATTEMPTS times in a row; then
the jobs of its role fail with the reason it gave, until restart(role).
poll() reads each worker for at most POLL_BUDGET seconds, so a job that
prints without end cannot keep the UI's timer from returning. Finished
jobs are forgotten beyond the newest FINISHED_KEPT (their results are the
Session's).
"""
import atexit
import contextlib
import itertools
import multiprocessing
import multiprocessing.connection
import os
import shutil
import signal
import tempfile
import time
import weakref
from collections import deque

from guiqula.worker import process
from guiqula.worker import protocol as P

TERMINAL = ("done", "failed", "cancelled")
POLL_BUDGET = 0.03       # seconds poll() reads one worker's messages before moving on
FINISHED_KEPT = 100      # finished jobs kept in JobManager.jobs
START_ATTEMPTS = 3       # starts in a row of a worker that dies before it is ready
START_PAUSE = 1.0        # seconds before starting it again (doubled at each attempt)


class Job:
    def __init__(self, job_id, kind, role, payload, timeout, label=""):
        self.id = job_id
        self.kind = kind
        self.role = role
        self.payload = payload
        self.timeout = timeout
        self.label = label
        self.status = "queued"     # queued, running, done, failed, cancelled
        self.progress = 0.0
        self.text = ""
        self.value = None          # Result or summary when done
        self.error = None          # message when failed
        self.traceback = None
        self.log = []
        self.submitted = time.time()
        self.started = None
        self.finished = None
        self.worker_pid = None

    @property
    def done(self):
        return self.status in TERMINAL

    def summary(self):
        return {"id": self.id, "kind": self.kind, "label": self.label, "role": self.role,
                "status": self.status, "progress": self.progress, "error": self.error,
                "seconds": (self.finished or time.time()) - self.started if self.started else None}

    def __repr__(self):
        return f"<Job {self.id} {self.kind} {self.status} {self.progress:.0%}>"


class _Worker:
    def __init__(self, role, warm, context):
        self.role = role
        self.warm = warm
        self.context = context
        self.process = None
        self.conn = None
        self.scratch = None
        self.ready = False
        self.job = None
        self.starts = 0
        self.failures = 0        # deaths in a row before READY
        self.broken = None       # why it could not start (its BROKEN message, or exit code)
        self.start_at = None     # when to start it again after such a death

    def start(self):
        self.scratch = tempfile.mkdtemp(prefix=f"guiqula-{self.role}-")
        parent, child = self.context.Pipe()
        config = {"role": self.role, "warm": self.warm, "scratch": self.scratch,
                  "parent_pid": os.getpid()}
        self.process = self.context.Process(target=process.main, args=(child, config),
                                            name=f"guiqula-{self.role}", daemon=False)
        self.process.start()
        child.close()
        self.conn = parent
        self.ready = False
        self.job = None
        self.starts += 1

    def alive(self):
        return self.process is not None and self.process.is_alive()

    def kill(self):
        """Kill the worker and its process group (pyqula's pool)."""
        if self.process is None:
            return
        pid = self.process.pid
        if hasattr(os, "killpg") and pid is not None:     # None: the process never started
            with contextlib.suppress(OSError):
                os.killpg(pid, signal.SIGKILL)   # only exists once the worker called setpgrp
        with contextlib.suppress(OSError, AttributeError):
            self.process.kill()
        with contextlib.suppress(AssertionError):        # a process that never started
            self.process.join(5)
        self._cleanup()

    def stop(self, timeout=2.0):
        """Ask an idle worker to quit; kill one that is busy or still
        starting (it would not read the request until it is done)."""
        if self.process is None:
            return
        if not self.ready or self.job is not None:
            self.kill()
            return
        with contextlib.suppress(OSError, BrokenPipeError):
            self.conn.send((P.QUIT,))
        self.process.join(timeout)
        if self.process.is_alive():
            self.kill()
        else:
            self._cleanup()

    def _cleanup(self):
        with contextlib.suppress(OSError):
            self.conn.close()
        if self.scratch:
            shutil.rmtree(self.scratch, ignore_errors=True)
        self.process = None
        self.ready = False

    def info(self):
        return {"role": self.role, "pid": self.process.pid if self.process else None,
                "alive": self.alive(), "ready": self.ready,
                "job": self.job.id if self.job else None, "starts": self.starts,
                "broken": self.broken if self.failures else None}


_MANAGERS = weakref.WeakSet()


def _shutdown_all():
    for manager in list(_MANAGERS):
        manager.shutdown()


class JobManager:
    """Workers and their job queues. Call poll() regularly (the UI does it
    from a timer); listeners get ("job", job) and ("worker", info) events."""

    def __init__(self, batch=1, interactive=True, warm=True, timeout=None):
        if not _MANAGERS:
            atexit.register(_shutdown_all)   # before multiprocessing joins non-daemonic children
        _MANAGERS.add(self)
        context = multiprocessing.get_context("spawn")
        self.timeout = timeout
        self.workers = {"batch": [_Worker("batch", warm, context) for _ in range(max(batch, 1))]}
        if interactive:
            self.workers["interactive"] = [_Worker("interactive", warm, context)]
        self.queues = {role: deque() for role in self.workers}
        self.jobs = {}
        self.names = {}          # name lists from pyqula (worker READY), e.g. "operators"
        self.request_handler = None   # (job, name, args) -> value; raises to refuse
        self._ids = itertools.count(1)
        self._listeners = []
        self._finished = deque()     # ids of finished jobs, oldest first
        self.closed = False
        for worker in self._all_workers():
            worker.start()

    # ---- public API
    def subscribe(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def submit(self, kind, payload, role="batch", timeout=None, label=""):
        if self.closed:
            raise RuntimeError("the job manager is shut down")
        if kind not in P.KINDS:
            raise ValueError(f"unknown job kind {kind!r}")
        if role not in self.workers:
            raise ValueError(f"no {role!r} worker; roles: {sorted(self.workers)}")
        job = Job(f"j{next(self._ids)}", kind, role, payload,
                  timeout if timeout is not None else self.timeout, label)
        self.jobs[job.id] = job
        self.queues[role].append(job)
        self._emit("job", job)
        self._dispatch()
        return job

    def run(self, document_json, calculation, cores=1, timeout=None, trusted=True, results=None):
        """trusted: whether the document's Python nodes run (PLAN.md 13.7);
        results: {calculation id: ResultRef} its from_result Fields read."""
        return self.submit("run", {"document": document_json, "calculation": calculation,
                                   "cores": cores, "trusted": trusted, "results": results},
                           "batch", timeout, label=calculation)

    def build(self, document_json, system, timeout=None, view=False, trusted=True,
              results=None):
        """view: include the Hamiltonian view (engine/structure.py)."""
        return self.submit("build", {"document": document_json, "system": system, "view": view,
                                     "trusted": trusted, "results": results}, "interactive",
                           timeout, label=system)

    def console(self, code, document_json, system, trusted=True, timeout=None, results=None):
        """Run code in the console worker (started now if needed)."""
        if "console" not in self.workers:
            context = multiprocessing.get_context("spawn")
            worker = _Worker("console", False, context)
            self.workers["console"] = [worker]
            self.queues["console"] = deque()
            worker.start()
            self._emit("worker", worker.info())
        return self.submit("console", {"code": code, "document": document_json, "system": system,
                                       "trusted": trusted, "results": results}, "console", timeout,
                           label="console")

    def restart(self, role):
        """Kill and restart the workers of a role (their jobs are cancelled):
        for the console, an interrupt that also resets its namespace. A
        worker that could not start gets its attempts back."""
        for worker in self.workers.get(role, []):
            job = worker.job
            worker.failures, worker.start_at = 0, None
            self._restart(worker)
            if job is not None and not job.done:
                self._finish(job, "cancelled")
        for job in list(self.queues.get(role, [])):
            self.cancel(job)

    def cancel(self, job):
        job = self.jobs[job] if isinstance(job, str) else job
        if job.done:
            return job
        if job in self.queues[job.role]:
            self.queues[job.role].remove(job)
        else:
            for worker in self.workers[job.role]:
                if worker.job is job:
                    self._restart(worker)
        self._finish(job, "cancelled")
        self._dispatch()
        return job

    def supersede(self, kind, label):
        """Cancel the queued (not yet running) jobs of this kind and label:
        a newer request replaces them (interactive builds coalesce per
        system). Returns them."""
        superseded = [job for queue in self.queues.values() for job in queue
                      if job.kind == kind and job.label == label]
        for job in superseded:
            self.cancel(job)
        return superseded

    def forget(self, job):
        """Drop a finished job from the table (builds are frequent)."""
        job = self.jobs.get(job) if isinstance(job, str) else job
        if job is not None and job.done:
            self.jobs.pop(job.id, None)

    def poll(self, timeout=0.0):
        """Process pending messages, detect dead workers and timeouts, and
        hand queued jobs to idle workers. Returns the number of messages."""
        if self.closed:
            return 0
        connections = {w.conn: w for w in self._all_workers() if w.process is not None}
        count = 0
        ready = multiprocessing.connection.wait(list(connections), timeout) if connections else []
        for conn in ready:
            worker = connections[conn]
            deadline = time.monotonic() + POLL_BUDGET
            while worker.process is not None and time.monotonic() < deadline:
                try:
                    if not conn.poll():
                        break
                    message = conn.recv()
                except (EOFError, OSError):
                    break
                count += 1
                self._handle(worker, message)
        now = time.time()
        for worker in self._all_workers():
            if worker.process is not None and not worker.alive():
                code = worker.process.exitcode
                job = worker.job
                if worker.ready:
                    self._restart(worker)
                    why = "it was restarted"
                else:
                    self._broke(worker, code)
                    why = f"it could not start: {worker.broken}"
                if job is not None and not job.done:
                    self._finish(job, "failed",
                                 error=f"the worker process died (exit code {code}) while "
                                       f"running this job; {why}")
            elif worker.process is None and worker.start_at is not None:
                if worker.failures >= START_ATTEMPTS:
                    for job in list(self.queues[worker.role]):
                        self.queues[worker.role].remove(job)
                        self._finish(job, "failed", error=f"the {worker.role} worker cannot "
                                                          f"start: {worker.broken}")
                elif time.monotonic() >= worker.start_at:
                    worker.start_at = None
                    worker.start()
                    self._emit("worker", worker.info())
            job = worker.job
            if job is not None and job.timeout and job.started and now - job.started > job.timeout:
                self._restart(worker)
                self._finish(job, "failed", error=f"timed out after {job.timeout:g} s")
        self._dispatch()
        return count

    def wait(self, job, timeout=None):
        """Poll until the job finishes; returns it. Raises TimeoutError."""
        job = self.jobs[job] if isinstance(job, str) else job
        deadline = None if timeout is None else time.monotonic() + timeout
        while not job.done:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"{job} still {job.status} after {timeout} s")
            self.poll(0.05)
        return job

    def wait_ready(self, timeout=120):
        deadline = time.monotonic() + timeout
        while not all(w.ready for w in self._all_workers()):
            if time.monotonic() > deadline:
                raise TimeoutError("workers not ready")
            self.poll(0.05)

    def status(self):
        return [w.info() for w in self._all_workers()]

    def shutdown(self):
        """Stop every worker; never blocks for long (non-daemonic children
        would otherwise be joined by multiprocessing at exit)."""
        if self.closed:
            return
        self.closed = True
        for worker in self._all_workers():
            worker.stop()
        for job in list(self.jobs.values()):     # listeners may forget jobs
            if not job.done:
                self._finish(job, "cancelled")
        _MANAGERS.discard(self)

    close = shutdown

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.shutdown()

    # ---- internals
    def _all_workers(self):
        return [w for workers in self.workers.values() for w in workers]

    def _emit(self, kind, payload):
        for listener in list(self._listeners):
            listener(kind, payload)

    def _restart(self, worker):
        worker.kill()
        worker.start()
        self._emit("worker", worker.info())

    def _broke(self, worker, code):
        """A worker died before it was ready: start it again after a pause
        (poll does), not at once, and give up after START_ATTEMPTS."""
        worker.kill()
        worker.job = None
        worker.failures += 1
        worker.broken = worker.broken or f"exit code {code}"
        worker.start_at = time.monotonic() + START_PAUSE * 2 ** (worker.failures - 1)
        self._emit("worker", worker.info())

    def _finish(self, job, status, value=None, error=None, traceback=None):
        job.status = status
        job.value = value
        job.error = error
        job.traceback = traceback
        job.finished = time.time()
        if status == "done":
            job.progress = 1.0
        self._finished.append(job.id)
        while len(self._finished) > FINISHED_KEPT:
            self.jobs.pop(self._finished.popleft(), None)
        self._emit("job", job)

    def _dispatch(self):
        for role, queue in self.queues.items():
            for worker in self.workers[role]:
                if not queue:
                    break
                if worker.job is None and worker.process is not None:
                    job = queue.popleft()
                    worker.job = job
                    job.worker_pid = worker.process.pid
                    try:
                        worker.conn.send((P.JOB, job.id, job.kind, job.payload))
                    except (OSError, BrokenPipeError):
                        worker.job = None
                        queue.appendleft(job)

    def _answer(self, worker, job_id, job, name, args):
        """Reply to a worker's request with what request_handler returns
        (or the error it raised)."""
        try:
            if self.request_handler is None:
                raise RuntimeError("nobody answers requests from the workers")
            if job is None or job.done:
                raise RuntimeError("the job that asked is over")
            reply = (P.REPLY, job_id, True, self.request_handler(job, name, args))
        except Exception as error:
            reply = (P.REPLY, job_id, False, f"{type(error).__name__}: {error}")
        with contextlib.suppress(OSError, BrokenPipeError):
            worker.conn.send(reply)

    def _handle(self, worker, message):
        tag = message[0]
        if tag == P.READY:
            worker.ready = True
            worker.failures, worker.broken = 0, None
            self.names.update(message[1].get("names", {}))
            self._emit("worker", worker.info())
            return
        if tag == P.BROKEN:
            worker.broken = message[1]
            return
        job = self.jobs.get(message[1])
        if tag == P.REQUEST:
            self._answer(worker, message[1], job, message[2], message[3])
            return
        if job is None or job.done:
            return
        if tag == P.STARTED:
            job.status = "running"
            job.started = time.time()
        elif tag == P.PROGRESS:
            job.progress, job.text = message[2], message[3]
        elif tag == P.LOG:
            job.log.append(message[2])
        elif tag == P.DONE:
            worker.job = None
            self._finish(job, "done", value=message[2])
            return
        elif tag == P.FAILED:
            worker.job = None
            self._finish(job, "failed", error=message[2], traceback=message[3])
            return
        self._emit("job", job)
