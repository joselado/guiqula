# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

guiqula is a graphical workbench for pyqula, the maintainer's Python tight-binding library:
one window in which the geometry, the Hamiltonian terms and the calculations are freely
composable (Blender/Inkscape-style non-destructive pipeline). It is a new program, not a
refactor of the maintainer's older `quantum-lattice` GUI
(https://github.com/joselado/quantum-lattice, one fixed form per lattice "mode"); see `PLAN.md` section 9 for what it keeps and what it drops.

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

Status (2026-09-26): phases 0 to 3 are done and the maintainer has answered the phase-3
report (PLAN.md section 7 says what each phase built, what was left for later, and the
answers). Phase 4 is done (2026-09-27, in parts 1 to 4b: the breadth of the registry and the
plot kinds, Python nodes, trust and the console, classical systems and `from_result` Fields,
results in projects, presets gallery, overlays, sweeps, sliders, the Brillouin-zone canvas,
the remaining Fields and the brush); the maintainer asked for phase 5 without commenting
on its report, so its items stand as built. Phase 5 (polish) is done (2026-09-27, in four
parts: settings, themes, shortcuts, undo; teaching exports and locks; performance; the in-app
help); its report, numbered design items 1 to 14 and decisions 15 to 24 (PLAN.md section 7,
end of phase 5; items 1 to 7 are the in-app help's open points of section 11), was not
commented on (phase 6 was asked for), so its items stand as built. Phase 6 (distribution
and the add-on) is done (2026-09-27, in three parts: remote control and the MCP add-on;
plugins; distribution: README, PyPI metadata, sdist and wheel, conda file, `guiqula
desktop`, icons), and the maintainer answered its report, decisions 25 to 45 (PLAN.md
section 7): a public GitHub repository without CI, pip as the only installer (no frozen
builds), Python 3.12 and 3.13, 0.0.1 as the first release. Nothing is uploaded or pushed
without the maintainer.

## Code map

The flow is Document -> plan -> engine -> worker -> Result -> plot; everything goes through
a `Session`.

- `core/`: `document.py` (pydantic models; ids unique across the document; a quantum
  system's Hamiltonian = construction, terms, mean-field block; a classical system's
  `model` = the model entry's set-up and its terms; `terms_of(system)`), `fields.py` and
  `locks.py` (what a teaching preset locks: an entry, `t1.m`, `s1/geometry`; the
  dispatcher refuses any mutation that changes a locked thing, comparing before and after),
  `expressions.py` (Fields: constant, expression, piecewise over regions, from_result,
  profile, interpolated, painted; the
  AST-whitelisted expression evaluator), `regions.py`, `nearest.py` (the stored point
  nearest to a position within a tolerance, by a cell hash: regions by positions, painted
  and from_result Fields and the canvas selection must use it, never an N x M scan), `results.py` (the `Result` dataclass
  that crosses the process boundary; a result drawn on the atoms carries its geometry in
  `structure`, and the ResultRefs its from_result Fields read in `reads`; `ResultRef`,
  what a from_result Field reads), `bonds.py` (a Field known on the sites only, painted,
  from_result or a region by positions, at the bond midpoints where pyqula evaluates the
  parameters declared `FieldParam(bond=True)`: the mean of the two ends, a region holding
  a bond when it holds both), `hashing.py`.
- `registry/`: one declaration per lattice, op, term, mean field and calculation
  (`lattices.py`, `geometry_ops.py`, `terms.py`, `meanfield.py`, `calculations.py`,
  `classical.py` for the classical models, terms and calculations, `python_nodes.py`,
  `sweeps.py`, a calculation that runs another one over parameter values; `kpaths.py`, the
  points of a k-path); an
  entry's `systems` names the system kinds it applies to. A
  declarative `Call("h.add_zeeman", "m")` drives both the engine and the script export; a
  custom entry gives `apply` and `script`. `pipeline.py` plans a system without pyqula: the
  Hilbert-space pre-scan, invalid entries, region references resolved to selections, and
  the stage and calculation keys (staleness); the mean field is the last stage; an entry
  that `runs_code` (the Python nodes, `python_nodes.py`) is invalid unless planned with
  `trusted=True` (the Session's flag, never the Document's; the UI plans only through
  `Session.plan_system`/`plan_calculation`/`calculation_key`). `plugins.py` loads the
  plugins right after the built-in entries, in the window and the workers alike: entry points
  of the group `guiqula.plugins` and the `*.py` of the user's plugins folder; a failing one is
  left out whole and listed (Help > Plugins); `EntrySpec.plugin` names it; the test suite
  sets `$GUIQULA_NO_PLUGINS`; `plugin_template/` is a plugin package with its test. `cost.py`
  estimates durations (the cost guard). Adding a term = one `entry(...)` call plus its case
  in `tests/engine/test_entries.py` (a completeness test fails otherwise; the case is also
  exported and run by `tests/engine/test_script_export.py`). A custom script names the
  pyqula modules it uses (`modules=`); a calculation's `plot` is a dict or a callable of the
  parameters (and the arrays); plot kinds are listed in `ui/plots.py`.
- `docs/`: the in-app help (13.13), without pyqula imports: `guide.py` (a Markdown guide in
  sections; an anchor is a heading's text, "Parent > Heading" when repeated; equations to
  mathtext images), `docstrings.py` (pyqula's docstrings read from its source with `ast`,
  following imports and `@get_docstring`), `entries.py` (an item's help: formula,
  parameters, the pyqula code with its values, docstrings, the guide sections it names
  with `guide=`, the reference section of each call), `user_guide.md` (guiqula's own
  guide: the program, never pyqula's physics; its shortcut table is checked against
  `ui/shortcuts.py`). A registry entry names its guide sections (`guide=`, "guiqula: X" for
  guiqula's guide) and, if custom, its pyqula calls (`pyqula=`); `tests/test_help.py`
  checks every anchor and `tests/engine/test_help_docstrings.py` every docstring.
- `commands/`: `Dispatcher` (mutations with snapshot undo, actions journaled only; each undo
  step named by `steps.py`, which a new mutation needs a text in, and `undo(steps)`);
  `mutations.py` lists every mutation. Command arguments are JSON.
- `engine/`: `build.py` executes a plan (per-stage cache handing out copies, bounded by
  memory too, skip on error, seeds; `meanfield=False` for the interactive builds, which
  defer the mean field, and `sparse_above` for them: sparse above pyqula's dense limit),
  `calculations.py` runs an adapter and returns a `Result`, `structure.py` gives the canvas
  its arrays (positions, lattice, sublattice, pyqula's first-neighbour bonds, and the
  Hamiltonian view: onsite, exchange, pairing, every hopping's amplitude and phase).
- `worker/`: `process.py` (the worker, imports the engine inside `main()` only; its
  `Console` is the Python console's interpreter), `client.py` (`JobManager`: interactive and
  batch workers, the console worker started at its first command, cancel, respawn,
  timeouts, `request_handler` answering a job's REQUEST), `protocol.py`.
- `session.py`: dispatcher + job manager + results + the latest build of each system
  (coalesced requests; a stuck build is killed when a newer one is asked) + `modified` +
  `trusted` (`always_trust`: the window's setting) + the console (`console(code)`) + a few
  earlier results per calculation (an undo brings the matching one back) + the plans and
  keys of the current Document object, reused until it, the results or trust change;
  actions `undo`,
  `redo`, `history` for drivers; with `autosave=True` (the window's) it
  autosaves from `poll()`. The object tests, `guiqula run`, `tools/drive.py`, the window
  and the remote API drive. `ACTIONS` names its dispatcher actions.
- `remote/` (the Claude add-on, PLAN.md 3.7): `api.py` (`RemoteAPI`: the methods a client
  calls over a Session, JSON in and out: status, document, commands, catalogue, do, run,
  wait, result, plot, screenshot, help, script, console, journal; a method that waits
  returns a `Pending`; without a window it asks for the builds itself;
  `WINDOW_ACTIONS` lists the window's actions, checked by a test), `server.py` (JSON-RPC
  2.0, one message per line, on 127.0.0.1, `hello` with the token first; polled from the
  host's loop, never a thread of its own, so the Session stays single-threaded),
  `connection.py` (connection files, mode 0600, in `$GUIQULA_DATA_DIR/remote`),
  `client.py` (`connect()`), `mcp.py` (`guiqula mcp`: the MCP protocol written by hand,
  the handshake of 2024-11-05 to 2025-11-25; attaches to the newest running server or runs
  a Session of its own; fd 1 points at stderr so nothing but protocol reaches stdout),
  `window.py` (the window's hooks: screenshots, widget names, its state).
- `io/`: project files (a `.guiqula` zip keeps the results too), presets
  (`src/guiqula/presets/*.json`, loadable by name, described by the Document's `notes`),
  script export (a sweep exports a loop), result files, `autosave.py` (autosave and
  recovery), `crashreport.py`, `bundle.py` (Export figure, data and script: one folder
  per result, the figure drawn by the window in the light theme), `settings.py` (the user's theme, recent files, always
  trust, remote control; `$GUIQULA_CONFIG_DIR`; only the interactive program's window, `use_settings=True`,
  reads or writes it).
- `desktop.py`: `guiqula desktop` (the menu entry, icon and `.guiqula` file type for the
  current user: freedesktop files on Linux, a Start menu shortcut and registry keys on
  Windows, `~/Applications/guiqula.app` on macOS; from a checkout it carries `src/`);
  `env.launcher()` is the command that starts guiqula again. `resources/`: the icon (SVG;
  PNG, ICO, ICNS made by `tools/make_icons.py`).
- `packaging/README.md`: what each distribution is (pip only: sdist and wheel, the conda
  file, `guiqula desktop`), what was verified, the release checklist (built and uploaded by
  hand; there is no CI).
- `ui/`: `mainwindow.py` (workspaces, palettes with search boxes from the registry, docks,
  bars, one result view per calculation, the cost guard, auto re-run; the window's own
  dispatcher actions `select`, `workspace`, `tool`, `select_sites`, `region_from_selection`,
  `remove_selected`, `canvas_view`, `preview`, `auto_rerun`, `projection`, `overlay`,
  `slider`, `set_slider`, `remove_slider`, `paint`, `theme`, `export_bundle`, `help`,
  `remote`; a new one joins `remote/api.py`'s `WINDOW_ACTIONS`; File > Allow remote
  control starts the server, polled from the window's timer),
  `help.py` (the Help dock: F1, a form's ?, the guides; Markdown in a QTextBrowser, whose
  `loadResource` serves the equations), `shortcuts.py` (the one
  table of keyboard shortcuts: menus, the canvas and outliner keys, the dialog; a test
  refuses ambiguous keys), `outliner.py`, `gallery.py`
  (presets), `sliders.py` (the Sliders dock), `kspace.py` (the Brillouin-zone canvas),
  `properties.py` + `forms.py` (forms from the parameter declarations; the `f(r)` Field
  editor), `formulas.py` (mathtext images; rich tooltips of the palettes), `structure.py`
  (canvas, its three views,
  selection tools, and the mplot3d drawing of geometries that are not flat), `plots.py`
  (`PlotView` per calculation, `plot_<id>`; lines, colored_scatter, heatmap,
  structure_scalar, structure_vector, scalar), `jobpanel.py`,
  `console.py` (the console dock), `bars.py` (recovery, error, cost and trust bars),
  `errors.py` (exception hook), `theme.py` (light and dark: the colour names are the active
  theme's, rebound by `apply`; every figure is drawn inside `theme.drawing(figure)`). The
  window saves its view state as the Document's `ui` block (not a
  Command, not an unsaved change) and restores it on open and recovery. The window
  polls the session from a `QTimer` and starts the workers after it is shown; a form or tree
  rebuilt from inside one of its own signals must be deleted later (PLAN.md phase 2 facts).

## Hard rules

- **A local checkout of upstream pyqula (https://github.com/joselado/pyqula) is read-only
  from this project.** Never edit it, never `pip install -e` it (that writes egg-info into
  it), never run anything with the cwd inside it (pyqula writes `.OUT` files to the cwd). The
  same applies to a checkout of quantum-lattice. Where they are on this machine is in
  `CLAUDE.local.md` (gitignored), if present.
- **The repository is public** (github.com/joselado/guiqula, no CI): nothing private goes in
  it. No paths of the maintainer's computer in tracked files (they belong in
  `CLAUDE.local.md`), no Claude session links in commit messages (a commit ends with the
  `Co-Authored-By` line only).
- `vendor/pyqula/` is a copy of upstream's working tree, and (decision 3) the copy that ships
  inside releases as `guiqula/_vendor/pyqula`, imported as top-level `pyqula` through a
  `sys.path` shim because pyqula imports itself absolutely. Never hand-edit it;
  refresh the whole copy with `tools/update_vendor.sh`, which also rewrites `vendor/VENDOR.md`
  (upstream URL and commit, uncommitted upstream files that were included, upstream's
  runtime dependencies to mirror in `pyproject.toml`) and then runs the help tests. Commit a
  refresh on its own; the one exception is the fix of registry `guide=` anchors that a
  renamed upstream guide section forces (decision 13.13), which may join it. `vendor/` holds
  the package and `vendor/pyqula_user_guide.md`, upstream's user guide (the in-app help), and
  nothing else of upstream (the maintainer's answer, 2026-09-27). For how to call something,
  check the guide first, then upstream's `examples/` (in the pyqula checkout, or on GitHub),
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
and the launcher `./guiqula` do it themselves (the launcher also through `PYTHONPATH`, for
what `env.launcher()` starts, and its `__main__` guard is what keeps the spawned workers
from running `main()` again). Keep this section in sync with what exists.

```bash
python -m pytest                       # everything (offscreen Qt, worker processes; 5-6 min)
python -m pytest -m "not slow"         # skip the wheel build
python -m pytest tests/core            # pure Python, under a second
python -m pytest tests/engine -k zeeman  # one area / one test
./guiqula [preset|file]                # the window, from the checkout (any subcommand below too)
PYTHONPATH=src python -m guiqula [preset|file]         # the window (--offscreen, --version)
PYTHONPATH=src python -m guiqula run honeycomb_zeeman_rashba --calc c1 --out out --script
PYTHONPATH=src python -m guiqula script honeycomb_zeeman_rashba --calc c1   # print the script
python tools/drive.py honeycomb_zeeman_rashba --run c1 --shot bands.png    # drive the window
python tools/drive.py preset --do '{"do": "add_term", "system": "s1", "kind": "haldane"}' \
    --run c1 --widget plot_c1 --shot plot.png      # also --commands FILE, --python CODE,
                                                   # --list-widgets, --no-warm (see --help)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "select_sites", "box": [0.9, -2, 2.1, 2]}' \
    --do '{"do": "remove_selected"}' --widget structureView --shot sculpted.png
python tools/drive.py --recover --shot recovered.png   # unsaved work of a killed session
                                                   # (--hold SECONDS keeps the window running)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "canvas_view", "name": "hamiltonian"}' \
    --widget structureView --shot hview.png        # the Hamiltonian view (13.8)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "preview", "entry": "t1", "param": "m"}' \
    --widget structureView --shot field.png        # a Field on the structure
python tools/drive.py honeycomb_hubbard --run c1 --widget plot_c1 --shot hubbard.png   # mean field
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "console", "code": "h.get_gap()"}'
                                                   # the console; its output is in the report
python tools/drive.py project.guiqula --trust ...   # run the Python nodes of a file (13.7)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "theme", "name": "dark"}' --shot dark.png
python tools/drive.py preset --do '{"do": "set_param", ...}' --do '{"do": "undo"}'
                                                   # undo, redo (steps), history
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "select", "entry": "t1"}' \
    --do '{"do": "help"}' --widget helpDock --shot help.png   # an entry's help (13.13)
python tools/drive.py honeycomb_zeeman_rashba --run c1 \
    --python "session.act('export_bundle', calculation='c1', path='out/c1_bands')"
                                                   # figure, data, script in one folder
                                                   # (--do runs before --run, --python after)
PYTHONPATH=src python -m guiqula --remote preset      # the window, remote control on (3.7)
PYTHONPATH=src python -m guiqula serve preset         # a session without a window, remotely driven
PYTHONPATH=src python -m guiqula mcp [--attach|--headless] [--document D]   # the MCP add-on
claude mcp add guiqula -e PYTHONPATH=$PWD/src -- python -m guiqula mcp  # register it (checkout)
<python with the mcp SDK> tools/mcp_check.py --python $(which python)  # the SDK's client vs mcp
PYTHONPATH=src python -m guiqula desktop [--remove]   # menu entry, icon, file type (this user)
python -m build && twine check --strict dist/*   # sdist and wheel (packaging/README.md)
python tools/make_icons.py             # the PNG, ICO and ICNS from resources/guiqula.svg
python tools/readme_images.py [name ...]   # the README's screenshots (docs/images), by drive.py
tools/update_vendor.sh /path/to/pyqula  # refresh vendor/ from upstream pyqula ($PYQULA_SRC)
```

`drive.py` prints a JSON report last (document outline, builds, jobs, result summaries,
canvas view, tab shown, open result views, selection, undo steps, log tail, screenshot
path); a `--do`
object names a mutation or an action with `"do"`, and the driver waits for the rebuild after
each one. Autosaves and crash reports go to the user data directory, or to
`$GUIQULA_DATA_DIR` (the test suite sets it); the settings file to the user config
directory, or `$GUIQULA_CONFIG_DIR` (set by the test suite too). Presets with locks are the gallery's
teaching group (`ssh_chain`, `graphene_basics`); the others are its examples. In Python,
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
