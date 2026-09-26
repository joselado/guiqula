"""Test harness (PLAN.md 3.6).

- Qt renders offscreen, with PySide6's platform plugins found explicitly.
- Every test runs with its own tmp_path as the working directory, so pyqula's
  cwd-relative .OUT files can never land in the repository.
- ``shot(widget, name)`` saves a screenshot under ui_dump/<test>/ for Claude
  to inspect with the Read tool (GUIQULA_SHOT_DIR overrides the directory).
- ``run_python(code)`` runs code in a fresh interpreter that sees src/, for
  checks that need a clean process (startup cost, import side effects).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

from guiqula import env  # noqa: E402  (src/ is on sys.path via pyproject)

env.configure_qt(offscreen=True)
os.environ.setdefault("MPLBACKEND", "Agg")   # pyplot never opens a window


@pytest.fixture(autouse=True)
def _scratch_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


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

    return run
