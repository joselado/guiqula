"""The ``guiqula`` / ``python -m guiqula`` entry point."""
import guiqula


def test_version(run_python):
    result = run_python("import sys; from guiqula.__main__ import main; sys.exit(main(['--version']))")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"guiqula {guiqula.__version__}"
