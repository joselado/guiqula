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
plain Qt theme, trust prompt for Python nodes, in-app help rendered from pyqula's own
documentation, whose open design points are at the end of section 11), and section 14's
review decisions of the same day (the console is a remote REPL in the worker,
a thin UI already in phase 1, invalid entries are skipped and flagged; the review items
still open are at the end of section 11). Read it before designing anything; update it when
a decision changes.

Status (2026-09-26): phases 0, 1 and 2 are done (PLAN.md section 7 says what each built
and what was left for later). Phase 3 (Hamiltonian workspace, `f(r)` editor, results) is next.

## Code map

The flow is Document -> plan -> engine -> worker -> Result -> plot; everything goes through
a `Session`.

- `core/`: `document.py` (pydantic models; ids unique across the document), `fields.py` and
  `expressions.py` (Fields; the AST-whitelisted expression evaluator), `regions.py`,
  `results.py` (the `Result` dataclass that crosses the process boundary), `hashing.py`.
- `registry/`: one declaration per lattice, op, term and calculation (`lattices.py`,
  `geometry_ops.py`, `terms.py`, `calculations.py`). A declarative `Call("h.add_zeeman", "m")`
  drives both the engine and the script export; a custom entry gives `apply` and `script`.
  `pipeline.py` plans a system without pyqula: the Hilbert-space pre-scan, invalid entries,
  and the stage and calculation keys (staleness). Adding a term = one `entry(...)` call plus
  its case in `tests/engine/test_entries.py` (a completeness test fails otherwise).
- `commands/`: `Dispatcher` (mutations with snapshot undo, actions journaled only);
  `mutations.py` lists every mutation. Command arguments are JSON.
