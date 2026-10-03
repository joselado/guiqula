"""The marks of a state, one set for the outliner's rows, the result tabs and
the status row above a plot (PLAN.md section 7, phase 8, P7): Unicode until
the icons of P8 draw them.

No Qt here, so that the outliner, the window and the tests read the same
strings."""

DONE = "✓"       # check mark
STALE = "↻"      # clockwise open circle arrow
FAILED = "✗"     # ballot x
INVALID = "✗"
DISABLED = "○"   # white circle
LOCKED = "locked"

MARKS = {
    "done": DONE,
    "stale": STALE,
    "failed": FAILED,
    "invalid": INVALID,
    "disabled": DISABLED,
    "locked": LOCKED,
}

# drawn in the theme's error colour
ERROR_STATES = frozenset({"failed", "invalid"})


def mark(state, progress=None):
    """The mark of `state`; a running job shows its progress, a fraction from
    0 to 1, as "70%", and "running" before its first report."""
    if state == "running":
        return "running" if progress is None else f"{round(100 * progress)}%"
    return MARKS.get(state, "")
