# Building and releasing guiqula

What each distribution is, how it is built, and what has been verified (PLAN.md section 6
and phase 6, part 3). The CI workflows in `.github/workflows/` build all of them once the
repository has a GitHub remote.

| what | built by | verified |
|---|---|---|
| sdist and wheel (PyPI) | `python -m build` (the wheel is built from the sdist) | Linux: `tests/test_packaging.py`; a clean venv installs the wheel from PyPI's dependencies and runs |
| conda environment | `environment.yml` (conda-forge stack, guiqula and Qt from PyPI) | the file's list is checked against `pyproject.toml`; not solved here |
| menu entry, icon, file type | `guiqula desktop` (`src/guiqula/desktop.py`) | Linux (`tests/test_desktop.py`, `desktop-file-validate`); Windows and macOS: the files are tested as text, never applied |
| application folder | `pyinstaller packaging/pyinstaller/guiqula.spec` | Linux: the frozen `guiqula-cli run`, `serve` and the window, driven through the remote API |
| Windows installer | Inno Setup: `iscc /DVersion=X packaging/windows/guiqula.iss` | not built (no Windows here) |
| macOS disk image | `hdiutil create` of `dist/guiqula.app` (release workflow) | not built (no macOS here); unsigned |

## The application folder (PyInstaller)

In an environment with guiqula's dependencies and PyInstaller (a fresh venv is best: a
conda base drags hundreds of packages into the analysis):

```
python -m venv build-env && build-env/bin/pip install . pyinstaller
build-env/bin/pyinstaller packaging/pyinstaller/guiqula.spec --noconfirm
dist/guiqula/guiqula-cli run honeycomb_zeeman_rashba --calc c1 --out smoke
```

`dist/guiqula/` holds `guiqula` (the window) and `guiqula-cli` (a console program for
`run`, `serve`, `script`, `mcp`), sharing `_internal/` (about 900 MB on Linux: jaxlib
340 MB and llvmlite 170 MB, both pyqula's dependencies, and Qt 100 MB). pyqula is
collected as source files; `packaging/pyinstaller/launcher.py` calls
`multiprocessing.freeze_support()`, without which the worker processes could not start.
`tests/test_frozen.py` builds and drives the folder when `$GUIQULA_FROZEN_PYTHON` names a
Python with PyInstaller and guiqula's dependencies.

## A release

1. `tools/update_vendor.sh` if pyqula changed (a commit of its own), and the full test
   suite green (`python -m pytest`), on every platform through `tests.yml`.
2. The version in `src/guiqula/__init__.py`, and a note in PLAN.md.
3. `python -m build && twine check --strict dist/*`; try the wheel in a fresh venv.
4. Tag `vX.Y.Z` and push: `release.yml` builds the artifacts and uploads to PyPI through
   trusted publishing (configured once on PyPI for the repository, with a `pypi`
   environment on GitHub). By hand instead: `twine upload dist/*`.
5. Attach the installers from the workflow's artifacts to the GitHub release.

The macOS bundle is not signed or notarized (that needs an Apple developer account):
the first start needs a right click > Open. The Windows installer is not signed either:
SmartScreen warns once.
