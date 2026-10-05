"""The marks of a state, one set for the outliner's rows, the result tabs and
the status row above a plot (PLAN.md section 7, phase 8, P7): Unicode until
the icons of P8 draw them.

No Qt here, so that the outliner, the window and the tests read the same
strings. A state without a mark ("none", a calculation never run) reads as
nothing at all; a queued or cancelled job, rarer, keeps its word."""

DONE = "✓"       # check mark
STALE = "↻"      # clockwise open circle arrow
FAILED = "✗"     # ballot x
INVALID = "✗"
DISABLED = "○"   # white circle
LOCKED = "locked"
WARNING = "⚠"    # warning sign: valid, but worth a look (a stale result read)
QUEUED = "queued"
CANCELLED = "cancelled"

MARKS = {
    "done": DONE,
    "stale": STALE,
    "failed": FAILED,
    "invalid": INVALID,
    "disabled": DISABLED,
    "locked": LOCKED,
    "warning": WARNING,
    "queued": QUEUED,
    "cancelled": CANCELLED,
}

# drawn in the theme's error colour
ERROR_STATES = frozenset({"failed", "invalid"})
# drawn in the dimmed colour: what is out of date or out of the stack
DIM_STATES = frozenset({"stale", "disabled"})


def mark(state, progress=None):
    """The mark of `state`; a running job shows its progress, a fraction from
    0 to 1, as "70%", and "running" before its first report."""
    if state == "running":
        return "running" if progress is None else f"{round(100 * progress)}%"
    return MARKS.get(state, "")


def calculation_state(session, calculation, job=None):
    """(state, progress) of a calculation in a Session, so that
    mark(*calculation_state(session, c)) reads the same in the outliner, the
    result tab and the status row above the plot. The state is
    Session.status's (none, queued, running, done, stale, failed or
    cancelled), but for a job still queued or running, which gives its own
    state (job: the one an event is about, which the session may not hold
    yet). A run that failed over an earlier result thus reads as that
    result does, stale, and failed only when no result is kept (decision
    121, answered with its alternative); the failure is in the Jobs panel.
    The progress is a running job's fraction once it has reported one, else
    None."""
    if job is None or job.done:
        job = session.calc_jobs.get(calculation)
    if job is not None and not job.done:
        return job.status, (job.progress or None) if job.status == "running" else None
    return session.status(calculation), None
