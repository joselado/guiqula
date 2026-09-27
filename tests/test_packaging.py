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


def test_the_conda_environment_mirrors_the_dependencies(repo):
    """environment.yml has every dependency of pyproject.toml with the same bound
    (matplotlib as conda-forge's matplotlib-base), except Qt, which pip brings."""
    lines = (repo / "environment.yml").read_text().split("dependencies:")[1].splitlines()
    conda = {requirement_name(line.strip()[2:]): line.strip()[2:] for line in lines
             if line.startswith("  - ") and not line.strip().endswith(":")}
    conda["matplotlib"] = conda.pop("matplotlib-base").replace("-base", "")
    ours = tomllib.loads((repo / "pyproject.toml").read_text())["project"]["dependencies"]
    for req in ours:
        name = requirement_name(req)
        if name == "pyside6-essentials":
            assert not [n for n in conda if n.startswith("pyside")]    # two Qt copies break it
            continue
        assert conda.get(name) == req, f"environment.yml: {conda.get(name)}, pyproject: {req}"
    assert "guiqula" in (repo / "environment.yml").read_text().split("pip:")[1]


@pytest.mark.slow
def test_wheel_ships_vendored_pyqula(repo, tmp_path, run_python):
    """What pip does with a source distribution: the sdist from the files git
    knows, then the wheel from the sdist (setup.py needs vendor/'s guide in it)."""
    listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                            cwd=repo, capture_output=True, text=True, check=True).stdout.split()
    tree = tmp_path / "tree"
    for name in listed:
        if (repo / name).is_file() and not name.startswith("ui_dump/"):
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / name, tree / name)
    build = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--wheel", "--no-isolation",
         "--outdir", str(tmp_path / "dist"), str(tree)],
        capture_output=True, text=True, timeout=900)
    assert build.returncode == 0, build.stdout[-3000:] + build.stderr[-3000:]
    (sdist,) = (tmp_path / "dist").glob("guiqula-*.tar.gz")
    (wheel,) = (tmp_path / "dist").glob("guiqula-*.whl")
    import tarfile
    in_sdist = {n.split("/", 1)[1] for n in tarfile.open(sdist).getnames() if "/" in n}
    assert {"README.md", "LICENSE", "environment.yml", "vendor/pyqula_user_guide.md",
            "vendor/VENDOR.md", "plugin_template/pyproject.toml"} <= in_sdist
    assert not [n for n in in_sdist if n.startswith(("tests/", "ui_dump/", "tools/"))]
    if shutil.which("twine"):
        check = subprocess.run(["twine", "check", "--strict", str(sdist), str(wheel)],
                               capture_output=True, text=True, timeout=300)
        assert check.returncode == 0, check.stdout + check.stderr
    names = set(zipfile.ZipFile(wheel).namelist())

    assert "guiqula/__init__.py" in names
    assert "guiqula/ui/app.py" in names
    assert "guiqula/presets/honeycomb_zeeman_rashba.json" in names
    assert "guiqula/_vendor/pyqula/__init__.py" in names
    assert "guiqula/_vendor/pyqula/htk/__init__.py" in names
    assert "guiqula/_vendor/pyqula/datasets/bands_TaS2.txt" in names
    assert "guiqula/_vendor/__init__.py" not in names   # a plain directory, not a package
    assert "guiqula/_vendor/pyqula_user_guide.md" in names   # the in-app help (13.13)
    assert "guiqula/docs/user_guide.md" in names
    assert {"guiqula/resources/guiqula.png", "guiqula/resources/guiqula.svg",
            "guiqula/resources/guiqula.ico", "guiqula/resources/guiqula.icns"} <= names
    metadata = zipfile.ZipFile(wheel).read(next(n for n in names if n.endswith("METADATA")))
    assert b"License-Expression: GPL-3.0-or-later" in metadata
    assert b"Description-Content-Type: text/markdown" in metadata and b"# guiqula" in metadata
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
            "guide = [str(p) for p in vendoring.find_guide()]\n"
            "print(json.dumps([vendoring.location[0], guiqula.__file__, pyqula.__file__, guide]))"
            % str(site))
    result = run_python(code, env_update={"GUIQULA_PYQULA_PATH": "", "PYTHONPATH": ""})
    assert result.returncode == 0, result.stderr
    origin, guiqula_file, pyqula_file, guide = json.loads(result.stdout.strip().splitlines()[-1])
    assert guide == ["vendored", str(site / "guiqula" / "_vendor" / "pyqula_user_guide.md")]
    assert origin == "vendored"
    assert guiqula_file == str(site / "guiqula" / "__init__.py")
    assert pyqula_file == str(site / "guiqula" / "_vendor" / "pyqula" / "__init__.py")
