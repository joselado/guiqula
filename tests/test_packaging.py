"""Packaging: the vendored pyqula ships as guiqula/_vendor/pyqula and its
runtime dependencies are mirrored in pyproject.toml (PLAN.md section 6)."""
import json
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile

import pytest


def requirement_name(req):
    return re.split(r"[<>=!~;\[ ]", req, maxsplit=1)[0].strip().lower().replace("_", "-")


def test_vendored_dependencies_are_mirrored(repo):
    vendor_md = (repo / "vendor" / "VENDOR.md").read_text()
    upstream = re.findall(r"^\s+- (\S+)$", vendor_md.split("runtime dependencies")[1], re.M)
    assert upstream, "no dependency list found in vendor/VENDOR.md"
    ours = tomllib.loads((repo / "pyproject.toml").read_text())["project"]["dependencies"]
    ours = {requirement_name(r): r for r in ours}
    for req in upstream:
        assert requirement_name(req) in ours, f"{req} (from VENDOR.md) missing in pyproject.toml"
        assert ours[requirement_name(req)] == req, f"pyproject has {ours[requirement_name(req)]}, upstream {req}"


@pytest.mark.slow
def test_wheel_ships_vendored_pyqula(repo, tmp_path, run_python):
    tree = tmp_path / "tree"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info")
    for name in ("pyproject.toml", "setup.py", "LICENSE"):
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / name, tree / name)
    shutil.copytree(repo / "src", tree / "src", ignore=ignore)
    shutil.copytree(repo / "vendor" / "pyqula", tree / "vendor" / "pyqula", ignore=ignore)
    shutil.copy2(repo / "vendor" / "VENDOR.md", tree / "vendor" / "VENDOR.md")
    build = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
         "-w", str(tmp_path / "dist"), str(tree)],
        capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, build.stdout + build.stderr
    (wheel,) = (tmp_path / "dist").glob("guiqula-*.whl")
    names = set(zipfile.ZipFile(wheel).namelist())

    assert "guiqula/__init__.py" in names
    assert "guiqula/ui/app.py" in names
    assert "guiqula/presets/honeycomb_zeeman_rashba.json" in names
    assert "guiqula/_vendor/pyqula/__init__.py" in names
    assert "guiqula/_vendor/pyqula/htk/__init__.py" in names
    assert "guiqula/_vendor/pyqula/datasets/bands_TaS2.txt" in names
    assert "guiqula/_vendor/__init__.py" not in names   # a plain directory, not a package
    assert not [n for n in names if n.endswith((".pyc", ".nbi", ".nbc"))]
    assert not [n for n in names if n.startswith(("vendor/", "pyqula/", "tests/"))]
    upstream = {p.relative_to(repo / "vendor").as_posix()
                for p in (repo / "vendor" / "pyqula").rglob("*.py")
                if "__pycache__" not in p.parts}
    shipped = {n.removeprefix("guiqula/_vendor/") for n in names
               if n.startswith("guiqula/_vendor/") and n.endswith(".py")}
    # every module of a package (a directory with __init__.py) is shipped
    packaged = {m for m in upstream
                if (repo / "vendor" / m).parent.joinpath("__init__.py").is_file()}
    assert packaged <= shipped
    entry_points = next(n for n in names if n.endswith("entry_points.txt"))
    assert "guiqula = guiqula.__main__:main" in zipfile.ZipFile(wheel).read(entry_points).decode()

    # unpacked, the shim finds the shipped copy and pyqula imports from it
    site = tmp_path / "site"
    zipfile.ZipFile(wheel).extractall(site)
    code = ("import sys; sys.path.insert(0, %r)\n"
            "import json, guiqula, pyqula; from guiqula import vendoring\n"
            "print(json.dumps([vendoring.location[0], guiqula.__file__, pyqula.__file__]))"
            % str(site))
    result = run_python(code, env_update={"GUIQULA_PYQULA_PATH": "", "PYTHONPATH": ""})
    assert result.returncode == 0, result.stderr
    origin, guiqula_file, pyqula_file = json.loads(result.stdout.strip().splitlines()[-1])
    assert origin == "vendored"
    assert guiqula_file == str(site / "guiqula" / "__init__.py")
    assert pyqula_file == str(site / "guiqula" / "_vendor" / "pyqula" / "__init__.py")
