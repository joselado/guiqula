from types import SimpleNamespace

from guiqula.ui import marks


def test_one_mark_per_state():
    assert marks.mark("done") == "✓"
    assert marks.mark("stale") == "↻"
    assert marks.mark("failed") == marks.mark("invalid") == "✗"
    assert marks.mark("disabled") == "○"
    assert marks.mark("locked") == "locked"
    assert marks.mark("something else") == ""
    assert marks.ERROR_STATES == {"failed", "invalid"}


def test_a_running_job_shows_its_progress():
    assert marks.mark("running") == "running"
    assert marks.mark("running", 0.7) == "70%"
    assert marks.mark("running", 0) == "0%"


def test_the_states_the_tree_needs_too():
    assert marks.mark("warning") == "⚠"
    assert marks.mark("queued") == "queued" and marks.mark("cancelled") == "cancelled"
    assert marks.mark("none") == ""
    assert marks.DIM_STATES == {"stale", "disabled"}


def test_the_state_of_a_calculation_in_a_session():
    """The state is the session's, the progress a running job's only, once
    it has reported one; a job an event is about counts before the session
    holds it, and a failed last run over an earlier result reads as that
    result does (decision 121's alternative)."""
    def job(status, progress=0.0, done=False):
        return SimpleNamespace(status=status, progress=progress, done=done)

    statuses = {"c1": "running", "c2": "done", "c4": "stale", "c5": "done", "c6": "failed"}
    session = SimpleNamespace(status=lambda calc: statuses.get(calc, "none"), calc_jobs={
        "c1": job("running", 0.7), "c2": job("done", 1.0, True),
        "c4": job("failed", done=True), "c5": job("failed", done=True),
        "c6": job("failed", done=True)})
    assert marks.calculation_state(session, "c1") == ("running", 0.7)
    assert marks.mark(*marks.calculation_state(session, "c1")) == "70%"
    assert marks.calculation_state(session, "c2") == ("done", None)
    assert marks.calculation_state(session, "c3") == ("none", None)
    # before its first report a running job reads "running", as in the result's tab
    session.calc_jobs["c1"] = job("running")
    assert marks.mark(*marks.calculation_state(session, "c1")) == "running"
    # the job of an event, which the session does not hold yet
    assert marks.calculation_state(session, "c3", job("queued")) == ("queued", None)
    # a failed run over an earlier result reads as the result does, stale or done, and
    # failed only when no result is kept
    assert marks.calculation_state(session, "c4") == ("stale", None)
    assert marks.calculation_state(session, "c5") == ("done", None)
    assert marks.calculation_state(session, "c6") == ("failed", None)


def test_a_failure_is_told_by_its_final_exception():
    """The engine chains the exceptions on one line; the status row and the
    form show the last one, and a message without one its last line."""
    assert marks.failure_line("CalculationError: Sweep: SweepError: c1 gives no number") == \
        "SweepError: c1 gives no number"
    assert marks.failure_line("CalculationError: Python: ValueError: no band here") == \
        "ValueError: no band here"
    assert marks.failure_line("Traceback\n  File x\n\nKeyError: 'k'\n") == "KeyError: 'k'"
    assert marks.failure_line("timed out after 3 s") == "timed out after 3 s"
    assert marks.failure_line(None) == marks.failure_line("") == ""
