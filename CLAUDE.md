# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository. It holds what is needed before acting anywhere, and no more, so that it costs
every session little; what matters only in one area lives in `.claude/rules/`, loaded when a file of that area is read or
edited: `ui.md` (the interface: how it is designed, built and checked, its widget names,
and the `drive.py` command that shows each feature) and `engine.md` (the registry, the
engine, the worker, the help and the vendored pyqula). A change of one area updates its
rules file; a fact needed before acting anywhere stays here.

## What this is

guiqula is a graphical workbench for pyqula, the maintainer's Python tight-binding library:
one window in which the geometry, the Hamiltonian terms and the calculations are freely
composable (Blender/Inkscape-style non-destructive pipeline). It is a new program, not a
refactor of the maintainer's older `quantum-lattice` GUI
(https://github.com/joselado/quantum-lattice, one fixed form per lattice "mode"); PLAN.md
section 9 says what it keeps and what it drops.

**`PLAN.md` is the design reference**: the requirements as the maintainer stated them
(section 1), the architecture (section 3: headless core + command API + worker process +
Qt view, and 3.8, any parameter spatially modulable), the window as built (section 4), the
decisions (sections 12 to 14; section 11 records where every former open question was
settled, so no design question is open) and the phases (section 7: what each of phases 0
to 8 built, its report with numbered decisions, and the maintainer's answers). Read it
before designing anything; update it when a decision changes. Status: phases 0 to 8 are
done and merged into master (2026-10-04). A numbered decision stands as built unless the
maintainer answers it; a new change records its decisions, numbered on from the last, at
the end of section 7, the recommended option first.

## Hard rules

- **A local checkout of upstream pyqula (https://github.com/joselado/pyqula) is read-only
  from this project.** Never edit it, never `pip install -e` it (that writes egg-info into
  it), never run anything with the cwd inside it (pyqula writes `.OUT` files to the cwd). The
  same applies to a checkout of quantum-lattice. Where they are on this machine is in
  `CLAUDE.local.md` (gitignored), if present.
- **The repository is public** (github.com/joselado/guiqula, no CI): nothing private goes in
  it. No paths of the maintainer's computer in tracked files (they belong in
  `CLAUDE.local.md`), no Claude session links in commit messages (a commit ends with the
  `Co-Authored-By` line only). Nothing is uploaded or pushed without the maintainer.
- `vendor/pyqula/` is a copy of upstream's working tree, and (decision 3) the copy that ships
  inside releases as `guiqula/_vendor/pyqula`, imported as top-level `pyqula` through a
  `sys.path` shim because pyqula imports itself absolutely. Never hand-edit it; refresh the
  whole copy with `tools/update_vendor.sh`, committed on its own (`engine.md` says what the
  refresh does and the one exception). `vendor/` holds the package and
  `vendor/pyqula_user_guide.md`, upstream's user guide (the in-app help), and nothing else of
  upstream.
- Every pyqula calculation runs in a scratch directory (the worker's job dir, or the session
  scratchpad when experimenting by hand). Verified: `h.get_bands(write=False)` still writes
  `KPOINTS_BANDS.OUT` and `BANDLINES.OUT` to the cwd.
- Layering (PLAN.md section 3): no Qt imports outside `src/guiqula/ui/` and
  `src/guiqula/remote/`; pyqula imports only in `engine/` and `worker/`, and in `registry/`
  only inside function bodies (the UI imports the registry to build its forms, and the UI
  process must never load pyqula, jax or numba, PLAN.md 13.15); every mutation of the
  Document goes through a Command; every registry entry gets an engine test against a
  direct pyqula call. The import rules are enforced by `tests/test_layering.py`, the
  UI-process rule by `tests/ui/test_startup.py`.
- Every stochastic term or calculation (disorder, random guesses, multistart, annealing)
  carries an explicit `seed` that the engine applies before the entry; pyqula itself draws
  from the unseeded global generator. Several `add_*` calls silently turn a Hamiltonian
  spinful or Nambu, so the engine sets the mode from the whole term stack before building
  (PLAN.md 3.1, 3.3).
- Every term parameter is a Field (constant, expression of position, piecewise per region,
  profile, interpolated, painted, from a result; PLAN.md section 3.8), never a bare float.
  The maintainer wants any Hamiltonian parameter spatially modulable from the interface.
- The documentation (`src/guiqula/docs/user_guide.md`, the README, this file and the rules
  files) is the last package of any change, in the voice of `~/.claude/CLAUDE.md`.

## Code map

The flow is Document -> plan -> engine -> worker -> Result -> plot; everything goes through
a `Session`. Most modules open with a docstring saying what they are and which PLAN.md
section or decision they build, so this map is an index; the rules files hold what the docstrings do
not carry.

- `core/`: the Document and what the engine and the UI share without pyqula. `document.py`
  (pydantic models; ids unique across the document; a quantum system's Hamiltonian =
  construction, terms, mean-field block; a classical system's `model` = the model entry's
  set-up and its terms; `terms_of(system)`; an entry's `name` is left out of the JSON when
  empty, never in a key), `fields.py` and `expressions.py` (the Field kinds of 3.8 and the
  AST-whitelisted expression evaluator), `regions.py`, `nearest.py` (the stored point
  nearest to a position within a tolerance, by a cell hash: regions by positions, painted
  and from_result Fields and the canvas selection use it, never an N x M scan), `locks.py`
  (what a teaching preset locks; the dispatcher refuses a mutation that changes a locked
  thing), `results.py` (`Result`, what crosses the process boundary, and `ResultRef`, what
  a from_result Field reads), `picks.py` (a point of a plot as the values it stands for,
  `QUANTITIES` and `AXES`), `bonds.py` (a site Field at the bond midpoints), `hashing.py`.
- `registry/`: one declaration per lattice, op, term, mean field and calculation
  (`lattices.py`, `geometry_ops.py`, `terms.py`, `meanfield.py`, `calculations.py`,
  `classical.py`, `python_nodes.py`, `sweeps.py`, `kpaths.py`, `picks.py`; `base.py` and
  `params.py` are the declarations themselves); `pipeline.py` plans a system without pyqula
  (the stage and calculation keys, the invalid entries, trust); `plugins.py` loads the
  plugins after the built-in entries; `cost.py` estimates durations (the cost guard). How an
  entry is declared, tested and exported is in `engine.md`.
- `docs/`: the in-app help, without pyqula imports: `guide.py` (pyqula's guide in sections,
  an anchor being a heading's text), `docstrings.py` (pyqula's docstrings read with `ast`),
  `entries.py` (an item's help), `user_guide.md` (guiqula's own guide: the program, never
  pyqula's physics; its shortcut table is checked against `ui/shortcuts.py`).
  `tests/test_help.py` checks every anchor an entry names, `tests/engine/test_help_docstrings.py`
  every docstring.
- `commands/`: `Dispatcher` (mutations with snapshot undo, actions journaled only; each undo
  step named by `steps.py`, which a new mutation needs a text in, and `undo(steps)`);
  `mutations.py` lists every mutation. Command arguments are JSON.
- `engine/`: `build.py` executes a plan (per-stage cache, the seeds, the mode from the term
  stack, `meanfield=False` and `sparse_above` for the interactive builds), `calculations.py`
  runs an adapter and returns a `Result`, `structure.py` gives the canvas its arrays,
  `context.py` is what an entry sees while it is applied (its parameters compiled for pyqula,
  the script text, pyqula's name lists).
- `worker/`: `process.py` (the worker; imports the engine inside `main()` only; its
  `Console` is the Python console's interpreter), `client.py` (`JobManager`: the interactive,
  batch and console workers, cancel, respawn, timeouts, `request_handler` answering a job's
  REQUEST), `protocol.py`.
- `session.py`: dispatcher + job manager + results + the latest build of each system
  (coalesced requests; a stuck build is killed when a newer one is asked) + `modified` +
  `trusted` (`always_trust`: the window's setting) + the console (`console(code)`) + a few
  earlier results per calculation (an undo brings the matching one back) + the plans and
  keys of the current Document object, reused until it, the results or trust change; actions
  `undo`, `redo`, `history`; with `autosave=True` (the window's) it autosaves from `poll()`.
  `ACTIONS` names its dispatcher actions. The object tests, `guiqula run`, `tools/drive.py`,
  the window and the remote API all drive it.
- `remote/` (the Claude add-on, PLAN.md 3.7): `api.py` (`RemoteAPI`, the methods a client
  calls over a Session, JSON in and out; `WINDOW_ACTIONS` is the one list of the window's
  actions with their arguments, checked by tests against the window and `tools/drive.py`'s
  help), `server.py` (JSON-RPC 2.0, one message per line, on 127.0.0.1, `hello` with the
  token first; polled from the host's loop, never a thread of its own, so the Session
  stays single-threaded), `connection.py` (connection files, mode 0600, in
  `$GUIQULA_DATA_DIR/remote`), `client.py` (`connect()`), `mcp.py` (`guiqula mcp`, the MCP
  protocol written by hand; fd 1 points at stderr so nothing but protocol reaches stdout),
  `window.py` (the window's hooks: screenshots, widget names, its state).
- `io/`: `project.py` (a `.guiqula` zip keeps the results too), the presets
  (`src/guiqula/presets/*.json`, loadable by name, described by the Document's `notes`;
  those with locks, `ssh_chain` and `graphene_basics`, are the gallery's teaching group),
  `script.py` (the script export; a sweep exports a loop), `results.py` (result files),
  `autosave.py` (autosave and recovery), `crashreport.py`, `bundle.py` (Export figure,
  data and script, one folder per result), `settings.py` (only what was set,
  `settings.chosen`, in `$GUIQULA_CONFIG_DIR`; only the interactive window,
  `use_settings=True`, reads or writes it, so tests and drivers run with Run at once off
  unless they turn it on).
- `ui/`: the window as PLAN.md section 4 draws it, one module per panel, bar or drawing;
  `app.py` is the entry point and `mainwindow.py` the shared file. The modules, their widget
  names, their gotchas and their tests are catalogued in `ui.md`.
- `desktop.py` (`guiqula desktop`: the menu entry, icon and `.guiqula` file type for the
  current user), `env.py` (the Qt and numba environment, `launcher()`, the command that
  starts guiqula again), `vendoring.py` (which pyqula copy is used), `__main__.py` (the
  subcommands), `resources/` (the icon, `thumbnails/` and `icons/`: PNG and SVG files
  shipped as package data and made by the scripts in `tools/`), `plugin_template/` (a plugin
  package with its test), `packaging/README.md` (what each distribution is, pip only, and
  the release checklist; built and uploaded by hand, there is no CI).

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
`kpointstk.labels.get_label_names()`, `extract.get_extractable_names()`. For how to call
something, check `vendor/pyqula_user_guide.md` first, then upstream's `examples/` (in the
pyqula checkout, or on GitHub), before grepping the vendored source.

## Headless Qt (how the UI is tested and driven without clicking)

The interpreter on `PATH` is anaconda's base Python 3.14.6 with PySide6 6.11.0, outside
the declared 3.12 and 3.13; the whole suite passes on it. Offscreen rendering works, but
the platform plugin is only found when `QT_QPA_PLATFORM_PLUGIN_PATH` names PySide6's
`Qt/plugins/platforms` directory next to `QT_QPA_PLATFORM=offscreen`, which
`guiqula.env.configure_qt(offscreen=True)` sets (`tests/conftest.py`, `tools/drive.py` and
`guiqula --offscreen` call it). Under that setup a window builds, buttons can be clicked
with `.click()`, an interactive matplotlib `QtAgg` canvas embeds and renders, and
`widget.grab().save("shot.png")` writes a screenshot that can be inspected with the Read
tool. The message `This plugin does not support propagateSizeHints()` is the offscreen
plugin's and harmless. `pytest-qt` 4.5.0 is installed (without it every test using `qapp`
or `qtbot` errors at setup); `pyqtgraph`, the `fast` extra, is not, and no test needs it;
pyvista 0.48.4 with VTK 9.6.2, the `3d` extra, is (`tests/ui/test_pyvista_view.py` skips
without it). `tests/ui/test_startup.py` keeps a 2 s budget on the start of the window,
which holds on a quiet machine and not under the load of several suites at once, so a
failure there under load is the load before it is the code: measure it alternately against
an older tree (a `git worktree add --detach` in a `mktemp -d` directory) rather than once.

## Commands

Nothing is installed: pytest puts `src/` on the path (`pyproject.toml`), and `tools/drive.py`
and the launcher `./guiqula` do it themselves (the launcher also through `PYTHONPATH`, for
what `env.launcher()` starts, and its `__main__` guard is what keeps the spawned workers
from running `main()` again). Keep this section in sync with what exists. `tools/drive.py
--help` is the catalogue of the window's actions, and `ui.md` has the `drive.py` command
that shows each feature.

```bash
python -m pytest                       # everything (offscreen Qt, worker processes; about
                                       # 17 min on this machine)
python -m pytest -m "not slow"         # skip the wheel build
python -m pytest tests/core            # pure Python, under a second
python -m pytest tests/engine -k zeeman  # one area / one test
./guiqula [preset|file]                # the window, from the checkout (any subcommand below too)
PYTHONPATH=src python -m guiqula [preset|file]         # the window (--offscreen, --remote, --version)
PYTHONPATH=src python -m guiqula run honeycomb_zeeman_rashba --calc c1 --out out --script
PYTHONPATH=src python -m guiqula script honeycomb_zeeman_rashba --calc c1   # print the script
PYTHONPATH=src python -m guiqula serve preset         # a session without a window, remotely driven
PYTHONPATH=src python -m guiqula mcp [--attach|--headless] [--document D]   # the MCP add-on
claude mcp add guiqula -e PYTHONPATH=$PWD/src -- python -m guiqula mcp  # register it (checkout)
<python with the mcp SDK> tools/mcp_check.py --python $(which python)  # the SDK's client vs mcp
PYTHONPATH=src python -m guiqula desktop [--remove]   # menu entry, icon, file type (this user)
python tools/drive.py honeycomb_zeeman_rashba --run c1 --shot bands.png    # drive the window
python tools/drive.py preset --do '{"do": "add_term", "system": "s1", "kind": "haldane"}' \
    --run c1 --widget plot_c1 --shot plot.png      # also --commands FILE, --python CODE,
                                                   # --list-widgets, --no-warm, --trust (--help)
python -m build && twine check --strict dist/*   # sdist and wheel (packaging/README.md)
python tools/make_icons.py             # the PNG, ICO and ICNS from resources/guiqula.svg
python tools/make_thumbnails.py [name ...]   # the start page's pictures (resources/thumbnails),
                                             # after a new lattice, classical system or preset
python tools/readme_images.py [name ...]   # the README's screenshots (docs/images), by drive.py
tools/update_vendor.sh /path/to/pyqula  # refresh vendor/ from upstream pyqula ($PYQULA_SRC)
```

`drive.py` prints a JSON report last (its help says what it holds); a `--do` object names a
mutation or an action with `"do"`, and the driver waits for the rebuild after each one
(`--do` runs before `--run`, `--python` after). Autosaves and crash reports go to the user
data directory, or to `$GUIQULA_DATA_DIR` (the test suite sets it); the settings file to the
user config directory, or `$GUIQULA_CONFIG_DIR` (set by the test suite too). In Python,
`Session("honeycomb_zeeman_rashba", warm=False)` gives the same API: `do(...)`, `act(...)`,
`run_calculation(calc, wait=True)`, `result(calc)`, `status(calc)`, `undo()`, `close()`.

Every test runs with its own `tmp_path` as the cwd (autouse fixture in `tests/conftest.py`),
so pyqula's `.OUT` files never reach the repository. The `shot(widget, name)` fixture saves
screenshots to `ui_dump/<test id>/` (gitignored) for inspection with the Read tool; the
`run_python(code)` fixture runs code in a fresh interpreter that sees `src/`. Tests that
start workers share one `Session`/`JobManager` per module and pass `warm=False`; the first
numba compile of a code path costs seconds once per machine (`NUMBA_CACHE_DIR`). Do not pipe
pytest output through `tail`/`grep` without `set -o pipefail`: the pipe hides pytest's exit
status.
