"""The ``guiqula`` / ``python -m guiqula`` entry point, and ``./guiqula``."""
import json
import os
import subprocess
import sys

import guiqula


def test_version(run_python):
    result = run_python("import sys; from guiqula.__main__ import main; sys.exit(main(['--version']))")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"guiqula {guiqula.__version__}"


def test_mistakes_are_one_line_not_a_traceback(run_python, tmp_path):
    """A document, calculation or output folder that cannot be used is one
    line on stderr and exit status 2, as argparse does for its own errors."""
    (tmp_path / "afile").write_text("")
    for args, message in (
            (["script", "honeycomb_zeeman_rashba", "--calc", "c9"],
             "guiqula script: no calculation 'c9' (calculations: c1, c2)\n"),
            (["run", "honeycomb_zeeman_rashba", "--calc", "c9"], "guiqula run: no calculation"),
            (["run", "nope"], "guiqula run: nope: no such file and no such preset"),
            (["run", "honeycomb_zeeman_rashba", "--out", "afile"], "guiqula run: [Errno"),
            (["serve", "nope"], "guiqula serve: nope: no such file")):
        result = run_python(f"import sys; from guiqula.__main__ import main; sys.exit(main({args!r}))")
        assert result.returncode == 2, (args, result.stderr)
        assert result.stderr.startswith(message) and "Traceback" not in result.stderr, result.stderr


def test_checkout_launcher(repo, tmp_path):
    """./guiqula runs main() from a checkout with nothing on PYTHONPATH, from
    any directory, and its spawned workers find src/ too."""
    launcher = repo / "guiqula"
    assert os.access(launcher, os.X_OK)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run([sys.executable, str(launcher), "--version"], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.stdout.strip() == f"guiqula {guiqula.__version__}", result.stderr
    result = subprocess.run([sys.executable, str(launcher), "run", "honeycomb_zeeman_rashba",
                             "--calc", "c1", "--out", "out"], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1])["status"] == "done"
    assert (tmp_path / "out" / "c1.npz").is_file()
