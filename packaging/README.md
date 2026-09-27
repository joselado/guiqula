# Building and releasing guiqula

What each distribution is, how it is built, and what has been verified (PLAN.md section 6,
phase 6, and the maintainer's answers to its report: pip is the only installer, no GitHub
CI, releases are built and uploaded by hand).

| what | built by | verified |
|---|---|---|
| sdist and wheel (PyPI) | `python -m build` (the wheel is built from the sdist) | Linux: `tests/test_packaging.py` (builds without isolation: it needs setuptools 77 or newer and `build`, in the `test` extra); a clean venv installs the wheel from PyPI's dependencies and runs; the full suite on Python 3.12 and 3.13 |
| conda environment | `environment.yml` (conda-forge stack, guiqula and Qt from PyPI) | the file's list is checked against `pyproject.toml`; not solved here |
| menu entry, icon, file type | `guiqula desktop` (`src/guiqula/desktop.py`) | Linux (`tests/test_desktop.py`, `desktop-file-validate`); Windows and macOS: the files are tested as text, never applied |

## A release

1. `tools/update_vendor.sh /path/to/pyqula` if pyqula changed (a commit of its own), and
   the full test suite green (`python -m pytest`) on Python 3.12 and 3.13.
2. The version in `src/guiqula/__init__.py`, and a note in PLAN.md.
3. `rm -rf dist && python -m build && twine check --strict dist/*`; try the wheel in a
   fresh venv (`pip install dist/guiqula-X.Y.Z-py3-none-any.whl`, then `guiqula run
   honeycomb_zeeman_rashba --calc c1 --out smoke` from a scratch directory).
4. The maintainer uploads: `twine upload dist/*` (a PyPI API token), then tags
   `vX.Y.Z` and pushes the tag.