- `engine/`: `build.py` executes a plan (per-stage cache handing out copies, skip on error,
  seeds), `calculations.py` runs an adapter and returns a `Result`, `structure.py` gives the
  canvas its arrays (positions, lattice, sublattice, pyqula's first-neighbour bonds).
- `worker/`: `process.py` (the worker, imports the engine inside `main()` only), `client.py`
  (`JobManager`: interactive and batch workers, cancel, respawn, timeouts), `protocol.py`.
- `session.py`: dispatcher + job manager + results + the latest build of each system
  (coalesced requests) + `modified`; with `autosave=True` (the window's) it autosaves from
  `poll()`. The object tests, `guiqula run`, `tools/drive.py` and the window drive.
- `io/`: project files, presets (`src/guiqula/presets/*.json`, loadable by name), script
  export, result files, `autosave.py` (autosave and recovery), `crashreport.py`.
- `ui/`: `mainwindow.py` (workspaces, palettes from the registry, docks, bars; the window's
  own dispatcher actions `select`, `workspace`, `tool`, `select_sites`,
  `region_from_selection`, `remove_selected`), `outliner.py`, `properties.py` + `forms.py`
  (forms from the parameter declarations), `formulas.py` (mathtext images), `structure.py`
  (canvas and selection tools), `plots.py`, `jobpanel.py`, `bars.py`, `errors.py` (exception
  hook), `theme.py`. The window saves its view state as the Document's `ui` block (not a
  Command, not an unsaved change) and restores it on open and recovery. The window
  polls the session from a `QTimer` and starts the workers after it is shown; a form or tree
  rebuilt from inside one of its own signals must be deleted later (PLAN.md phase 2 facts).

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
  pyqula imports only in `engine/` and `worker/`, and in `registry/` only inside function
  bodies (the UI imports the registry to build its forms, and the UI process must never load
  pyqula, jax or numba, PLAN.md 13.15); every mutation of the Document goes through a
  Command; every registry entry gets an engine test against a direct pyqula call. The import
  rules are enforced by `tests/test_layering.py`, the UI-process rule by
  `tests/ui/test_startup.py`.
- Every stochastic term or calculation (disorder, random guesses, multistart, annealing)
  carries an explicit `seed` that the engine applies before the entry; pyqula itself draws
  from the unseeded global generator. Several `add_*` calls silently turn a Hamiltonian
  spinful or Nambu, so the engine sets the mode from the whole term stack before building
  (PLAN.md 3.1, 3.3).
- Every term parameter is a Field (constant, expression of position, piecewise per region,
  profile, interpolated, painted, from a result; PLAN.md section 3.8), never a bare float. The
  maintainer wants any Hamiltonian parameter spatially modulable from the interface.

## Using the vendored pyqula

`import guiqula` puts the right copy on `sys.path` without importing it
(`src/guiqula/vendoring.py`): `$GUIQULA_PYQULA_PATH` if set (a directory containing `pyqula/`,
or the package directory itself; it then also stops bytecode writes so an upstream checkout
stays untouched), else the shipped `guiqula/_vendor`, else the checkout's `vendor/`. It also
sets `NUMBA_CACHE_DIR` to the user cache, so numba never writes next to pyqula's sources.
Code that needs pyqula calls `vendoring.ensure_pyqula_on_path()`, which raises if no copy is
found or a different pyqula was imported first. By hand, from a scratch directory:

```python
import sys; sys.path.insert(0, "<repo>/src")
import guiqula                                     # or sys.path.insert(0, "<repo>/vendor")
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
plugin. `guiqula.env.configure_qt(offscreen=True)` sets both variables; `tests/conftest.py`,
`tools/drive.py` and `guiqula --offscreen` call it. `pytest-qt` 4.5 and `pyqtgraph` 0.14 are
installed (2026-09-26). Importing pyqtgraph prints a NumPy-ABI traceback from the conda base's
`bottleneck`, which was built against NumPy 1.x; pyqtgraph catches it and works.

## Commands

Nothing is installed: pytest puts `src/` on the path (`pyproject.toml`), and `tools/drive.py`
does it itself. Keep this section in sync with what exists.

```bash
python -m pytest                       # everything (offscreen Qt, worker processes; 2-3 min)
python -m pytest -m "not slow"         # skip the wheel build
python -m pytest tests/core            # pure Python, under a second
python -m pytest tests/engine -k zeeman  # one area / one test
PYTHONPATH=src python -m guiqula [preset|file]         # the window (--offscreen, --version)
PYTHONPATH=src python -m guiqula run honeycomb_zeeman_rashba --calc c1 --out out --script
PYTHONPATH=src python -m guiqula script honeycomb_zeeman_rashba --calc c1   # print the script
python tools/drive.py honeycomb_zeeman_rashba --run c1 --shot bands.png    # drive the window
python tools/drive.py preset --do '{"do": "add_term", "system": "s1", "kind": "haldane"}' \
    --run c1 --widget plotView --shot plot.png     # also --commands FILE, --python CODE,
                                                   # --list-widgets, --no-warm (see --help)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "select_sites", "box": [0.9, -2, 2.1, 2]}' \
    --do '{"do": "remove_selected"}' --widget structureView --shot sculpted.png
python tools/drive.py --recover --shot recovered.png   # unsaved work of a killed session
                                                   # (--hold SECONDS keeps the window running)
tools/update_vendor.sh                 # refresh vendor/ from upstream pyqula
```

`drive.py` prints a JSON report last (document outline, builds, jobs, result summaries,
selection, log tail, screenshot path); a `--do` object names a mutation or an action with
`"do"`, and the driver waits for the rebuild after each one. Autosaves and crash reports go to
the user data directory, or to `$GUIQULA_DATA_DIR` (the test suite sets it). In Python,
`Session("honeycomb_zeeman_rashba", warm=False)` gives the same API: `do(...)`, `act(...)`,
`run_calculation(calc, wait=True)`, `result(calc)`, `status(calc)`, `undo()`, `close()`.

Every test runs with its own `tmp_path` as the cwd (autouse fixture in `tests/conftest.py`),
so pyqula's `.OUT` files never reach the repository. The `shot(widget, name)` fixture saves
screenshots to `ui_dump/<test id>/` (gitignored) for inspection with the Read tool; the
`run_python(code)` fixture runs code in a fresh interpreter that sees `src/`. Tests that
start workers share one `Session`/`JobManager` per module and pass `warm=False`; the first
numba compile of a code path costs seconds once per machine (`NUMBA_CACHE_DIR`).

Do not pipe pytest output through `tail`/`grep` without `set -o pipefail`: the pipe hides
pytest's exit status (a lesson recorded in pyqula's own notes).
