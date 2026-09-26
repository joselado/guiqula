"""The worker process (PLAN.md 3.3): builds systems and runs calculations
with pyqula, one job at a time, each in its own scratch directory. The
console worker (decision 14.1) runs the Python console instead: a
namespace that lives as long as the process, see Console.

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


class RequestError(RuntimeError):
    """The UI process refused a request (the message says why)."""


class Quit(Exception):
    """The UI process asked the worker to stop while a job waited for a reply."""


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


class Console:
    """The Python console's interpreter (decision 14.1). Its namespace lives
    as long as the worker: variables persist between commands, and an
    interrupt (a kill) loses them. ``doc`` is the Document, ``g`` and ``h``
    the geometry and Hamiltonian of the chosen system (built with the mean
    field, as the calculations see them), rebuilt when the Document or the
    system changed since the last command that used them; ``do(command,
    **args)`` (and ``act``) runs a command of the window's dispatcher, so a
    mutation is undoable there. The value of a final expression is echoed;
    an error prints its traceback and the job still ends normally."""

    def __init__(self, request, build):
        import numpy as np
        import pyqula
        self.request, self.build = request, build
        self.namespace = {"np": np, "pyqula": pyqula, "__name__": "__console__"}
        self.document_json = self.system = None
        self.built = False

    def _set_document(self, document_json):
        from guiqula.core.document import Document
        if document_json != self.document_json:
            self.document_json = document_json
            self.namespace["doc"] = Document.from_json(document_json)
            self.built = False

    def run(self, job_id, payload):
        import ast
        code = payload["code"]
        self._set_document(payload["document"])
        if payload.get("system") != self.system:
            self.system, self.built = payload.get("system"), False
        self.namespace["do"] = self.namespace["act"] = \
            lambda command, /, **args: self._do(job_id, command, args)
        try:
            tree = ast.parse(code, "<console>")
        except SyntaxError as error:
            print(f"SyntaxError: {error.msg} (line {error.lineno})")
            return {"ok": False, "error": f"SyntaxError: {error.msg}"}
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        try:
            if names & {"g", "h"} and not self.built:
                self._build(payload.get("trusted", False), payload.get("results"))
            echo = tree.body and isinstance(tree.body[-1], ast.Expr)
            body = ast.Module(body=tree.body[:-1] if echo else tree.body, type_ignores=[])
            exec(compile(body, "<console>", "exec"), self.namespace)
            if echo:
                value = eval(compile(ast.Expression(tree.body[-1].value), "<console>", "eval"),
                             self.namespace)
                if value is not None:
                    self.namespace["_"] = value
                    print(repr(value))
        except Quit:
            raise
        except Exception as error:
            print(self._traceback(error))
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}
        return {"ok": True, "error": None}

    def _build(self, trusted, results=None):
        if self.system is None:
            raise NameError("g and h need a system: the document has none")
        built = self.build(self.namespace["doc"], self.system, trusted, results)
        self.namespace["g"], self.namespace["h"] = built.g, built.h
        self.built = True

    def _do(self, job_id, command, args):
        reply = self.request(job_id, "run", {"command": command, "args": args})
        self._set_document(reply["document"])
        return reply["value"]

    @staticmethod
    def _traceback(error):
        """The traceback from the console's own code on (not the worker's)."""
        frames = traceback.extract_tb(error.__traceback__)
        start = next((i for i, f in enumerate(frames) if f.filename == "<console>"), 0)
        lines = ["Traceback (most recent call last):"]
        lines += [line.rstrip() for line in traceback.format_list(frames[start:])]
        lines += [line.rstrip() for line in traceback.format_exception_only(type(error), error)]
        return "\n".join(lines)


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
            _warm_up(config["role"])
    pipe.send(P.READY, {"pid": os.getpid(), "role": config["role"], "names": _names()})

    def request(job_id, name, args=None):
        """Ask the UI process something and wait for the answer (protocol
        REQUEST/REPLY). Jobs are sent to idle workers only, so the next
        message is the reply, or QUIT."""
        pipe.send(P.REQUEST, job_id, name, dict(args or {}))
        while True:
            message = conn.recv()
            if message[0] == P.QUIT:
                raise Quit()
            if message[0] == P.REPLY and message[1] == job_id:
                _, _, ok, value = message
                if not ok:
                    raise RequestError(value)
                return value

    console = []          # the Console, made at the first console job

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
            return run_calculation(document, payload["calculation"], cache, progress,
                                   trusted=payload.get("trusted", False),
                                   results=payload.get("results"))
        if kind == "build":
            document = Document.from_json(payload["document"])
            built = build_system(document, payload["system"], cache, meanfield=False,
                                 trusted=payload.get("trusted", False),
                                 results=payload.get("results"))
            quantum = hasattr(built.h, "intra")        # else a classical model
            view = bool(payload.get("view")) and quantum
            return dict(structure.describe(built.g), view=view,
                        hamiltonian=structure.hamiltonian_view(built.h) if view else None,
                        system=payload["system"], key=built.key, mode=built.mode,
                        kind=built.plan.kind, reports=built.reports,
                        upgraded_by=built.plan.upgraded_by, sites=len(built.g.r),
                        dimension=int(built.h.intra.shape[0]) if quantum else len(built.g.r),
                        cache={"hits": cache.hits, "misses": cache.misses, "size": len(cache)})
        if kind == "sleep":
            steps = max(int(payload.get("seconds", 1.0) / 0.05), 1)
            for i in range(steps):
                time.sleep(0.05)
                progress((i + 1) / steps)
            return {"slept": payload.get("seconds", 1.0), "pid": os.getpid()}
        if kind == "crash":
            os._exit(int(payload.get("code", 3)))
        if kind == "request":
            return request(job_id, payload["name"], payload.get("args"))
        if kind == "console":
            if not console:
                console.append(Console(request, lambda document, system, trusted, results:
                                       build_system(document, system, cache, trusted=trusted,
                                                    results=results)))
            return console[0].run(job_id, payload)
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
        except Quit:
            break
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
    from guiqula.engine.context import SOURCES, source_names
    return {source: source_names(source) for source in SOURCES}


def _warm_up(role):
    """Compile the numba kernels of the common paths before the first job
    (PLAN.md 3.3); with NUMBA_CACHE_DIR set this is fast after the first
    run on a machine. The mean field only in the batch workers: the
    interactive one never runs it (about 5 s even with the cache)."""
    from pyqula import geometry
    h = geometry.honeycomb_lattice().get_hamiltonian()
    h.get_bands(nk=4, write=False)
    h.get_bands(nk=4, operator="sz", write=False)
    h.get_dos(nk=2, energies=[0.0], write=False)
    if role == "batch":
        h.get_mean_field_hamiltonian(U=1.0, mf="ferro", nk=2, maxite=2)
