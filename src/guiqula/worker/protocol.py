"""Messages between the UI process and a worker process (tuples over a
multiprocessing Pipe; everything in them pickles without pyqula).

UI to worker:  (JOB, job_id, kind, payload) | (QUIT,) | (REPLY, job_id, ok, value)
worker to UI:  (READY, info) | (STARTED, job_id) | (PROGRESS, job_id, fraction, text)
               | (LOG, job_id, text) | (DONE, job_id, value) | (FAILED, job_id, message, traceback)
               | (REQUEST, job_id, name, args) | (BROKEN, message)

BROKEN is the last message of a worker that cannot start (pyqula does not
import): why, before it exits.

A job may ask the UI process something while it runs (the console's doc
and do(), decision 14.1): the worker sends REQUEST and waits for the
REPLY to that job; the UI answers from poll() (JobManager.request_handler,
installed by the Session: "run" a dispatcher command, or the current
"document"). ok is False when the request failed, value then says why.

READY's info carries the worker's pid and role, and ``names``: the name
lists pyqula provides ({"operators": [...]}), which the forms offer.

Job kinds: "console" (payload: code, document JSON, system id or None,
trusted; the console worker's REPL, decision 14.1) returns {"ok", "error"},
its output arriving as LOG lines; "run" (payload: document JSON, calculation id, cores) returns a
guiqula.core.results.Result; "build" (document JSON, system id) returns a
build summary dict (the stage reports, the Hilbert-space mode and dimension,
and the geometry arrays of guiqula.engine.structure.describe); "sleep", "crash" and
"request" (payload: name, args; returns the reply) exist for testing the machinery.
"""
JOB = "job"
QUIT = "quit"
READY = "ready"
STARTED = "started"
PROGRESS = "progress"
LOG = "log"
DONE = "done"
FAILED = "failed"
REQUEST = "request"
REPLY = "reply"
BROKEN = "broken"

KINDS = ("run", "build", "console", "sleep", "crash", "request")
