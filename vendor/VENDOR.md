# Vendored pyqula

This directory holds a **read-only local copy** of pyqula used by guiqula
during development. Never edit anything under `vendor/pyqula/`; refresh
the whole copy instead.

- Source: a local checkout of https://github.com/joselado/pyqula (working tree, not git HEAD)
- Upstream HEAD at copy time: `0cdb0632e03929f0144e396e3be43b8943b17bec` (2026-10-06 12:53:33 +0300)
- Copied on: 2026-10-06
- Uncommitted upstream changes that were included in this copy:
    (none)

Contents:
- `pyqula/` — the package (`src/pyqula` upstream), without `__pycache__`
- `pyqula_user_guide.md` — upstream `documentation/user_guide.md` (the in-app help)

Upstream runtime dependencies at copy time (mirror them in guiqula's
`pyproject.toml`; optional extras are not listed):
    - numpy>=2.1
    - scipy>=1.13.1
    - matplotlib>=3.10.0
    - numba>=0.60.0
    - multiprocess>=0.70.19
    - dill>=0.4.1
    - threadpoolctl>=3.5.0
    - jax>=0.8.1

Refresh with `tools/update_vendor.sh` (re-runs the same rsync and rewrites
this file). The upstream checkout it is copied from must never be
modified from a guiqula session: no edits, no `pip install -e`, no running
scripts with the cwd inside it (pyqula writes `.OUT` files to the cwd).
