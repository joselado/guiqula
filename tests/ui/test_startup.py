"""Startup budget (PLAN.md 13.15): the window appears quickly and the UI
process never loads pyqula, jax or numba; those live in the worker."""
import json

HEAVY = {"pyqula", "jax", "jaxlib", "numba"}

# Measured on the development machine on 2026-09-26 (PLAN.md 13.15), warm
# file cache, offscreen: 0.23 s from the first guiqula import to a shown
# window, 0.3 s wall-clock including interpreter start. The budget leaves
# room for a cold cache and for matplotlib, which the phase-1 window adds;
# importing pyqula alone costs 0.7 s. The module check is the sharp part.
BUDGET_SECONDS = 2.0

PROBE = """
import json, sys, time
t0 = time.perf_counter()
from guiqula import env
env.configure_qt(offscreen=True)
from guiqula.ui.app import build_main_window, create_application
app = create_application()
window = build_main_window()
window.show()
app.processEvents()
seconds = time.perf_counter() - t0
print(json.dumps({"seconds": seconds,
                  "loaded": sorted({m.split(".")[0] for m in sys.modules})}))
"""


def test_startup(run_python):
    result = run_python(PROBE)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert HEAVY.isdisjoint(out["loaded"]), sorted(HEAVY & set(out["loaded"]))
    assert out["seconds"] < BUDGET_SECONDS, f"startup took {out['seconds']:.2f} s"
