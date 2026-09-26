"""The worker process (PLAN.md 3.3): builds systems and runs calculations
with pyqula, one job at a time, each in its own scratch directory.

Started with the ``spawn`` method and non-daemonic (decision 14.10), so
pyqula's own process pool can start inside it. It makes itself the leader
of a new process group, so that a cancel kills the worker together with any
pool it started. A watchdog thread ends the whole group if the UI process
disappears without shutting the worker down.

This module is imported by the UI process (the Process target must be
importable there), so the engine and pyqula are imported inside main()
only (tests/test_layering.py).
"""
import contextlib
import os
import shutil
import signal
import sys
import tempfile
import threading
import time
import traceback

from guiqula.worker import protocol as P

PROGRESS_INTERVAL = 0.1   # seconds between progress messages


class _Pipe:
    """The connection to the UI process. pyqula hands callbacks (progress)
    to its own pool processes, and forked pool processes inherit the stdout
    redirection: anything they send would corrupt the stream, so only the
    worker process itself may send."""

    def __init__(self, conn):
        self.conn = conn
        self.lock = threading.Lock()
        self.owner = os.getpid()

    def send(self, *message):
        if os.getpid() != self.owner:
            return
        with self.lock:
            self.conn.send(message)


class _LogWriter:
    """stdout of a job, forwarded line by line."""

    def __init__(self, pipe, job_id):
        self.pipe, self.job_id, self.buffer = pipe, job_id, ""

    def write(self, text):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.pipe.send(P.LOG, self.job_id, line)
        return len(text)

    def flush(self):
        if self.buffer.strip():
            self.pipe.send(P.LOG, self.job_id, self.buffer)
        self.buffer = ""


def _watch_parent(parent_pid):
    while True:
        time.sleep(0.5)
        if os.getppid() != parent_pid:
            _end_group()


def _end_group():
    if hasattr(os, "killpg"):
        with contextlib.suppress(OSError):
            os.killpg(os.getpgrp(), signal.SIGKILL)
    os._exit(1)


def main(conn, config):
    if hasattr(os, "setpgrp"):
        os.setpgrp()
    threading.Thread(target=_watch_parent, args=(config["parent_pid"],), daemon=True).start()
    pipe = _Pipe(conn)
    scratch = config["scratch"]
    os.chdir(scratch)

    from guiqula import vendoring
    vendoring.ensure_pyqula_on_path()
    from guiqula.core.document import Document
    from guiqula.engine import structure
    from guiqula.engine.build import BuildCache, build_system
    from guiqula.engine.calculations import run_calculation
    from pyqula import parallel

    cache = BuildCache()
    state = {"cores": 1}
    if config.get("warm"):
        with contextlib.redirect_stdout(open(os.devnull, "w")):
            _warm_up()
    pipe.send(P.READY, {"pid": os.getpid(), "role": config["role"], "names": _names()})

    def handle(job_id, kind, payload):
        last = [0.0]

        def progress(fraction, text=""):
            now = time.monotonic()
            if now - last[0] >= PROGRESS_INTERVAL or fraction >= 1.0:
                last[0] = now
                pipe.send(P.PROGRESS, job_id, fraction, text)

        if kind == "run":
            cores = int(payload.get("cores", 1))
            if cores != state["cores"]:
                parallel.set_cores(cores)
                state["cores"] = parallel.cores
            document = Document.from_json(payload["document"])
            return run_calculation(document, payload["calculation"], cache, progress)
        if kind == "build":
            document = Document.from_json(payload["document"])
            built = build_system(document, payload["system"], cache)
            return dict(structure.describe(built.g),
                        system=payload["system"], key=built.key, mode=built.mode,
                        reports=built.reports, upgraded_by=built.plan.upgraded_by,
                        sites=len(built.g.r), dimension=int(built.h.intra.shape[0]),
                        cache={"hits": cache.hits, "misses": cache.misses, "size": len(cache)})
        if kind == "sleep":
            steps = max(int(payload.get("seconds", 1.0) / 0.05), 1)
            for i in range(steps):
                time.sleep(0.05)
                progress((i + 1) / steps)
            return {"slept": payload.get("seconds", 1.0), "pid": os.getpid()}
        if kind == "crash":
            os._exit(int(payload.get("code", 3)))
        raise ValueError(f"unknown job kind {kind!r}")

    while True:
        try:
            message = conn.recv()
        except (EOFError, OSError):
            break
        if message[0] == P.QUIT:
            break
        _, job_id, kind, payload = message
        job_dir = tempfile.mkdtemp(prefix=f"job-{job_id}-", dir=scratch)
        os.chdir(job_dir)   # pyqula writes .OUT files to the cwd
        pipe.send(P.STARTED, job_id)
        writer = _LogWriter(pipe, job_id)
        try:
            with contextlib.redirect_stdout(writer):
                value = handle(job_id, kind, payload)
            writer.flush()
            pipe.send(P.DONE, job_id, value)
        except Exception as error:
            writer.flush()
            pipe.send(P.FAILED, job_id, f"{type(error).__name__}: {error}",
                      traceback.format_exc())
        finally:
            os.chdir(scratch)
            shutil.rmtree(job_dir, ignore_errors=True)
    if state["cores"] > 1:
        parallel.set_cores(1)
    sys.exit(0)


def _names():
    """The name lists pyqula itself provides (CLAUDE.md), for the forms of
    the UI process, which cannot import pyqula."""
    from pyqula import operatorlist
    return {"operators": list(operatorlist.get_operator_names())}


def _warm_up():
    """Compile the numba kernels of the common paths before the first job
    (PLAN.md 3.3); with NUMBA_CACHE_DIR set this is fast after the first
    run on a machine."""
    from pyqula import geometry
    h = geometry.honeycomb_lattice().get_hamiltonian()
    h.get_bands(nk=4, write=False)
    h.get_bands(nk=4, operator="sz", write=False)
    h.get_dos(nk=2, energies=[0.0], write=False)
