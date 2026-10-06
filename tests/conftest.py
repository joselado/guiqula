"""Test harness (PLAN.md 3.6).

- Qt renders offscreen, with PySide6's platform plugins found explicitly.
- Every test runs with its own tmp_path as the working directory, so pyqula's
  cwd-relative .OUT files can never land in the repository.
- ``shot(widget, name)`` saves a screenshot under ui_dump/<test>/ for Claude
  to inspect with the Read tool (GUIQULA_SHOT_DIR overrides the directory).
- Autosaves and crash reports go to a temporary directory
  ($GUIQULA_DATA_DIR), never to the user's data directory; so does the
  settings file ($GUIQULA_CONFIG_DIR).
- ``run_python(code)`` runs code in a fresh interpreter that sees src/, for
  checks that need a clean process (startup cost, import side effects);
  ``run_python.src`` is that directory.
- Installed guiqula plugins are not loaded ($GUIQULA_NO_PLUGINS).
- After each module the top-level widgets are deleted: a closed window is
  only hidden, and the stale widgets of earlier modules made every
  application-wide restyle (theme, interface text) walk tens of thousands
  of them, which doubled the time of tests/ui.
"""
import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

from guiqula import env  # noqa: E402  (src/ is on sys.path via pyproject)

env.configure_qt(offscreen=True)
os.environ.setdefault("MPLBACKEND", "Agg")   # pyplot never opens a window
# autosaves and crash reports of the whole run (children inherit it) go to a
# temporary directory, never to the user's data directory
os.environ["GUIQULA_DATA_DIR"] = tempfile.mkdtemp(prefix="guiqula-test-data-")
atexit.register(shutil.rmtree, os.environ["GUIQULA_DATA_DIR"], True)
# and the settings file (theme, recent files) never is the user's either
os.environ["GUIQULA_CONFIG_DIR"] = tempfile.mkdtemp(prefix="guiqula-test-config-")
atexit.register(shutil.rmtree, os.environ["GUIQULA_CONFIG_DIR"], True)
# plugins installed on the machine must not change the results (tests/test_plugins.py
# turns them on for its own interpreters)
os.environ["GUIQULA_NO_PLUGINS"] = "1"


@pytest.fixture(autouse=True)
def _scratch_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture(scope="module", autouse=True)
def _delete_windows():
    """Set up before a module's own fixtures, so torn down after them."""
    yield
    if "PySide6.QtWidgets" not in sys.modules:   # a module without Qt imports none
        return
    import gc
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()


@pytest.fixture
def repo():
    return REPO


@pytest.fixture
def shot(request):
    base = Path(os.environ.get("GUIQULA_SHOT_DIR", REPO / "ui_dump"))
    folder = base / re.sub(r"[^\w.-]+", "_", request.node.nodeid)

    def save(widget, name="shot"):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.png"
        assert widget.grab().save(str(path)), f"could not write {path}"
        return path

    return save


@pytest.fixture
def run_python(tmp_path):
    def run(code, env_update=None, timeout=120):
        child_env = dict(os.environ)
        child_env["PYTHONPATH"] = os.pathsep.join(
            [str(SRC)] + [p for p in child_env.get("PYTHONPATH", "").split(os.pathsep) if p])
        child_env.update(env_update or {})
        return subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=child_env,
                              capture_output=True, text=True, timeout=timeout)

    run.src = str(SRC)
    return run


class NoJobs:
    """The part of JobManager a Session uses, for tests that run nothing."""
    names = {}

    def subscribe(self, listener):
        return lambda: None

    def poll(self, timeout=0.0):
        return 0

    def status(self):
        return []

    def supersede(self, kind, label):
        return []

    def build(self, document_json, system, timeout=None, view=False, trusted=True,
              results=None):
        raise RuntimeError("NoJobs runs nothing")

    def shutdown(self):
        pass


@pytest.fixture
def no_jobs():
    return NoJobs()
