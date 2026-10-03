"""Startup budget (PLAN.md 13.15): the window appears quickly and the UI
process never loads pyqula, jax or numba; those live in the worker."""
import json

HEAVY = {"pyqula", "jax", "jaxlib", "numba", "scipy"}   # scipy: the worker finds the bonds
# the 3D drawing with pyvista loads them at its first drawing (ui/pyvista_view.py)
LATER = {"pyvista", "vtkmodules", "vtk"}

# Measured on the development machine on 2026-09-26 (PLAN.md 13.15), warm
# file cache, offscreen, from the first guiqula import to a shown window:
# 0.23 s for the phase-0 placeholder, 0.63 s for the phase-1 window, which
# imports matplotlib and numpy for its plot tab; 0.68 s for the phase-2
# shell (outliner, properties, structure canvas). Importing pyqula alone
# costs 0.7 s. The budget leaves room for a cold cache; the module check is
# the sharp part. Workers start after the window is shown (ui/app.py). The
# empty program shows the start page (PLAN.md phase 8, package P1): its 52
# cards cost about 30 ms to build and their pictures are read after the
# first paint (measured on 2026-10-03).
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
print(json.dumps({"seconds": seconds, "start_page": window.start_page.isVisible(),
                  "loaded": sorted({m.split(".")[0] for m in sys.modules})}))
"""


def test_startup(run_python):
    # with the plugins on (the suite turns them off): listing them is part of the start,
    # 15 ms among 431 installed distributions on the development machine (2026-09-27)
    result = run_python(PROBE, env_update={"GUIQULA_NO_PLUGINS": ""})
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert HEAVY.isdisjoint(out["loaded"]), sorted(HEAVY & set(out["loaded"]))
    assert LATER.isdisjoint(out["loaded"]), sorted(LATER & set(out["loaded"]))
    assert out["start_page"]                    # the empty program shows it, within the budget
    assert out["seconds"] < BUDGET_SECONDS, f"startup took {out['seconds']:.2f} s"
