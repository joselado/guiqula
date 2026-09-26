"""Messages between the UI process and a worker process (tuples over a
multiprocessing Pipe; everything in them pickles without pyqula).

UI to worker:  (JOB, job_id, kind, payload) | (QUIT,)
worker to UI:  (READY, info) | (STARTED, job_id) | (PROGRESS, job_id, fraction, text)
               | (LOG, job_id, text) | (DONE, job_id, value) | (FAILED, job_id, message, traceback)

READY's info carries the worker's pid and role, and ``names``: the name
lists pyqula provides ({"operators": [...]}), which the forms offer.

Job kinds: "run" (payload: document JSON, calculation id, cores) returns a
guiqula.core.results.Result; "build" (document JSON, system id) returns a
build summary dict (the stage reports, the Hilbert-space mode and dimension,
and the geometry arrays of guiqula.engine.structure.describe); "sleep" and "crash" exist for testing the machinery.
"""
JOB = "job"
QUIT = "quit"
READY = "ready"
STARTED = "started"
PROGRESS = "progress"
LOG = "log"
DONE = "done"
FAILED = "failed"

KINDS = ("run", "build", "sleep", "crash")
