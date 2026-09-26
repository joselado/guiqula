# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

guiqula is a graphical workbench for pyqula, the maintainer's Python tight-binding library:
one window in which the geometry, the Hamiltonian terms and the calculations are freely
composable (Blender/Inkscape-style non-destructive pipeline). It is a new program, not a
refactor of the maintainer's older `quantum-lattice` GUI (a local checkout of quantum-lattice, one fixed
form per lattice "mode"); see `PLAN.md` section 9 for what it keeps and what it drops.

**`PLAN.md` is the design reference**: requirements as the maintainer stated them, the
decisions made on 2026-09-26 (PySide6; matplotlib embedded in Qt; pyqula vendored inside the
package; embedded console and Python nodes; GPLv3; Linux first, Mac/Windows packaging in
phase 6), the architecture (headless core + command API + worker process + Qt view), the UI
layout, the phased plan, and section 13's further decisions (several systems per document,
regions, headless runner, classical spin/lattice-gas/Ising systems as their own system kinds,
plain Qt theme, trust prompt for Python nodes; only 13.13 in-app help is still open), and
section 14's review decisions of the same day (the console is a remote REPL in the worker,
a thin UI already in phase 1, invalid entries are skipped and flagged; the review items
still open are at the end of section 11). Read it before designing anything; update it when a decision changes. As of 2026-09-26
no application code exists yet (phase 0 not started; the git repository is initialised but has
no commits).

## Hard rules

- **The upstream pyqula repository (a local checkout of upstream pyqula) is read-only from this
  project.** Never edit it, never `pip install -e` it (that writes egg-info into it), never run
  anything with the cwd inside it (pyqula writes `.OUT` files to the cwd). The same applies to
  a local checkout of quantum-lattice.
- `vendor/pyqula/` is a copy of upstream's working tree, and (decision 3) the copy that ships
  inside releases as `guiqula/_vendor/pyqula`, imported as top-level `pyqula` through a
  `sys.path` shim because pyqula imports itself absolutely. Never hand-edit it;
  refresh the whole copy with `tools/update_vendor.sh`, which also rewrites `vendor/VENDOR.md`
  (source path, upstream commit, uncommitted upstream files that were included, upstream's
  runtime dependencies to mirror in `pyproject.toml`). Commit a refresh on its own. `vendor/pyqula_user_guide.md` is upstream's user guide and
  `vendor/pyqula_examples/` its example scripts: check those first for how to call something,
  before grepping the vendored source.
- Every pyqula calculation runs in a scratch directory (the worker's job dir, or the session
  scratchpad when experimenting by hand). Verified: `h.get_bands(write=False)` still writes
  `KPOINTS_BANDS.OUT` and `BANDLINES.OUT` to the cwd.
- Layering (PLAN.md section 3): no Qt imports outside `src/guiqula/ui/` and `src/guiqula/remote/`;
  no pyqula imports in `core/`, `commands/`, `io/`; every mutation of the Document goes through
  a Command; every registry entry gets an engine test against a direct pyqula call.
- Every stochastic term or calculation (disorder, random guesses, multistart, annealing)
  carries an explicit `seed` that the engine applies before the entry; pyqula itself draws
  from the unseeded global generator. Several `add_*` calls silently turn a Hamiltonian
  spinful or Nambu, so the engine sets the mode from the whole term stack before building
  (PLAN.md 3.1, 3.3).
- Every term parameter is a Field (constant, expression of position, piecewise per region,
  profile, interpolated, painted, from a result; PLAN.md section 3.8), never a bare float. The
  maintainer wants any Hamiltonian parameter spatially modulable from the interface.

## Using the vendored pyqula

```python
import sys; sys.path.insert(0, "<repo>/vendor")   # the package is vendor/pyqula
from pyqula import geometry                        # always import submodules explicitly;
                                                   # pyqula/__init__.py exports nothing
```

pyqula's first call compiles numba kernels (about 12 s for a band structure on this machine);
that is compile time, not a hang. Names that are selected by string are listed by pyqula
itself, use those rather than copying lists: `operatorlist.get_operator_names()`,
`meanfield.get_guess_names()`, `sctk.pairing.get_pairing_modes()`,
`kpointstk.labels.get_label_names()`, `extract.get_extractable_names()`.

## Headless Qt (how the UI is tested and driven without clicking)

The interpreter is conda's Python 3.12 with PySide6 6.11.1. Offscreen rendering works, but
the platform plugin is only found when its path is given explicitly:

```bash
QT_QPA_PLATFORM=offscreen \
QT_QPA_PLATFORM_PLUGIN_PATH=$(python -c "import PySide6,os;print(os.path.join(os.path.dirname(PySide6.__file__),'Qt','plugins','platforms'))") \
python some_script.py
```

Under that setup a window builds, buttons can be clicked with `.click()`, and
`widget.grab().save("shot.png")` writes a screenshot that can be inspected with the Read tool.
An interactive matplotlib `QtAgg` canvas embeds and renders offscreen too. The harmless
message `This plugin does not support propagateSizeHints()` is printed by the offscreen
plugin. The test `conftest.py` and `tools/drive.py` are meant to set these variables
themselves (to be written in phase 0); `pytest-qt` and `pyqtgraph` are not installed yet
(`pip install pytest-qt pyqtgraph`).

## Commands

Nothing to build yet. Planned (phase 0), keep this section in sync when they exist:

```bash
python -m pytest tests                 # everything (core, engine, ui offscreen)
python -m pytest tests/ui -k outliner  # one area / one test
python tools/drive.py preset.guiqula --run bands --shot out.png   # drive the app headlessly
tools/update_vendor.sh                 # refresh vendor/ from upstream pyqula
```

Do not pipe pytest output through `tail`/`grep` without `set -o pipefail`: the pipe hides
pytest's exit status (a lesson recorded in pyqula's own notes).
