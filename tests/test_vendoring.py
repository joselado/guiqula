"""The sys.path shim that makes the vendored pyqula importable as top-level
``pyqula`` (PLAN.md section 6, decision 3). Each check runs in a fresh
interpreter, because the shim acts on import."""
import json

import pytest

REPORT = """
import json, sys
import guiqula
from guiqula import vendoring
out = {"imported": "pyqula" in sys.modules, "location": None, "problem": vendoring.problem,
       "numba_cache": __import__("os").environ.get("NUMBA_CACHE_DIR"),
       "no_bytecode": sys.dont_write_bytecode}
if vendoring.location:
    out["location"] = [vendoring.location[0], str(vendoring.location[1])]
    out["first_on_path"] = sys.path[0] == str(vendoring.location[1])
print(json.dumps(out))
"""


def report(run_python, env_update=None, prelude=""):
    result = run_python(prelude + REPORT, env_update=env_update)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture
def fake_pyqula(tmp_path):
    parent = tmp_path / "fake_src"
    (parent / "pyqula").mkdir(parents=True)
    (parent / "pyqula" / "__init__.py").write_text("MARK = 'fake'\n")
    (parent / "pyqula" / "geometry.py").write_text("X = 1\n")
    return parent


def test_checkout_copy_without_importing_pyqula(run_python, repo):
    out = report(run_python, env_update={"GUIQULA_PYQULA_PATH": ""})
    assert out["location"] == ["checkout", str(repo / "vendor")]
    assert out["first_on_path"]
    assert out["imported"] is False          # the shim never imports pyqula
    assert out["problem"] is None
    assert out["no_bytecode"] is False
    assert out["numba_cache"]


def test_checkout_copy_is_the_one_imported(run_python, repo):
    result = run_python("import guiqula, pyqula; print(pyqula.__file__)",
                        env_update={"GUIQULA_PYQULA_PATH": ""})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(repo / "vendor" / "pyqula" / "__init__.py")


@pytest.mark.parametrize("point_at_package", [False, True])
def test_override(run_python, fake_pyqula, point_at_package):
    target = fake_pyqula / "pyqula" if point_at_package else fake_pyqula
    code = REPORT + "import pyqula.geometry; print(pyqula.MARK)\n"
    result = run_python(code, env_update={"GUIQULA_PYQULA_PATH": str(target)})
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    out = json.loads(lines[-2])
    assert out["location"] == ["override", str(fake_pyqula)]
    assert out["no_bytecode"] is True        # nothing written into an upstream tree
    assert lines[-1] == "fake"
    assert not (fake_pyqula / "pyqula" / "__pycache__").exists()


def test_invalid_override_is_reported_not_fatal(run_python, tmp_path):
    out = report(run_python, env_update={"GUIQULA_PYQULA_PATH": str(tmp_path / "nowhere")})
    assert out["location"] is None
    assert "contains no pyqula package" in out["problem"]
    strict = run_python("from guiqula import vendoring; vendoring.ensure_pyqula_on_path()",
                        env_update={"GUIQULA_PYQULA_PATH": str(tmp_path / "nowhere")})
    assert strict.returncode != 0
    assert "VendoringError" in strict.stderr


def test_foreign_pyqula_imported_first(run_python, fake_pyqula):
    prelude = f"import sys; sys.path.insert(0, {str(fake_pyqula)!r}); import pyqula\n"
    out = report(run_python, env_update={"GUIQULA_PYQULA_PATH": ""}, prelude=prelude)
    assert out["location"] is None
    assert "a different pyqula was imported before guiqula" in out["problem"]


def test_numba_cache_respects_user_setting(run_python, tmp_path):
    out = report(run_python, env_update={"NUMBA_CACHE_DIR": str(tmp_path / "nc")})
    assert out["numba_cache"] == str(tmp_path / "nc")
