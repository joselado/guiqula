"""guiqula: a graphical workbench for the pyqula tight-binding library.

Importing guiqula puts the right pyqula copy on sys.path (guiqula.vendoring)
and points numba's cache at the user cache directory (guiqula.env). It
imports neither pyqula nor Qt: the UI process stays free of pyqula, jax and
numba (PLAN.md 13.15), and the headless parts stay free of Qt (PLAN.md 3).
"""
__version__ = "0.0.1.dev0"

from guiqula import env as _env
from guiqula import vendoring as _vendoring

_env.configure_numba_cache()
# Not strict: a missing or shadowed pyqula must not stop the window from
# opening. The problem is recorded in vendoring.problem and raised by
# vendoring.ensure_pyqula_on_path() where pyqula is actually needed.
_vendoring.ensure_pyqula_on_path(strict=False)
