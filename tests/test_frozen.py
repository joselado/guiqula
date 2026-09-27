"""The PyInstaller application folder (packaging/pyinstaller; PLAN.md phase
6, part 3), built and driven: the frozen command line runs a calculation in
its worker processes, and a frozen guiqula serve answers the remote API with
pyqula's docstrings in its help (pyqula is collected as sources).

It needs a Python with PyInstaller and guiqula's dependencies, named by
$GUIQULA_FROZEN_PYTHON (a fresh venv: pip install <guiqula> pyinstaller);
skipped otherwise. About two minutes."""
import json
import os
import signal
import subprocess
from pathlib import Path

import numpy as np
import pytest

from guiqula.remote.client import connect

PYTHON = os.environ.get("GUIQULA_FROZEN_PYTHON")
REPO = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.slow,
              pytest.mark.skipif(not PYTHON, reason="set GUIQULA_FROZEN_PYTHON to a Python "
                                                     "with PyInstaller")]


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    work = tmp_path_factory.mktemp("frozen")
    pyinstaller = [PYTHON, "-m", "PyInstaller", str(REPO / "packaging" / "pyinstaller" /
                                                    "guiqula.spec"), "--noconfirm",
                   "--distpath", str(work / "dist"), "--workpath", str(work / "build")]
    done = subprocess.run(pyinstaller, cwd=REPO, capture_output=True, text=True, timeout=1800)
    assert done.returncode == 0, done.stderr[-3000:]
    return work / "dist" / "guiqula"


def test_the_frozen_command_line_runs_a_calculation(folder, tmp_path, run_python):
    cli = str(folder / ("guiqula-cli.exe" if os.name == "nt" else "guiqula-cli"))
    done = subprocess.run([cli, "run", "honeycomb_zeeman_rashba", "--calc", "c1", "--out", "out"],
                          cwd=tmp_path, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-3000:]
    assert json.loads(done.stdout.splitlines()[-1])["status"] == "done"
    frozen = np.load(tmp_path / "out" / "c1.npz")
    ours = run_python("from guiqula.__main__ import main; main(['run', "
                      "'honeycomb_zeeman_rashba', '--calc', 'c1', '--out', 'ours'])",
                      timeout=600)
    assert ours.returncode == 0, ours.stderr[-3000:]
    assert np.array_equal(frozen["energies"], np.load(tmp_path / "ours" / "c1.npz")["energies"])


def test_a_frozen_server_answers(folder, tmp_path):
    cli = str(folder / ("guiqula-cli.exe" if os.name == "nt" else "guiqula-cli"))
    serve = subprocess.Popen([cli, "serve", "honeycomb_zeeman_rashba", "--no-warm"],
                             cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    try:
        info = json.loads(serve.stdout.readline())
        with connect(info["pid"]) as client:
            assert client.info["pyqula"].startswith("pyqula: bundled copy")
            assert "Adds zeeman to the matrix" in client.call("help", kind="zeeman")["markdown"]
            reply = client.call("run", calculation="c2", timeout=300)
            assert reply["status"] == "done", reply
    finally:
        serve.send_signal(signal.SIGTERM)
        serve.wait(timeout=60)
