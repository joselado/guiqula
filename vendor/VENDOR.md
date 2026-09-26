# Vendored pyqula

This directory holds a **read-only local copy** of pyqula used by guiqula
during development. Never edit anything under `vendor/pyqula/`; refresh
the whole copy instead.

- Source: a local checkout of upstream pyqula (working tree, not git HEAD)
- Upstream HEAD at copy time: `f8087b43e9011228dddf17e62a6809dde77e14dc` (2026-09-26 17:57:58 +0300)
- Copied on: 2026-09-26
- Uncommitted upstream changes that were included in this copy:
    (none)

Contents:
- `pyqula/` — the package (`src/pyqula` upstream), without `__pycache__`
- `pyqula_user_guide.md` — upstream `documentation/user_guide.md`
- `pyqula_examples/` — upstream `examples/` (scripts only, outputs stripped)

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
this file). The upstream repository at the source path above must never be
modified from a guiqula session: no edits, no `pip install -e`, no running
scripts with the cwd inside it (pyqula writes `.OUT` files to the cwd).
