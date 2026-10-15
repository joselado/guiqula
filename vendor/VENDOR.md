# Vendored pyqula

This directory holds a **read-only local copy** of pyqula used by guiqula
during development. Never edit anything under `vendor/pyqula/`; refresh
the whole copy instead.

- Source: a local checkout of https://github.com/joselado/pyqula (working tree, not git HEAD)
- Upstream HEAD at copy time: `edd19d7bbd42cae771ad286c3bba527a120bdae5` (2026-10-15 12:34:20 +0300)
- Copied on: 2026-10-15
- Uncommitted upstream changes that were included in this copy:
     M src/pyqula/chitk/pairchi.py
     M src/pyqula/chitk/qpi.py
     M src/pyqula/chitk/rpa.py
     M src/pyqula/chitk/spinchi.py
     M src/pyqula/hamiltonians.py
     M src/pyqula/kpointstk/labels.py
     M src/pyqula/ldostk/atomicmultildos.py
     M src/pyqula/meanfield.py
     M src/pyqula/scftk/densitydensity.py
     M src/pyqula/scftk/densitydensity_jax.py
     M src/pyqula/scftk/densitydensity_kpm.py
     M src/pyqula/scftk/kondolattice.py
     M src/pyqula/scftk/spinspin.py
     M src/pyqula/scftk/vjinteraction_jax.py
     M src/pyqula/spinon.py
     M src/pyqula/topology.py
     M src/pyqula/topologytk/berry.py
     M src/pyqula/transporttk/kappa.py
    ?? src/pyqula/scftk/convergence.py

Contents:
- `pyqula/` — the package (`src/pyqula` upstream), without `__pycache__`
- `pyqula_user_guide.md` — upstream's user guide, the pages of `documentation/guide/` in the order of `mkdocs.yml` joined by `tools/assemble_guide.py` (the in-app help)

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
