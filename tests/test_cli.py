"""The ``guiqula`` / ``python -m guiqula`` entry point."""
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
