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
