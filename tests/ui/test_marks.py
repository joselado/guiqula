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
    """The state is the session's, the progress a running job's only."""
    job = SimpleNamespace(progress=0.7)
    session = SimpleNamespace(status=lambda calc: {"c1": "running", "c2": "done"}.get(
        calc, "none"), calc_jobs={"c1": job, "c2": SimpleNamespace(progress=1.0)})
    assert marks.calculation_state(session, "c1") == ("running", 0.7)
    assert marks.mark(*marks.calculation_state(session, "c1")) == "70%"
    assert marks.calculation_state(session, "c2") == ("done", None)
    assert marks.calculation_state(session, "c3") == ("none", None)
