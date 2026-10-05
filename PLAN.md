# guiqula — design and development plan

guiqula is a graphical workbench for [pyqula](https://github.com/joselado/pyqula),
the Python tight-binding library. This document records the requirements, the
framework decision, the architecture, and the phased plan. It is the reference
for every later design discussion; update it when a decision changes.

Status: **all decisions in sections 12 and 13 made on 2026-09-26 (13.13, in-app
help from pyqula's documentation, decided after phase 1, its open design
points settled in phase 5 and recorded in section 11); the plan review of the
same day is in section 14, and its one item left open then is settled in
section 11.** Phases 0 to 3 were
done on 2026-09-26 and phase 4 on 2026-09-27 (section 7); the maintainer asked
for phase 5 without commenting on the phase-4 report, so its items stand as
built. Phase 5 (polish) was done on 2026-09-27; its report (design items 1
to 14, the first seven being the recommendations for the open points of the
in-app help, recorded in section 11, and decisions 15 to 24) was not commented on
(phase 6 was asked for), so its items stand as built. Phase 6 (distribution and the add-on) was done on 2026-09-27 in
three parts (remote control and the MCP add-on; plugins; distribution,
verified on Linux); the maintainer answered its report (decisions 25 to 45
in section 7) the same day: a public GitHub repository without CI, pip as
the only installer (the frozen builds dropped), Python 3.12 and 3.13, the
plugin recorded in the documents, and 0.0.1 as the first release, which
the maintainer uploads. After phase 7, the maintainer asked for the 3D
drawings (structures, magnetization) to be done optionally by pyvista,
turned and zoomed with the mouse as in a pyvista window; built on
2026-09-29 (section 7, after the phase-7 answers; decisions 63 to 70). The
maintainer then asked for the controls of Blender in the 3D scene and of
Inkscape on the flat drawings (section 7, after the look; decisions 80 to 87). Phase 8, the interface, was planned on 2026-10-03 (nine
packages, P1 to P9, and decisions 90 to 106, at the end of section 7; the
maintainer answered 93, and the others stand as recommended) and built on
2026-10-03 and 2026-10-04 on branch phase8, every package included; its
report closes section 7, with decisions 107 to 145, which the maintainer
answered on 2026-10-05 (all as recommended but 121, answered with its
alternative), and section 4 draws the window as built. Phase 8 was merged into
master and pushed on 2026-10-04.

## 1. Requirements (as stated by the maintainer)

1. One single program in which *everything* can be changed: geometry,
   Hamiltonian terms and calculations are freely composable. Much more freedom
   than quantum-lattice, which has one fixed form per "mode".
2. Three conceptual steps: **geometry** (choose and modify), **Hamiltonian
   terms** (choose and modify), **calculations** (bands, DOS, ...). It must be
   possible to go back and modify the geometry after the Hamiltonian is set up,
   and have the Hamiltonian follow.
3. Inspiration: Inkscape and Blender (one document, one canvas, tool panels,
   non-destructive editing).
4. Runs on Linux; Mac and Windows if possible. Installation must not be
   problematic on other Linux machines, Mac or Windows.
5. Save and load the configuration.
6. Robust to crashes.
7. Testable directly from Claude Code, without clicking by hand.
8. Easy to add further functionality.
9. Possibly, in the future, a Claude add-on that controls the program from
   inside.
10. Many plots, contained inside the program and interactive. matplotlib if
    fitting; alternatives welcome.
11. The upstream pyqula repository is read-only from this project. A local
    copy lives in `vendor/` (see `vendor/VENDOR.md`).
12. Any Hamiltonian parameter can be spatially modulated from the interface
    (stated 2026-09-26; design in section 3.8).

## 2. Framework decision

### Decision (2026-09-26): PySide6 (Qt 6) desktop application, one Python process for the UI, calculations in a worker process

The discriminating requirements are 7 (drive it without clicking), 6 (crash
robustness) and 4 (installation). What was verified on this machine
(2026-09-26):

- PySide6 6.11.1 is installed. A window builds under
  `QT_QPA_PLATFORM=offscreen`, a button can be clicked programmatically, and
  `widget.grab().save("x.png")` produces a screenshot that Claude can read.
  One gotcha: with the conda interpreter the platform plugin is only found if
  `QT_QPA_PLATFORM_PLUGIN_PATH` points at PySide6's own `Qt/plugins/platforms`
  directory. The launcher and the test harness set it.
- An interactive matplotlib canvas (`QtAgg`, with the navigation toolbar)
  embeds inside a PySide6 window and also renders offscreen.
- The vendored pyqula runs a honeycomb + exchange + Rashba band calculation
  from a scratch directory. First call took 12 s, dominated by numba
  compilation; pyqula also wrote `KPOINTS_BANDS.OUT` and `BANDLINES.OUT` to
  the cwd even with `write=False`, so calculations must always run in a
  scratch directory.

Why Qt over the alternatives:

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **PySide6** | Native docks/toolbars/splitters (Blender-style workbench is built in). One language. Mature offscreen testing (pytest-qt). matplotlib and pyqtgraph embed natively. Maintainer already knows it. LGPL, pip wheels for Linux/Mac/Windows. | Big dependency (the Essentials wheel is 80 MB on Linux; the full PySide6 adds a 175 MB Addons wheel that guiqula does not need, see section 6). Bundling into a single installer takes work. | **Recommended** |
| Web front end (browser + FastAPI/websocket backend, or NiceGUI/Panel) | Trivially cross-platform, remote use (HPC), modern look, Playwright for tests. | Two languages for a real workbench (dock layout, canvas picking, undo). Interactive plots must be rebuilt in JS or go through Plotly. Desktop packaging still needs pywebview/Electron. Roughly double the work for the same features. | Viable plan B if remote/HPC use becomes a goal |
| Dear PyGui | Fast, immediate mode, GPU plots. | Small ecosystem, no matplotlib embedding, weak accessibility/theming, harder offscreen testing. | No |
| Tkinter | Ships with Python. | Looks dated, no docking, matplotlib only via TkAgg, poor high-DPI. | No |
| Kivy / Flet / Toga | Mobile story. | Not desktop-workbench toolkits; immature widgets for dense forms. | No |

The architecture below keeps every requirement in a Qt-free core so a web
front end could be added later without touching the physics or the document
model. That is also what makes the Claude add-on (requirement 9) cheap.

### Plotting

- **matplotlib embedded in Qt** for every result plot. Zoom/pan toolbar, hover
  cursor readouts, click-to-select (used e.g. to pick a k-point or an atom),
  and publication export (PNG/PDF/SVG plus the raw data) all come for free.
  Every plot lives in a tab of the central viewport and can be detached into a
  window of its own.
- **pyqtgraph** (pip, pure Python, installed in phase 0) as the fast path for the
  structure canvas once systems have thousands of atoms, and for slider-driven
  live updates. Not needed for phase 1; the canvas starts on matplotlib too.
- **3D structures**: pyqtgraph.opengl first (light). pyvista/vtk are already
  installed here and can back an optional `[3d]` extra later; they are heavy
  and need a working OpenGL stack, so they stay optional. (Phase 4 part 1
  drew 3D with matplotlib's mplot3d instead, because Qt refuses OpenGL
  widgets offscreen; a decision for the maintainer, section 7. On
  2026-09-29 pyvista became the optional second 3D drawing, View > 3D
  drawing, the `[3d]` extra: it renders off-screen and the window paints
  the image, so it needs no OpenGL from Qt; section 7, decisions 63 to 70.)

## 3. Architecture: headless core, command API, Qt view

```
src/guiqula/
  __init__.py, vendoring.py, env.py, __main__.py
              Package entry: the pyqula sys.path shim (never imports pyqula),
              the Qt plugin path and NUMBA_CACHE_DIR fixes, the command line.
  core/       Document model (JSON-serializable). No Qt, no pyqula imports.
  registry/   Declarative catalogue: lattices, geometry ops, terms, calculations,
              operators. Each entry = parameter schema + applicability rules +
              a build function + docs/tooltip/formula. Plugins register here.
              registry/pipeline.py plans a system without pyqula (mode pre-scan,
              invalid entries, stage and calculation keys) for the engine and the UI.
  engine/     Turns a Document into pyqula objects. Content-hash cache so that
              editing one term rebuilds only from that point down.
  worker/     Runs engine jobs in a separate OS process (multiprocessing spawn),
              in a scratch cwd. Returns numpy arrays + metadata, never widgets.
  commands/   Every mutation of the Document is a named Command with undo.
              This is the single API used by the UI, the tests, the embedded
              console, the CLI driver and the future Claude add-on.
  session.py  Dispatcher + job manager + results: the one object the tests, the
              CLI, tools/drive.py, the UI and the remote API drive (phase 1).
  io/         Project save/load (.guiqula), autosave and crash recovery, crash
              reports, pyqula script export, result files.
  ui/         PySide6: main window, outliner, properties forms (auto-generated
              from schemas), viewport (structure canvas + plot tabs), console,
              job panel. Widgets carry stable objectNames for tests.
  remote/     Local JSON-RPC server over the command API + MCP wrapper
              (the Claude add-on). Phase 6.
tests/        core/ (pure), engine/ (against direct pyqula calls), ui/ (pytest-qt, offscreen)
tools/        update_vendor.sh, drive.py (headless driver), screenshot helpers
vendor/       read-only pyqula copy; shipped inside releases as src/guiqula/_vendor/pyqula (section 6)
```

### 3.1 The Document: a non-destructive pipeline

The Document is the Blender scene / Inkscape SVG of guiqula. It is a plain
data structure (pydantic models, already installed): a list of systems, each
with its ordered stacks, plus a list of calculations and their results:

```json
{
  "version": 1,
  "systems": [
    {
      "id": "s1", "name": "graphene flake", "kind": "quantum",
      "geometry": {
        "base": {"kind": "honeycomb_lattice", "params": {}},
        "ops": [
          {"id": "op1", "kind": "supercell", "enabled": true, "params": {"n": [3, 3, 1]}},
          {"id": "op2", "kind": "remove_atoms", "enabled": true,
           "params": {"positions": [[0.0, 0.577, 0.0]], "tol": 0.05}},
          {"id": "op3", "kind": "ribbon", "enabled": false, "params": {"n": 10}}
        ]
      },
      "regions": [
        {"id": "r1", "name": "left edge", "select": {"kind": "expression", "expr": "x < -2.0"}},
        {"id": "r2", "name": "picked", "select": {"kind": "positions", "positions": [[1.0, 0.0, 0.0]], "tol": 0.05}}
      ],
      "hamiltonian": {
        "construction": {"has_spin": true, "nambu": false, "tij": [1.0], "is_sparse": "auto"},
        "terms": [
          {"id": "t1", "kind": "zeeman", "enabled": true, "region": "r1",
           "params": {"m": [0.0, 0.0, "0.3*tanh(x/4)"]}},
          {"id": "t2", "kind": "rashba", "enabled": true, "params": {"c": 0.1}},
          {"id": "t3", "kind": "python", "enabled": true, "params": {"code": "h.add_kane_mele(0.05)"}}
        ],
        "meanfield": {"enabled": false, "kind": "interactions",
                      "params": {"U": 2.0, "V1": 0.0, "filling": 0.5, "mf": "random", "seed": 1}}
      }
    },
    {
      "id": "s2", "name": "triangular AFM", "kind": "classical_spin",
      "geometry": {"base": {"kind": "triangular_lattice", "params": {}},
                   "ops": [{"id": "op4", "kind": "supercell", "enabled": true, "params": {"n": [3, 3, 1]}}]},
      "regions": [],
      "model": {"terms": [{"id": "t4", "kind": "heisenberg", "enabled": true, "params": {"Jij": [1.0]}}]}
    }
  ],
  "calculations": [
    {"id": "c1", "system": "s1", "kind": "bands", "params": {"nk": 200, "operator": "Sz", "kpath": "auto"}},
    {"id": "c2", "system": "s2", "kind": "minimize_energy", "params": {"tries": 10}}
  ],
  "ui": {"workspace": "hamiltonian", "selected": "t1"}
}
```

(Since phase 2 `ui` holds the view state: the workspace, the selected
entry and calculation, the canvas tool, the viewport tab and the canvas
selection by position. The window keeps it as its own state, reached
through dispatcher actions, and hands the session a `view_state` callable
whose dict is written into `ui` of what is saved and autosaved; opening or
recovering a project restores it. A click is not a Command: the view state
never goes on the undo stack, never enters a key, and does not count as an
unsaved change. The maintainer asked for projects to remember it, answer 1
to the phase-2 report.)

A document holds a list of **systems** (decision 13.1). Each system has a
`kind`: `quantum` (geometry, regions, Hamiltonian construction, term stack,
mean field) or one of the classical kinds `classical_spin`, `lattice_gas`,
`ising` (geometry, regions, a classical model term stack). Calculations name
the system they act on; a transport or embedding calculation names two or
three. **Regions** (decision 13.2) are named site selections stored by
positions or by rule (expression, sublattice, layer, edge distance), and any
term may carry a `region` that restricts it to those sites.

Semantics, borrowed from Blender's modifier stack:

- **Order matters and is visible.** Terms are applied top to bottom, exactly as
  `h.add_*` calls would be in a script. The user can reorder, disable (eye
  icon) and duplicate entries.
- **Upstream edits re-apply downstream.** Changing the geometry invalidates
  the built Hamiltonian; the engine rebuilds it by replaying the same term
  stack. This is requirement 2. Results are marked *stale* but kept until
  re-run, never deleted silently.
- **Invalid entries are flagged and skipped, not deleted.** Haldane on a
  square lattice, sublattice imbalance on a lattice without sublattices: the
  entry turns red with the message pyqula's own guards produce
  (`check.require_spin`, `require_nambu`, `require_sublattice`), the engine
  skips it and continues with the rest of the stack (decision 14.3, as
  Blender does with a failing modifier), so the canvas and the downstream
  entries stay inspectable; a result built with a skipped entry says so.
  Applicability is *asked of pyqula* by building, not maintained as a shadow
  table (that table drifted in quantum-lattice's `latticeterms.py`).
- **pyqula upgrades the Hilbert space silently inside some terms** (verified
  2026-09-26, review item 1): `add_zeeman` and `add_magnetism` call
  `turn_spinful()` (`hamiltonians.py:642`), `add_antiferromagnetism` does the
  same, and `add_swave` calls `turn_nambu()` (`superconductivity.py:253`).
  So the construction block's `has_spin` and `nambu` are the *requested*
  mode, not the source of truth. The engine pre-scans the declared
  `requires` of the whole term stack and sets the mode once, before the first
  term, and the outliner shows the mode after each entry (spinless, spinful,
  Nambu) so an upgrade is never invisible. Nambu is the exception (changed
  2026-09-27, after the bug hunt): unless the construction asks for it, the
  Hamiltonian turns Nambu just before the first entry that needs it, as in
  pyqula in the stack's order, because some terms (the spin spiral, Kekule
  hopping) cannot take a Nambu Hamiltonian and were skipped in any stack
  with a pairing term; a term that fails below the pairing says so. The
  exported script does the same (`h.turn_nambu()` before that entry). A mid-stack `turn_spinful` on a
  sparse Hamiltonian goes dense, spinful, sparse again (`htk/mode.py:55`),
  which the cost guard (13.12) counts.
- **Every numeric parameter is a Field** (section 3.8): a constant, an
  expression of position, a piecewise value per region, a preset profile, an
  interpolated or painted map, or a result of another calculation. Most
  pyqula terms accept callables of `r` (the per-term list is in 3.8), so
  this maps directly. Fields stay data in
  the Document and are compiled inside the worker, which keeps the Document
  JSON-serializable and picklable across the process boundary.
- **Python nodes.** A geometry op or a term can be a snippet of Python that
  receives `g` or `h` (and `np`, `pyqula`) and mutates or returns it. This is
  the escape hatch that gives access to all of pyqula without waiting for a
  registry entry, and it is what "everything can be changed from a single
  program" ultimately rests on. A node can be promoted to a registry entry
  later by adding a schema.
- **Interactive edits are ops too.** Clicking atoms on the canvas to remove
  them creates/updates a `remove_atoms` op that stores *positions* (with a
  tolerance), not indices, so it survives changing the supercell size or the
  lattice parameter upstream as far as physically meaningful.

### 3.2 Registry: how functionality is added

One `entry(...)` call per entry, grouped by family in the modules of
`registry/` (built-ins) or in a plugin (the `plugins` folder of the user
config directory, plus a `guiqula.plugins` entry-point group for
pip-installed extensions; built in phase 6, part 2: `registry/plugins.py`,
`plugin_template/`). An entry declares:

```python
entry("term", "zeeman", "Zeeman / exchange field",
      VectorFieldParam("m", (0.0, 0.0, 0.1), "field (mx, my, mz)", "exchange field"),
      group="Magnetism", formula=r"\sum_i \vec m(\vec r_i)\cdot\vec\sigma_i",
      doc="Local exchange field acting on the spin; breaks time-reversal symmetry.",
      requires=("spin",), call=Call("h.add_zeeman", "m"),
      guide=("Including an external Zeeman field",))
```

From this single declaration the program derives the properties form, the
tooltip/formula, the validation, the outliner label, the script-export line,
the help, and the JSON schema for save/load. The `Call` drives both the
engine and the script export; an entry with no single pyqula call behind it
gives `apply` and `script` instead, and names the calls it makes with
`pyqula=` (the bands name `h.get_bands`), so that its help shows their
docstrings. `guide=` names the sections of pyqula's guide its help shows, or
of guiqula's own with "guiqula: " in front. An entry also declares the system
kinds it applies to (`quantum`, `classical_spin`, `lattice_gas`, `ising`), so
each kind gets its own palette from one registry. Calculations declare the
same way plus a `plot` kind (see 3.4). Adding a term or a calculation is one
`entry(...)` call and its case in `tests/engine/test_entries.py`; nothing
else changes.

Name lists come from pyqula itself, never hand-copied:
`operatorlist.get_operator_names()`, `meanfield.get_guess_names()`,
`sctk.pairing.get_pairing_modes()`, `kpointstk.labels.get_label_names()`,
`extract.get_extractable_names()` (all verified to exist). Lattice factories
are introspected from `pyqula.geometrytk.lattices` and `specialgeometry`.

### 3.3 Engine and worker

- `engine.build(document, system_id)` returns the built objects of one
  system (`g`, `h`, `h_mf` for a quantum system; `g` and the classical model
  for a classical one), with a cache keyed by the content hash of each prefix
  of that system's pipeline. Editing term 3 of 5 reuses `g` and the
  Hamiltonian after term 2. pyqula's `add_*` mutate in place, so the cache
  hands out `h.copy()` (`hamiltonians.py:825`) and never its own object
  (review item 5). Mean-field results are cached the same way, and their
  converged Hamiltonian can be pickled into the project file.
- **Every stochastic entry carries an explicit `seed`** (review item 2):
  Anderson and phase disorder, random mean-field guesses, multistart
  minimisation, annealing. pyqula draws from numpy's global generator without
  seeding (`disorder.py:8`, `disorder.py:25`), so the engine seeds it right
  before applying that entry; otherwise the content hash, the engine tests
  and the exported script would not reproduce. pyqula's own process pool
  seeds its tasks through `SeedSequence` (`paralleltk/multiprocess.py:54`),
  so a serial and a parallel run of the same document can differ; the result
  metadata records the core count.
- All building and all calculations run in a **worker process**, not a
  QThread. Reasons: pyqula's own notes record a fatal interpreter abort from
  numba's non-thread-safe work queue when entered from two threads; a process
  gives real cancellation (kill and respawn) and crash isolation (a segfault
  in a solver cannot take the window down); and pyqula's cwd-relative file
  output needs its own scratch directory per job. The worker warms numba on
  startup so the first click is not the 12 s compile. `NUMBA_CACHE_DIR` is
  pointed at the user cache directory to keep later startups fast.
- A **Job** carries a Document snapshot and a calculation id; the worker
  returns numpy arrays plus metadata. pyqula's return conventions are mixed
  (review item 3): `get_bands` returns arrays, the Green-function DOS writes
  `DOS.OUT` and returns nothing (`dos.py:223`), `ldos` writes `LDOS.OUT`,
  `get_bands_map` returns a matplotlib figure. So every calculation entry has
  an adapter that returns arrays, parsing the `.OUT` files from the job's
  scratch directory where needed, and never forwards a figure across the
  process boundary. Plots are drawn in the UI process from
  arrays. Only one job runs per worker; a small pool (default 1, configurable)
  allows parameter sweeps to run in parallel, respecting pyqula's own
  `parallel.set_cores`.
- Windows uses `spawn`, so the worker entry point imports cleanly and nothing
  crossing the boundary is a lambda; the string-expression rule above exists
  for this reason.

### 3.4 Results and plots

A Result = calculation id + parameter snapshot + upstream hash + arrays +
plot spec. Plot specs are a small closed set, each implemented once in
matplotlib with interactivity wired (hover readout, click callbacks, export):

| kind | used by |
|---|---|
| `lines` | DOS, bands (no operator), sweeps, dI/dV |
| `colored_scatter` | bands with an operator expectation value, Fermi surface with colour |
| `heatmap` | k-resolved DOS, surface spectral function, Berry-curvature maps, QPI, Hofstadter |
| `structure_scalar` | LDOS, density, onsite profile drawn on the atoms |
| `structure_vector` | magnetization arrows, currents |
| `scalar` / `table` | Chern, Z2, gap, total energy (shown in the result badge and a results table) |

A calculation entry only names its plot kind and how to map its arrays. This
is what keeps "add a calculation" to one file.

### 3.5 Commands, undo, save, recovery

- Every mutation is a Command (`add_term`, `set_param`, `move_op`, `toggle`,
  `run_calculation`, ...), applied through one dispatcher with undo/redo
  (Ctrl+Z / Ctrl+Shift+Z), a journal, and change notifications the UI binds
  to.
- **Save/load**: a `.guiqula` file = zip with `document.json` (versioned
  schema, migrated on load) and optionally cached results and mean-field
  Hamiltonians. The loader also accepts a bare `document.json`, and the
  presets shipped in the repository are stored as bare JSON so they diff in
  git (14.4). Recent-files list. Also **script export**: a runnable pyqula
  `.py` reproducing the document, the successor of quantum-lattice's "pyqula
  code" tab; it is generated from the same registry entries that build the
  Hamiltonian so it cannot drift.
- **Crash robustness**: (a) worker isolation as above; (b) the Document is
  autosaved to the per-user data directory (via `platformdirs`) after every
  command, debounced to a short interval so a slider drag is one write and
  not hundreds (14.4), and on start the program offers to recover; (c) a
  global exception hook turns any unexpected error in the UI into a log entry
  and a non-modal error bar, never
  an abort; (d) jobs have a timeout and a Cancel button; (e) the worker is
  respawned automatically if it dies, with the error shown next to the
  calculation that killed it; one that dies before it is ready (pyqula
  does not import) is started again a few times after a pause, then its
  jobs fail with the reason it gave (fixes of 2026-09-27).

### 3.6 Testability from Claude Code

- `tests/core`: Document, commands, undo, schema migration. Pure Python, fast.
- `tests/engine`: for each registry entry, build through the engine and
  compare against a direct pyqula call (same arrays), so the GUI can never
  compute something different from the script it exports.
- `tests/ui`: pytest-qt under offscreen Qt. Fixtures build the main window,
  drive it through commands *and* through widgets found by objectName, and
  save screenshots to a directory Claude reads with the Read tool.
- `tools/drive.py`: starts the application offscreen, executes a JSON list of
  commands (or a Python snippet) against it, saves screenshots of the whole
  window or a named widget, prints the Document and the log. This is how
  Claude "clicks" during development, and it uses the very same command API
  the Claude add-on will expose.
- Install needed: `pip install pytest-qt pyqtgraph` (pytest 7.4 is present).

### 3.7 The Claude add-on (later)

Because the UI is a client of the command API, exposing that API on a
localhost socket (JSON-RPC, token-protected) makes the running program
controllable from outside. A tiny MCP server (`guiqula-mcp`, stdio) proxies
to it, so Claude Code can list commands, read the Document, add terms, run
calculations, fetch result arrays and screenshots, and explain what it sees.
Inside the program, an "Ask Claude" panel can send the same context to the
Claude API. Nothing in phases 1 to 5 needs to change for this; it is the
payoff of the headless core.
Built in phase 6, part 1 (section 7): the server is `remote/server.py`
(off unless File > Allow remote control, `guiqula --remote` or `guiqula
serve`), the MCP server is `guiqula mcp` (written without the MCP SDK),
and the "Ask Claude" panel is left for the maintainer to decide
(decision 32).

### 3.8 Spatial modulation of any parameter (requirement 12)

Every parameter of every term is typed as a **Field**, never as a bare float.
A Field is a constant or one of these, all JSON-serializable and compiled to
a callable of position inside the worker:

| Field kind | what the user gives | pyqula side |
|---|---|---|
| `constant` | a number | the number |
| `expression` | `0.3*tanh(x/4)`, with `x, y, z`, `r` (distance from the origin), `pi` and a whitelist of numpy functions (also as `np.<name>`) in scope | `lambda r: ...` |
| `piecewise` | one value per region (13.2) plus a default; regions may overlap with a stated precedence | callable testing region membership by position |
| `profile` | a named preset with parameters: pyqula's `potentials` (commensurate potential, impurity, edge potential, stacking potential, skyrmion and vortex harmonics, Fibonacci and Thue-Morse chains, Aubry-André), plus radial/linear/step/Gaussian/random | the `potentials` function or a small built-in |
| `interpolated` | control points placed on the canvas, or an array/file on a grid | `potentials.interpolate2d` / `array2potential` |
| `painted` | a weight-paint tool on the structure canvas (brush radius, strength, smooth), stored per site by position | array-backed callable |
| `from_result` | a result of another calculation or system, e.g. a classical texture as an exchange field, a converged mean-field onsite profile, an LDOS map used as a potential | array-backed callable with a stale link |

Vector parameters (exchange field, d-vector, DM vector) take one Field per
component or a single vector-valued expression. **Bond parameters** (hopping
amplitudes and their phases, pairing amplitudes, DM couplings, interlayer
hoppings) take a Field of the bond midpoint or a two-point expression
`f(r1, r2)`, which is how pyqula's `tij` callables and `add_strain` work.
A Field can be scaled and summed (`0.5*A + B`) so modulations compose.

Everything that is a number in a term form has an `f(r)` button next to it
that switches the widget to the Field editor; the structure canvas previews
the Field as a colour map (scalar) or arrows (vector) before anything runs,
and 13.8's Hamiltonian view shows the resulting onsite energies and hoppings
afterwards. Python nodes see the same Fields as ready callables. Script
export writes an expression as a lambda, a profile as its `potentials` call,
and array-backed kinds as a `numpy` literal or a sidecar `.npy` next to the
script.

**Which pyqula calls take a callable of position** (verified 2026-09-26,
review item 4): `add_zeeman`/`add_magnetism`/`add_exchange`,
`add_antiferromagnetism`, `add_sublattice_imbalance`, `add_rashba`,
`add_haldane`, `add_kane_mele`, `add_kekule`, `add_onsite`, and `add_peierls`
as a two-point function; phase 3 added `add_swave`, the U of
`get_mean_field_hamiltonian` and its filling (as one value per site), and
found that `add_antiferromagnetism` takes a function returning a vector. Not `add_valley_exchange` and not
`add_crystal_field`. A registry entry declares whether its pyqula call takes
a Field natively; otherwise it declares a fallback designed per term (one
candidate: apply the term with a unit amplitude and scale the resulting
onsite or hopping entries per site or per bond through `get_multihopping()`,
which still has to be checked for bond terms that mix with existing
hoppings), or the parameter is constant-only and the form says so. `rashba.py:97` calls a position-dependent strength once
per bond from Python, so a compiled Field must be cheap per call (a compiled
numpy expression or an array lookup, never a re-parse).

Expressions are evaluated by the AST-whitelisted evaluator of decision
14.8 (`core/expressions.py`). In an expression `r` is the distance from
the origin, not the position vector: subscripts are not allowed, so the
coordinates are `x, y, z` (phase 1 choice, 2026-09-26). Script export
writes `x` as `r[0]` and `r` as `np.linalg.norm(r)` inside `lambda r:`.
One arithmetic holds in the engine, the canvas previews and the exported
script alike (a review decision of 2026-09-28, which the maintainer
confirmed the same day over numpy's booleans and over refusing arithmetic
on a comparison): a comparison is 1.0 where it holds and 0.0 elsewhere
wherever it appears, so `(x > 0) + (y > 0)` is 2 where both hold and
`-(x > 0)` works; `&`, `|`, `^` and `~` are logical on such truth values;
a value that is not a real
number is refused when typed if the expression does not depend on the
position (`(-8)**(1/3)`), and is NaN at the sites where it is not real
otherwise (`sqrt(x)` where x < 0, `(-8)**(x/3)`), which the preview greys
out and counts; a function
takes exactly its own arguments (a ufunc would read one more as the array
to write into). The lattice constants are not in scope yet. The engine
and the exporter accept `constant` and `expression` from phase 1; the UI
editor for them is phase 3.

Phase 3 delivers `constant`, `expression` and `piecewise`; phase 4 adds
`profile`, `interpolated`, `painted` and `from_result`.

A `piecewise` Field (phase 3) is `{"kind": "piecewise", "default": F,
"pieces": [{"region": "r1", "value": F}, ...]}` with each F a constant or
an expression (no nesting). Where regions overlap, the later piece wins,
as a later term does in the stack. It names regions by id, but ids never
enter keys (14.9): the planner resolves them to the regions' selections
and hashes those, so editing a region's selection makes the results
stale and renaming or duplicating it does not. A missing region is
refused by the command (the Document check), a broken one flags the entry;
`remove` refuses a region a piecewise Field uses, and duplicating a system
remaps the ids. Script export writes nested conditional expressions over
the regions' indicators.

**Fields known on the sites only, at the bonds** (2026-09-28, a review
finding). pyqula evaluates the Field of a bond term (Rashba, Haldane,
Kane-Mele and their variants, Kekule, the pairing's amplitude and
d-vector, the hopping modulation) at the midpoint of each bond. A painted
or from_result Field, and a region by positions (a term's region, or a
piece of a piecewise Field), are known on the sites only and found
nothing there: a term restricted to a region made from a canvas selection,
or given a painted Field, did nothing while its report said ok. Those
parameters declare `FieldParam(bond=True)`, and the engine and the
exported script hand pyqula `core/bonds.bond_field`, which takes a bond's
value from its two ends, found on the built geometry (the cell's sites and
their images in the cells around, so a bond crossing the cell's edge has
its ends too): a painted or from_result value is the **mean** of the
ends', and a region holds a bond when it holds **both** ends (a term
restricted to a region acts on the bonds between its sites). At a site
(an onsite element of the hopping modulation or of an s-wave pairing) the
value is the site's. Limits, design items for the maintainer: where bonds
share a midpoint pyqula gives them one value, and the shortest pairs
through it decide (the two diagonals of a square plaquette take its four
corners; a long bond whose midpoint is a site takes that site's value); a
bond longer than 6 (in pyqula's unit, the first-neighbour distance) takes
the Field at its midpoint as before. The canvas preview of such a Field
still shows its values at the sites (phase 2, left for later).

## 4. The user interface

One window, one document, three workspaces switched by tabs in the header
(Blender-style), sharing the same outliner, viewport and properties panel.
The window as phase 8 built it (2026-10-04), at 1200x800 on
`honeycomb_zeeman_rashba` with c1 run and then made stale by a change of
t1 (`python tools/drive.py honeycomb_zeeman_rashba --run c1 --python
"session.do('set_param', entry='t1', name='m', value=[0, 0, 0.3])"`; the
shot is `ui_dump/phase8/final/zr_c1_stale_1200x800_light.png`, not
tracked):

```
+-------------------------------------------------------------------------------------------------+
| File  Edit  View  Run  Help                                                                     |
| [Geometry][Hamiltonian][Calculate] | ⊞ New system v  + Add v  ▷ Run c1 · bands |v  ■  ⟲         |
+-------------------------------+----------------------------------------+------------------------+
| Outliner                   x  | Structure | k-space | c1 bands ↻  x    | Properties           x |
| Entry                 Status  | ⤢ ✥ ⊕ | ↖ | ≡v ⇥ ▦ ↗                 ▣ | Band structure       ? |
| v ⬡ s1  graphene with exch…   | ↻ stale: the model cha… [▷ Run again]  | c1 · Spectral          |
|     2D · 8 sites · spinful    |         c1 · bands · spinful           | Bands along a path     |
|   v Geometry               +  |    3 +--------------------+  sz        | through the zone...    |
|       ⁞ Honeycomb lattice     |      | \/  \/  \/  \/  \/ |  [#]       | system     s1          |
|     [x] ⚒ op1 Supercell · n … |    0 | /\  /\  /\  /\  /\ |  [#]       | k-points   [100    ]   |
|       Regions              +  |      | \/  \/  \/  \/  \/ |  [#]       | operator   [sz    v]   |
|   v Hamiltonian            +  |   -3 +--------------------+            | k-path     [default]   |
|     [x] Σ t1 Zeeman…  spinful |      Γ      K'   M   K       Γ         | result: stale          |
|     [x] Σ t2 Rashba…  spinful |                  k                     |                        |
|     [ ] ∞ Mean field      off |                                        | estimate: under a      |
|   v Calculations           +  |                                        | second  [▷ Run again]  |
|       ⌇ c1 Band structure   ↻ |                                        | ---------------------- |
|       ⌇ c2 Density of states  |                                        | Jobs                 x |
|                               | 0.06 s                                 | j2  run c1  done  100% |
|                               |                                        | Help | Sliders | Jobs  |
+-------------------------------+----------------------------------------+------------------------+
| s1 · 2D · 8 sites · spinful · dimension 16 · c1: under a second      j2 c1 done   [Log]         |
+-------------------------------------------------------------------------------------------------+
```

The drawing writes an icon as a sign: on the first row ⊞ new, + add, ▷
run, ■ cancel (the one filled icon) and ⟲ follow; on the bar of a result ⤢
fit, ✥ pan, ⊕ zoom, ↖ pick, ≡ overlay, ⇥ export, ▦ save data, ↗ detach and
▣ save image; in the outliner ⬡ a system, ⁞ its lattice, ⚒ an op, Σ a
term, ∞ the mean field and ⌇ a calculation, and ↻ the stale mark, which the
tab writes as that very sign. The icons are Tabler Icons drawn in the
theme's text colour, and every control that shows only its icon is named
by its tooltip, while New system, Add and Run keep their text beside it. A
calculation's estimate and Run sit at the foot of Properties, under the
scrolled form, so that a long form keeps them in sight.

When the document has no system the centre shows the start page in the
viewport's place (`ui/start.py`): a filter box, then the lattices (the
classical systems last) and the examples as cards with pictures, and the
recent files, each band folded to its first row (three for the files) until
Show all, and a line saying what comes next, with a link to the guide.

- **Outliner** (left): the whole pipeline as one tree, with one top-level
  node per system (the mockup shows a document with a single system; a
  classical system shows a *Model* stack in place of *Hamiltonian*, and the
  middle workspace tab reads *Model* while it is selected). Each section row
  has a "+" that opens the Add menu of its family for its system. A row's
  label says what it is, after an icon of its kind, and its Status column
  in what state, with one set of marks shared by the result tabs and the
  status row of a plot (`ui/marks.py`), written ✓ current, ↻ stale, the
  percentage while running, ✗ failed or invalid, ○ disabled and locked, and
  drawn as icons in the tree and the status row (a check mark, a circular
  arrow, an hourglass, a cross or a warning triangle in the error colour
  with the message on hover, a crossed-out circle, a padlock); the system's
  row reads its summary (2D · 8 sites · spinful) and the mean field its
  interactions. Drag to reorder,
  right-click to enable, run, rename, lock, duplicate, move or delete.
  Selecting an item shows it in Properties, brings its workspace forward,
  and marks what it affects on the canvas (e.g. the atoms a removal op
  deletes, the bonds a hopping term touches).
- **Workspace tabs** follow the selection (decision 93) and change what Add
  lists and what the Structure tab draws (the sites and bonds, or the
  Hamiltonian view), not the data. Entries are added from the "+" of their
  outliner section or from Add, one menu per family with a search line
  (Blender's Add menu, Inkscape's search): the lattices with the classical
  systems last (New system), the geometry ops, the terms grouped by physics
  (hopping, onsite, magnetism, spin-orbit, superconductivity, fields,
  disorder) with the mean field last, the calculations by group. **Run**
  names the calculation it acts on (selected in the outliner, else the tab
  shown, else the first); its arrow lists the others and every stale
  result, and Cancel and Follow (the automatic re-run of cheap results) sit
  beside it.
- **Viewport** (centre): a Structure tab always present (2D canvas with
  pan/zoom, atom picking, colour by sublattice/onsite/magnetization/LDOS,
  unit cell and neighbour cells, 3D view for 3D lattices), a k-space tab
  for a system with a periodic direction, plus one closable tab per result.
  A tab can be detached into a window of its own to compare plots side by
  side. Each drawing has a bar of its own (Fit, Pan, Zoom, the tools of that
  drawing, Save image) over a hidden matplotlib toolbar, wrapping onto
  further lines on a narrow window; a result that is not current has a
  status row above its plot (stale with Run again, running with its
  progress and Cancel, failed with the message).
- **Properties** (right): the form for the selected entry, generated from
  its schema, in the words of the physics. The button of each number shows
  the kind of its Field (`f(r)` for a plain number) and its menu changes the
  kind; the menu of a parameter's name locks it, attaches a slider, adds a
  sweep or previews the Field on the canvas. Live preview: changing a
  geometry or term parameter updates the structure canvas immediately
  (cheap) and marks results stale; results re-run on demand (Run button,
  F5, or the form's own Run) or on an opt-in "auto re-run" for cheap
  calculations. Below Properties, Help, Sliders and Jobs are tabbed
  (decision 95).
- **Log / console** (bottom): job output, errors with tracebacks folded, and a
  Python console (Blender's console), hidden until the Log toggle of the
  status bar shows them (decision 96), the status bar showing the last
  message meanwhile. The console is a *remote* REPL (decision 14.1):
  the code runs in the worker process, where `g`, `h`, `np` and `pyqula`
  live, and its text output (and arrays on request) streams back, so pyqula
  stays out of the UI process (13.15) and a crash in the console cannot take
  the window down. `doc` and the commands are available in the console too;
  those go through the same dispatcher, so they are undoable and journaled.
- **Presets**: quantum-lattice's seventeen modes become a gallery of presets
  (documents) so the old workflows are one click away, while remaining fully
  editable; they are cards on the start page and in File > Presets gallery.
  Tooltips are the registry's one-line docs and formula images;
  the longer help is pyqula's own documentation (13.13), in the Help panel
  below Properties (F1 shows the help of the selected entry).

## 5. What the user can change (initial registry scope)

- **Geometry bases** (from `geometrytk/lattices.py` and `specialgeometry.py`):
  chain, square, honeycomb (and armchair/zigzag/C6/square-cell variants),
  triangular, kagome, Lieb, cubic, diamond, pyrochlore, hyperhoneycomb,
  ribbons of each, twisted multilayers, mismatched lattices; read from
  file (xyz/POSCAR/pyqula geometry).
- **Geometry ops** (from `sculpt`, `supercell`, `ribbon`, `films`,
  `specialgeometry`, `Geometry` methods): supercell (matrix), ribbon
  (direction, width), film/slab, island (polygon, radius, rotation), remove
  atoms (picked or by expression), intersect with shape, rotate, shift,
  center, strain positions, stack/multilayer, twist, add geometry (sum),
  remove dangling atoms, python.
- **Hamiltonian construction**: spinless/spinful/Nambu, neighbour hoppings
  list or distance function, sparse/dense, multicell cutoff, non-Hermitian.
- **Terms** (`Hamiltonian.add_*`): onsite/Fermi level, hopping matrix and
  strained hopping, Zeeman/exchange, antiferromagnetism, sublattice
  imbalance, Rashba, Kane-Mele, anti Kane-Mele, Haldane, modified/anti
  Haldane, Kekulé, valley exchange, crystal field, Peierls and in-plane
  orbital fields, spin spiral, pairing (every mode from
  `get_pairing_modes()`), Anderson and phase disorder, interlayer/electric
  field, python.
- **Mean field**: U, V1, V2, J1..J3, filling or Fermi energy, initial guess
  from `get_guess_names()`, solver, mixing, max iterations, temperature.
  (Phase 3 built all of it: the filling is a Field, a function of
  position fixing every site's occupation; the solver is a choice of
  engine, pyqula's numpy engine with linear mixing or its jax engine with
  the solvers pyqula lists.)
- **Classical systems** (decision 13.5), built on `classicalspin.SpinModel`,
  `latticegas.LatticeGas` and `latticeising.LatticeIsing`, which take a
  `Geometry` and are otherwise independent of the quantum Hamiltonian. They
  share the geometry step, the regions and the canvas, and get their own
  palettes:
  - classical spin terms: Heisenberg shells (`Jij`, XXZ via `Jm`), tensor
    couplings from `generating_functions` (dipolar, RKKY on a TI surface,
    Ising ZZ, anisotropic XYZ, Dzyaloshinskii-Moriya), Zeeman field, spiral
    wavevector through `add_tensor_2d`, python;
  - lattice-gas terms: filling, repulsion shells `Jij`, chemical-potential
    profile (scalar or expression), python;
  - Ising terms: coupling shells `Jij`, field profile, fixed magnetization,
    python;
  - classical calculations: multistart energy minimisation, simulated
    annealing with a temperature schedule (progress through `checkpoint_at`),
    magnetization texture as arrows on the structure, local energy and local
    field maps, correlator, structure factor, specific heat and
    susceptibility against temperature, energy against temperature.
  - bridge to quantum systems: a converged classical texture can feed an
    exchange-field term of a quantum system in the same document (pyqula's
    `modulated_ladder` example does exactly this), which is one reason
    documents hold several systems.
- **Calculations** (first wave = what quantum-lattice covers, then grow):
  bands (with operator colouring and k-path editor), DOS (ED/KPM/Green),
  LDOS map, k-resolved DOS and surface spectral functions, Fermi surface,
  QPI, gap, magnetization/density profiles, Berry curvature (path and map),
  Chern/spin-Chern/Z2/winding, real-space Chern density, entanglement
  spectrum, optical conductivity, RPA susceptibility and magnon bands,
  transport through junctions, parameter sweeps of any parameter in the
  Document (this falls out of the Document being data).

## 6. Installation and distribution

- Python package `guiqula` (`pyproject.toml`, `src/` layout, console script
  `guiqula`). Runtime dependencies: `PySide6-Essentials` (80 MB wheel on
  Linux; the full `PySide6` adds a 175 MB Addons wheel that is not needed,
  since pyqtgraph's OpenGL view uses QtOpenGLWidgets, which is in Essentials;
  14.4), matplotlib, numpy, scipy, numba, pydantic, platformdirs, plus
  pyqula's own (`multiprocess`, `dill`, `threadpoolctl`, `jax`).
  All have wheels for Linux, macOS (Intel and Apple Silicon) and Windows, so
  `pip install guiqula` or `pipx install guiqula` is the whole install. A
  `conda` environment file is provided for people who prefer it.
- pyqula dependency (decision 3): **vendored**, as in quantum-lattice. The
  copy in `vendor/pyqula` is packaged as `guiqula/_vendor/pyqula`, and
  `guiqula` inserts `_vendor` at the front of `sys.path` before any pyqula
  import, in the UI process and in the worker entry point alike. It must stay
  importable as top-level `pyqula`, because pyqula imports itself absolutely
  in 64 places (`from pyqula import ...`). This shadows a pip-installed pyqula
  only inside guiqula's process. pyqula's runtime dependencies (numpy, scipy,
  matplotlib, numba, multiprocess, dill, threadpoolctl, jax) are mirrored in
  guiqula's `pyproject.toml`; `tools/update_vendor.sh` copies upstream's list
  into `vendor/VENDOR.md` so drift is visible at every refresh. A
  `GUIQULA_PYQULA_PATH` environment variable overrides the vendored copy for
  development against an upstream checkout.
- The launcher fixes the two known environment problems itself: the Qt
  platform-plugin path under conda, and `NUMBA_CACHE_DIR`.
- Desktop integration: `.desktop` file on Linux, a `.bat`/Start-menu entry on
  Windows, an app bundle on macOS. Single-file installers (PyInstaller or
  Briefcase) are a phase-6 item; numba and jax make bundles large but they do
  work. (Built in phase 6, part 3: `guiqula desktop`; a PyInstaller folder of
  900 MB on Linux, an Inno Setup installer for Windows and a disk image for
  macOS through a release workflow. The maintainer's answers to the phase-6
  report dropped the frozen builds and the workflows: pip is the only
  installer, with `guiqula desktop`; `packaging/README.md`.)
- Optional extras: `[3d]` (pyvista, the 3D drawing of View > 3D drawing,
  2026-09-29), `[fast]` (pyqtgraph).
  (A `[claude]` extra for the MCP server was planned; the server needs no
  dependency, decision 27.)
- Look and feel: plain Qt Widgets with the Fusion style and a light/dark
  palette (QSS), no `qfluentwidgets` dependency (section 13, item 6).

## 7. Phases

Each phase ends with tests that run headlessly and, where there is UI, with
screenshots Claude can inspect. No phase starts a new layer before the
previous one has tests.

**Phase 0 — bootstrap (short). Done 2026-09-26.** `pyproject.toml`, `src/guiqula` skeleton with
the `_vendor` path shim, `vendor/` wiring (done), `tools/update_vendor.sh`
(done), `git init` + license (done), test harness (`conftest.py` sets offscreen
Qt and plugin path, screenshot fixture, startup-time check), `tools/drive.py`
stub. Install `pytest-qt` and `pyqtgraph` (`platformdirs` 3.10 and `pydantic`
2.8 are already present).
What was built: `pyproject.toml` plus a small `setup.py` that maps
`vendor/pyqula` to `guiqula._vendor.pyqula` in the wheel (a test builds the
wheel and imports pyqula from it); `guiqula.vendoring` (lookup order
`$GUIQULA_PYQULA_PATH`, shipped `_vendor`, checkout `vendor/`; never imports
pyqula; refuses a different pyqula imported first; no bytecode writes into an
override tree); `guiqula.env` (Qt plugin path found without importing Qt,
`NUMBA_CACHE_DIR` in the user cache, because numba otherwise writes its cache
next to pyqula's sources); the empty layer packages; a placeholder main window;
`tools/drive.py` (window and widget screenshots, widget tree, Python snippets;
documents and `--run` wait for phase 1). Tests: an AST check of the layering
rules (section 10), the shim, the packaging, the startup budget, the driver, a
pyqula smoke build. Requires Python 3.11 or newer (jax 0.8.1).

**Phase 1 — headless vertical slice, plus a thin UI.** Document + commands +
registry with ~5 lattices, 3 geometry ops, 5 terms, 2 calculations (bands,
DOS); engine with caching; worker process; script export; and a minimal
window with a job panel (run, progress, cancel, worker respawn) and one plot
tab, so the worker ↔ Qt event-loop integration is exercised before the real
UI shell (decision 14.2). Acceptance: a test builds honeycomb → supercell →
Zeeman + Rashba → bands entirely through the command API, in the worker, and
the arrays equal a direct pyqula script; the exported script runs and
reproduces them; undo restores the previous Document; offscreen, cancelling a
running job leaves the window usable and the worker respawns.
**Done 2026-09-26**, acceptance tests in `tests/worker/test_session.py` and
`tests/ui/test_window_session.py`. Built: 6 lattices (chain, square,
honeycomb, triangular, kagome, Lieb), 3 ops (supercell, ribbon, remove atoms
by position), 6 terms (onsite, sublattice imbalance, Zeeman, Rashba, Haldane,
Anderson disorder with seed), bands (with operator) and DOS (ED, Green).
Fields `constant` and `expression` (engine and export; the editor is phase 3),
regions by expression or positions restricting any term whose pyqula call
takes a function of position. Beyond the plan: `registry/pipeline.py` (the
pyqula-free planning half of the engine: mode pre-scan, invalid entries,
keys, staleness), `session.py` (the one object every client drives), `guiqula
run` and `guiqula script` on the command line, presets as package data loaded
by name, a read-only document tree in the window fed by the interactive
worker's builds. Facts learned: `add_rashba` also turns a Hamiltonian
spinful; `add_haldane` on a square lattice does not raise; pyqula passes
callbacks (progress) into its own pool processes, so the worker's pipe only
accepts messages from the worker process itself; KPM DOS draws random
vectors, so it waits for a seed parameter; `get_hamiltonian(tij=[1.0])` takes
the multicell path, so the engine passes `tij` only when it differs from
pyqula's default.

**Phase 2 — UI shell and geometry workspace.** Main window with outliner,
viewport, properties, log; plain Qt theme; structure canvas with pan/zoom,
picking, lasso and region creation; lattice picker;
supercell/ribbon/island/remove-atoms ops; autosave, recovery and crash reports.
Acceptance: `tools/drive.py` loads a preset, removes atoms by command, and the
screenshot shows the sculpted geometry; killing the process and restarting
recovers the document.
Carried over from phase 1: coalesce the interactive worker's build requests
per system (every document event queues one build now, which a slider drag
would pile up); show the Hilbert-space mode after each entry in the outliner
(the build reports carry it, the phase-1 tree only shows the system's mode).
**Done 2026-09-26**, acceptance tests `test_sculpt_by_command_and_see_it` and
`test_kill_and_recover` in `tests/test_drive.py`. Built: the window of
section 4 (workspace tabs switching palette toolbars built from the
registry, outliner with enable checkboxes and the mode after each term,
properties forms generated from the parameter declarations, a Structure and
a Result tab, jobs and log docks, status bar); the structure canvas
(`ui/structure.py`: atoms as circles in data units coloured by sublattice,
pyqula's first-neighbour bonds, the neighbouring cells faded, the unit
cell, overlays for the selected region or removal op, wheel zoom, and the
pick, box and lasso tools plus select by sublattice or edge); formulas
rendered as images with matplotlib's mathtext (`ui/formulas.py`, a test
renders every registry formula); drag to reorder in the outliner (within an
entry's own list; the tree sends a `move` command and is rebuilt, Qt never
moves an item); the view state saved with the project; regions and
removals made from a selection (`remove_selected` grows a trailing Remove
atoms op, PLAN 3.1); the island op (`pyqula.islands`); the build summary
carries the geometry arrays (`engine/structure.py`); build requests
coalesce per system; `io/autosave.py` (debounced, driven from
`Session.poll()`, a recovered file is taken over so it stays recoverable
until saved) with a non-modal recovery bar; `io/crashreport.py` and an
exception hook with a non-modal error bar; a `duplicate` mutation; the
window's own actions (`select`, `workspace`, `tool`, `select_sites`,
`region_from_selection`, `remove_selected`) so drivers reach everything;
`tools/drive.py --recover --hold`; `$GUIQULA_DATA_DIR`. Left for later:
region kinds by rule that follow geometry changes (by sublattice or edge
distance; the canvas tools store positions), crash reports for worker
deaths (shown next to the job, as in phase 1), a 3D view (the canvas draws
xy; see answer 9 below). Maintainer's answers to the phase-2 report
(numbered as reported): 1, the project should remember the selection and
the workspace (done, see 3.1); 3, drag to reorder should exist (done; a
real mouse drag cannot be simulated offscreen, so the tests drive the drop
logic, `Outliner.drop_at`); 5, formulas should be images (done); 9, a 3D
view will be made for the cases that need it (geometries that are not
flat: 3D lattices, stacked or twisted layers), with pyqtgraph.opengl as in
section 2, when the first such lattices and ops arrive (phase 4). Items 2
(canvas selections stored as positions, no rule-based region kinds), 4
(no crash report for a worker death), 6 (the close prompt only in the
interactive program; since 2026-09-28 New, Open and Recover ask it too
when they would replace unsaved changes), 7 (recovery offers only
autosaves with unsaved changes) and 8 (island size from n alone) were not
commented on and stand as built. Facts
learned: with `geo=` given, `islands.get_geometry` still takes the default
`nedges` from `name="square"` (4), so the entry always passes it, and the
island size does not depend on the input cell (inradius 1.5 n); PySide6
6.11 hands exceptions raised in slots and timers to `sys.excepthook`;
`QScrollArea.setWidget` deletes the previous widget at once and
`QTreeWidget.clear()` deletes items, so a form or a tree rebuilt from
inside one of its own signals must be deleted later (the window does);
pytest-qt creates the QApplication, so the theme is applied to an existing
application too; matplotlib's selectors and synthetic `MouseEvent`s work
offscreen (a press outside the axes is ignored), a Qt drag does not
(`QTest.mouseMove` carries no pressed button in Qt 6); mathtext renders all
registry formulas (1 s for the first, fonts, then milliseconds); `os.kill(pid, 0)`
terminates a process on Windows, so the autosave's liveness check uses
`OpenProcess` there; pyqula's KD-tree neighbour search takes 0.2 s for
10,000 sites.

**Phase 3 — Hamiltonian workspace and results.** Term palette, schema forms
with `f(r)` expressions, invalid-entry flagging with pyqula's messages, job
panel with cancel, result tabs with interactive matplotlib, stale marking on
upstream edits, mean-field block. Acceptance: change the geometry after
setting terms and the bands re-run on the new geometry with the same terms;
cancelling a running job leaves the UI usable.
**Done 2026-09-26**, acceptance tests
`test_geometry_change_reruns_bands_with_the_same_terms`
(`tests/ui/test_hamiltonian_workspace.py`: the re-run result equals an
engine run of the changed Document, every term applied) and, from phase 1,
`test_cancel_running_job_keeps_window_usable`. Built: piecewise Fields
(3.8) in the core, the planner, the engine and the exporter; the `f(r)`
button and panel next to every Field that takes a function of position
(a number or an expression with its help, or one value per region plus
the default), one editor per component for vectors; the Field preview on
the structure canvas (the value being typed, restricted to the term's
region: colours for a scalar, in-plane arrows and z dots for a vector);
the Hamiltonian view of 13.8 (atoms by onsite energy, every hopping of
`get_multihopping()` with a width by |t| and a colour by phase, exchange
as arrows and dots; `engine/structure.hamiltonian_view`, from sparse
block reductions, up to 20,000 sites and pyqula's dense limit; the
interactive worker computes it only while the canvas shows it, since it
costs about as much as the build), with a Show box choosing among sites and bonds, Hamiltonian
and Field preview, and the workspaces choosing the first two; the
mean-field block (`Hamiltonian.meanfield` = enabled, kind, params, checked
by a registry entry of the new `meanfield` family: U as a Field, V1..V3
and J1..J3 constant-only, filling or chemical potential, the guess from
`meanfield.get_guess_names()`, seed, k-mesh, mixing, tolerance,
iterations, temperature; `set_meanfield`; an outliner row with its
checkbox and the converged energy; a form; a toolbar button), the last
stage of the plan, entering the mode pre-scan (it needs spin), run only
with the calculations: the interactive builds stop before it and report it
as deferred; one closable tab per calculation's result (`plot_<id>`) with
Save data, Detach into a window of its own and back (a button: dragging a tab
out is not offered), a readout of the data point under the mouse, and
"(stale)" in the tab; search boxes with completion on the op, term and
calculation palettes; the cost guard of 13.12 (`registry/cost.py`: an
order-of-magnitude duration from the build's Hilbert dimension, counting
dense diagonalizations for bands, DOS and the mean field, calibrated on
this machine at 2e-9 N³ s; shown in the status bar; a non-modal bar asks
before a run estimated above a minute; a note in the system's form above
pyqula's dense limit); opt-in automatic re-run of stale results estimated
under 3 s (Run menu, saved with the view state; it never pulls the
viewport to a result); terms Kane-Mele, antiferromagnetism and s-wave
pairing (the first term that upgrades to Nambu); the preset
`honeycomb_hubbard`; the batch workers warm the mean-field kernels too.
Decisions taken while building, for the maintainer to confirm: a mean
field that does not converge fails the calculation instead of being
skipped (14.3's skip semantics would hand the calculation the bare
Hamiltonian); the interactive builds are stamped with the system's full
key, mean field included, so that their reports are never stale (a
mean-field edit costs them a cache hit); `is_sparse` stays a plain
boolean: 13.12's automatic switch to sparse above `limits.densedimension`
waits for calculations that use sparse matrices (KPM, arpack), since
bands and the ED DOS diagonalize densely anyway. Left for later: the
Hamiltonian view shows the Hamiltonian before the mean field (the
converged magnetization belongs to the structure-vector plots of phase
4); the preview of a bond Field (Rashba, Haldane) shows its values at the
sites, not at the bond midpoints pyqula evaluates it at; persisting
mean-field results in projects (section 11); the cost model knows only
dense diagonalizations. Facts learned: `get_mean_field_hamiltonian`
returns None when the loop does not converge (the entry turns that into an
error) and routes spinful Hamiltonians to `VJinteraction`, which takes U
as a callable of position but V1..V3 and J1..J3 as numbers; its `T` and
`maxite` defaults are sentinels, so the entry passes the numpy engine's
values (mix 0.1, maxite 1000, T 1e-7) explicitly and the exported script
states them; the `antiferro` guess needs a sublattice (square lattices
without one raise); `add_swave` takes a callable, makes the Hamiltonian
spinful and then Nambu, with the per-site order (e↑, e↓, h↓, h↑) and the
singlet pairing at (4i, 4i+2); `add_antiferromagnetism` reads any list as
per-site values (and refuses one of another length), so a vector cannot be
given as a list and its entry takes a scalar Field (along z); a mean-field call takes 2 to 5 s the first
time in a process even with numba's cache warm; `get_multihopping()` of
a dense Hamiltonian copies every cell matrix (with the scan of each, the
Hamiltonian view takes 3 s for 2450 sites, dimension 4900, about the
time of the build); matplotlib truncates
synthetic mouse events to whole pixels; a `QTabWidget` tab loses its
close button with `setTabButton(index, side, None)`.
Maintainer's answers to the phase-3 report (numbered as reported): 1 to 4,
7, 9 and 10 stand as built (a mean field that does not converge fails the
calculation; the interactive builds carry the full key; `is_sparse` stays
a boolean; the cost guard is the window's only; auto re-run is saved with
the project; the search ranking; detaching by a button); 5, the filling
became a Field: a function of position gives pyqula one filling per site
(its numpy engine only), a constant stays a number; 6, the jax engine is
offered (engine numpy or jax, and the solver from
`densitydensity_jax.get_jax_solver_names()`), and the mixing, the
iterations and the temperature became optional, empty meaning the chosen
engine's own default (numpy mix 0.1, 1000 iterations, T 1e-7; jax 2000
iterations, T 1e-4, too sharp a T being unusable there), which the entry
then does not pass; 8, asked whether a function works for the
antiferromagnetic term: it does, also one returning a vector, so the term
now takes a vector Field (mx, my, mz) and always hands pyqula a function
(a list would be read as one value per site). Facts learned: jax is
imported on pyqula's usual path anyway, so listing its solvers costs the
worker nothing; the jax engine's first call compiles for about 5 s, then
takes milliseconds; its solvers other than linear mixing and Broyden
ignore (and warn about) the mixing; it refuses Nambu Hamiltonians and
per-site fillings; on the honeycomb Hubbard model at U = 3 the newton
solver ended at another total energy than linear mixing (-1.677 against
-1.691, jax and numpy linear mixing agreeing), so the result may depend on
the solver; pyqula refuses a per-site filling outside [0, 1]
with its own message, and a constant one is checked by the entry.

**Phase 4 — breadth and freedom.** Python nodes with the trust prompt,
embedded console, the rest of the geometry ops and terms, first-wave
calculations, structure-scalar and vector plots, classical spin, lattice-gas
and Ising systems with their palettes, Brillouin-zone canvas, sliders and
sweeps, result overlays, presets gallery from quantum-lattice's modes, project
save/load with results cache, script export for everything.
Built in four parts: (1) the breadth of the quantum registry and the plot
kinds, (2) Python nodes, the trust prompt and the console, (3) the
classical systems and `from_result` Fields, (4) the remaining Fields, the
Brillouin-zone canvas, sweeps, overlays, the presets gallery and results
in project files.
**Part 1 done 2026-09-26.** Built: 33 lattices (0D to 3D, the honeycomb
cells, ribbons with their width, multilayer graphene by stacking letters,
commensurate twisted bilayer graphene); 14 geometry ops (new: keep or
remove sites where a condition on the position holds, remove dangling
sites, make finite, film, orthorhombic cell, rotate, shift, center,
uniaxial strain; a condition is an AST-checked expression, `ConditionParam`);
21 terms (new: anti Kane-Mele, modified Haldane, Kekule, hopping
modulation, valley exchange, crystal field, electric field, orbital and
in-plane magnetic fields as Peierls phases, spin spiral, pairing of every
symmetry pyqula lists with its d-vector, phase disorder with a seed); 17
calculations (new: LDOS, electron density and magnetization on the
atoms, the local Chern marker of a finite system, Fermi surface, spectral
function along the path, surface spectral function, Berry curvature map
and along the path, Chern and spin Chern numbers, Z2, gap, total energy,
optical conductivity; the DOS gained KPM with a seed). The plot kinds
`heatmap`, `structure_scalar`, `structure_vector` and `scalar` (a table;
the outliner row shows the numbers); a result drawn on the atoms carries
the geometry it ran on (`Result.structure`, saved with the arrays), since
the UI process has no build of that snapshot. A 3D drawing of geometries
that are not flat (3D lattices, buckled or stacked layers) on the canvas
and in the results, with a 3D box and a `projection` window action (auto,
xy, 3d); the selection tools work on the flat drawing. Every calculation
that declares a seed is seeded by the engine and the exported script, as
the terms were. Entries declare the pyqula modules a custom script
imports (`modules`) and whether a region may restrict them (`regions`:
the hopping modulation multiplies what is there, so a region would zero
the Hamiltonian outside it; a piecewise Field does it instead). The term
search ranks a label starting with the text, then a word of a label,
before the rest. Tests: every entry against a direct pyqula call
(`tests/engine/test_entries.py`), every case exported and run in one
interpreter (`test_every_entry_exports`, `test_every_calculation_exports`),
a form for every entry (`tests/ui/test_forms.py`), each plot kind and the
3D canvas in the window (`tests/ui/test_result_kinds.py`).
Decisions taken while building, for the maintainer to confirm (numbered
in the phase-4 report): the 3D view is matplotlib's mplot3d, not
pyqtgraph.opengl as section 2 planned (Qt refuses OpenGL widgets on the
offscreen platform that the tests and tools/drive.py use, the conda build
here cannot load a GL driver either, and PyOpenGL is not a dependency; a
pyqtgraph view for large 3D systems can come with the phase-5 performance
pass); Z2 is reported as pyqula gives it, a parity (-1 topological, +1
trivial); the numbers of the new terms that pyqula takes as numbers only
(crystal field cutoff, electric field, spin spiral axis and wavevector) are
constant-only Fields, so the rule that every term number is a Field
holds; result figures use matplotlib's constrained layout (tight_layout
was computed at the figure's first size and clipped labels after a
resize). Facts learned: pyqula refuses a pairing function that is not
periodic with the lattice (its Fermi-antisymmetry check across cells), so
a modulated pairing needs a commensurate supercell or a finite geometry;
`add_valley_exchange` needs a Kekule-commensurate cell (a supercell of
the honeycomb cell whose size is a multiple of 3); `add_crystal_field`
and `add_valley_exchange` take numbers only, while `add_anti_kane_mele`,
`add_modified_haldane`, `add_kekule` and `add_pairing` (amplitude and
d-vector) take functions of position; `Geometry.shift(r0)` moves the
sites by -r0 and wraps them into the cell, `rotate(angle)` turns clockwise
in degrees and only up to two dimensions; `disorder.phase` returns a new
Hamiltonian (spinless, normal state only); `kdos.kdos_bands` passes its
keywords to `get_bands`, so `write=False` collides; `get_gap` is
deterministic (a seeded grid scan); `topology.z2_invariant` returns -1
for a quantum spin Hall insulator; the first magnetization and optical
conductivity in a process compile numba kernels for about 10 s each;
Qt prints "QOpenGLWidget is not supported on this platform" offscreen;
without tight_layout (which renders) matplotlib autoscales the limits
only at the first draw, so a readout needs a synchronous draw first.
**Part 2 done 2026-09-26.** Built: Python nodes (`registry/python_nodes.py`):
a geometry op, a term and a calculation whose parameter is Python source
(`CodeParam`, syntax-checked by the command, never run by it), executed in
the worker with `np` and `pyqula` in scope (op: `g`; term: `h` and `g`,
either changed in place or rebound; calculation: `h`, `g`, and it sets
`arrays` and may set `plot`, checked against the plot kinds). An error
flags the node with the line of its code and the stack carries on
(14.3); what it prints is kept with its report. A Python term declares
the Hilbert space it needs (`needs`: nothing, spin, nambu), so the
pre-scan fixes it before the first term (`EntrySpec.requires` may be a
callable of the parameters). Trust (13.7): `EntrySpec.runs_code`; the
planner takes `trusted` and plans a node of a document that is not
trusted as invalid (skipped, out of the keys, so trusting makes its
results stale); the flag is the Session's (`Session.trusted`, carried by
every job; `Session.plan_system`, `plan_calculation`, `calculation_key`
are the only planner calls of the UI, so its keys match the workers'). A
document built in the program or a shipped preset is trusted; one opened
or recovered from a file with Python nodes is not, until the `trust`
action (the trust bar with Trust and run and Show the code, a checkable
File menu entry, `--trust` for `guiqula run`, `guiqula script` and
`tools/drive.py`); the exporter writes an untrusted node as a skipped
comment. The code editor of a node (monospace, Apply or Ctrl+Return or
focus-out); the outliner shows its code as the tooltip. A build still
running `Session.build_patience` (10 s) after a newer one of the same
system is asked for is killed with the interactive worker (whose cache
goes with it; the next build redoes every stage), so a node stuck in a
loop is stopped as soon as its code is changed. The protocol's REQUEST
and REPLY: a job can ask the UI process during its run (the Session
answers "run" a dispatcher command, or "document"); `JobManager.submit`
refuses an unknown role. The console (14.1): a third worker role,
`console`, started at the first command; its interpreter keeps a
namespace for the life of the worker with `doc`, `g` and `h` of the
selected system (built with the mean field, as the calculations see
them; rebuilt when the Document, the system, trust or a result its
from_result Fields read changed since the last command that used them),
`do()`/`act()` for dispatcher commands (undoable; not `console` itself,
which would wait for the worker that asks), `np`, `pyqula`; a final
expression is echoed; an error prints its traceback from the console's
own code and the job still ends normally (so does `exit()`);
Interrupt restarts the worker (the namespace is lost). `Session.console`,
the `console` and `interrupt_console` actions (drivers get the output
back), and the Console dock (tabbed with the Log: Enter runs, Shift+Enter
adds a line, Up/Down history). Tests: `tests/engine/test_python_nodes.py`,
the Python cases in `test_entries.py` and the export tests,
`test_a_job_asks_the_ui_process` and `test_console` in `tests/worker`,
`tests/ui/test_python_nodes_ui.py` (the trust bar, the code editor, a
node stuck in a loop, the console dock).
Decisions taken while building, for the maintainer to confirm: a
recovered autosave with Python nodes opens untrusted even if the session
that wrote it had trusted it (the autosave does not record trust); the
global "always trust" preference of 13.7 is not built (no settings file
yet); the console's `h` includes the mean field; the console is not
itself subject to trust (it is code the user types), but the nodes of an
untrusted document stay skipped in the console's builds too; a build
stuck longer than 10 s is killed only when a newer build of the same
system is requested.
**Part 3 done 2026-09-26.** Built: classical systems (decision 13.5,
`registry/classical.py`). The Document's `System.model` (a `Model`: the
kind of a registry entry of the new "model" family, its set-up
parameters, its term stack) replaces the Hamiltonian of a system of kind
`classical_spin`, `lattice_gas` or `ising`; `terms_of(system)` is a
system's term stack whatever its kind, so ids, regions, duplicate,
remove, move and undo work alike. The plan of a classical system is base,
ops, the model stage (pyqula's `SpinModel`, `LatticeGas` or
`LatticeIsing` built on a copy of the geometry, seeded: the initial
configuration is random) and the terms; its mode is its kind; no mean
field, no Hamiltonian view. Terms: Heisenberg shells J1..J3 with an
anisotropy, a magnetic field, the exchange tensors of
`generating_functions` (Dzyaloshinskii-Moriya, dipolar, RKKY on a TI
surface, ZZ, XYZ; within the cell or with the neighbouring cells in 2D)
for spins; interaction shells and a chemical potential for the lattice
gas; interaction shells and a field for the Ising model; the Python term
(it sees `model`). Couplings between shells are constant-only Fields, a
field or a chemical potential is a Field evaluated on every site. Calculations:
minimizing the spins (the texture as arrows, or the local energy), and
annealing the lattice gas or the Ising model over a geometric cooling
schedule (the configuration, the local energy or field, or the energy
and the magnetization along the anneal), seeded; the Python calculation.
Lattices and geometry ops apply to every kind. Commands: `add_system`
takes a `kind` (and `model_params`), `set_model`; `add_term` and
`add_calculation` refuse an entry of another kind. The window: New
classical system (on the usual lattice, in a supercell the usual orders
fit in), a Model branch in the outliner with its set-up row and form, the
term and calculation palettes and their search boxes offering the
entries of the current system's kind, the middle workspace tab reading
Model. `from_result` Fields (PLAN.md 3.8): a Field reads an array of
another system's result site by site (the nearest site within `tol`,
times `scale`, a component of a vector per site); the key of the entry
hashes the key of the result read (`ResultRef`), so running the source
again makes the reader stale, while a source that is merely stale leaves
the reader's key alone and flags it ("reads a stale result"); a Field
may not read its own system, nor go round in a circle through others,
and needs the result to have run and to be drawn on the sites. The
Session hands the results read (only the arrays read) to every job and
plans with them; the exported script defines `site_field` and holds the
values. The Field editor offers "from a result" (the calculation, the
array, the component, a scale); the preview draws it. Tests:
`tests/core/test_classical_document.py`, the classical cases in
`tests/engine/test_entries.py` and in the export tests,
`tests/engine/test_from_result.py` (a classical texture as the exchange
field of a quantum ladder, equal to pyqula's own `add_zeeman` with the
array, and its exported script), `tests/ui/test_classical_ui.py`.
Decisions for the maintainer (section 11 had them open): the texture is
handed over by reference to the result (not a copied array), and a
reader of a stale result is flagged, not marked stale itself (its key
follows the data it read); the Ising temperature scan and the spiral
wavevector of `add_tensor_2d` wait for the sweeps of part 4. Facts
learned: `LatticeGas` and `LatticeIsing` set `g.nrep` on the geometry
they are given and draw their initial configuration, and their Monte
Carlo moves, from numpy's global generator in plain Python (so a seed
reproduces them); `SpinModel.minimize_energy` draws its random starting
angles the same way; pyqula's first-neighbour couplings of the classical
models go through `get_hamiltonian(tij=...)`, so a shell list is read as
first, second, third neighbours; the classical spin energy is a jax
function, and pyqula's jax modules switch jax to double precision
globally when they are imported (`jax.config.update("jax_enable_x64",
True)` at import time), so the same pyqula script minimizes to another
(degenerate) texture depending on what it imported before: the engine
now always runs jax in double precision (the workers did already, since
they list the jax solvers at start) and an exported script with classical
spins switches it on too (an entry's `preamble`). Worth fixing in pyqula.
**Part 4a done 2026-09-27** (part 4 is built in two halves). Built:
results in project files (a `.guiqula` zip holds `results/<calculation>.npz`
and `.json` next to `document.json`; opening it restores them, current or
stale by their keys; bare JSON and the autosave keep the document only;
the converged mean-field Hamiltonian is not kept, its total energy is,
in the reports: that settles the section 11 question). The presets
gallery (13.16): `Document.notes` (a title line and a description,
`set_notes`), ten new presets after quantum-lattice's modes and the
phase 4 features (Chern insulator, quantum spin Hall ribbon, graphene
island, Aubry-Andre chain, Landau levels on a ribbon, Majorana wire,
120-degree classical spins, lattice gas at 1/3, Ising ferromagnet, a
classical texture as an exchange field), and the gallery dialog (File,
Presets gallery). Overlays (13.11): the Overlay menu of a result view
draws other results on the same axes, or the difference of two curves on
the same x; the `overlay` window action; kept with the view state (a tab
dropped on another, as 13.11 said, cannot be driven offscreen, so it is a
menu, as Detach is a button). Sweeps (13.10): a calculation kind (the
section 11 question), `registry/sweeps.py`: another calculation of the
same system run at every value of one parameter or on a grid of two
(any number of an entry: a term's Field or a vector component, an op's or
a calculation's number, the lattice, the mean field, a classical model),
through the build cache; the numbers of its results collected, drawn as a
curve or a map; its key hashes the inner calculation's key; the cost
guard multiplies; the exported script loops over a function of the
value (the swept parameter is set to a sentinel number while the inner
script is generated, then replaced by the loop variable, so every way a
parameter reaches the code works). Sliders (13.10): a Sliders dock
(tabbed with the Jobs) with a slider per parameter and its range, the
`slider`, `set_slider` and `remove_slider` actions, kept with the view
state; a drag is one undo step (`Dispatcher.do_merged` and `end_merge`).
Tests: `test_results_are_kept_in_the_project`, `test_presets_gallery`,
`test_every_preset_exports` (every preset's first calculation against its
script, in one interpreter), `test_overlays`, `tests/engine/test_sweeps.py`
(the Haldane phase diagram point by point against pyqula, the scripts),
`test_merged_mutations_are_one_undo_step`,
`test_sliders_and_a_sweep_in_the_window`.
**Part 4b done 2026-09-27.** Built: the Brillouin-zone canvas (13.9,
`ui/kspace.py`), a fixed viewport tab next to the Structure: the zone of
the current system (the Wigner-Seitz cell of pyqula's reciprocal lattice,
a_i . b_j = delta_ij), the high-symmetry points pyqula names for its
geometry, pyqula's default path (dashed), the k-path of the chosen
calculation with vertices that are added (Add points), dragged (they
snap onto the high-symmetry points), removed, or reset to the default,
and the latest Fermi surface of the system underneath; the worker hands
k-space in the build summary (`engine/structure.kspace`: the reciprocal
vectors, the map from pyqula's mesh coordinates to reduced k, the
special points, the default path). The bands and the spectral function
take a `kpath` (`KPathParam`: labels or reduced coordinates; a label takes
the image nearest to the vertex before it, ties going to the image
nearest the origin; `registry/kpaths.py` spreads the points, and the
exported script defines the same functions); the vertices become named
ticks (the engine names a vertex after the high-symmetry point it is an
image of). The remaining Fields (3.8): `profile` (gaussian, step, disk,
plane wave, Aubry-Andre, domain wall: an expression once its numbers are
filled in), `interpolated` (control points smoothed with Gaussian
weights) and `painted` (values per site by position and a default), with
their panels in the Field editor, and the brush of the Field preview
(the Paint tool with its value, radius and component; the `paint`
action; a stroke is one undo step; painting a Field that is not painted
yet keeps its values: a constant becomes the default, anything else is
baked into every site). Tests: `tests/ui/test_kspace.py`, the k-path
cases of the bands and the spectral function, the new Field kinds in
`tests/core/test_fields_regions.py` and on the onsite term in the engine
and export tests, `test_new_field_kinds_and_the_brush`.
**Phase 4 done 2026-09-27.** Decisions taken while building, for the
maintainer to confirm (numbered for the phase-4 report; the parts above
say more):
1. the 3D drawing is matplotlib's mplot3d, not pyqtgraph.opengl (Qt
   refuses OpenGL widgets offscreen, PyOpenGL is not a dependency);
2. Z2 is reported as pyqula's parity (-1 topological, +1 trivial);
3. the numbers of the new terms that pyqula takes as numbers only are
   constant-only Fields (crystal field cutoff, electric field, spin
   spiral axis and wavevector);
4. result figures use constrained layout;
5. the palette search ranks a label that starts with the text, then a
   word of a label, before the rest (the phase-3 ranking, refined for the
   larger palettes);
6. the hopping modulation (a factor) refuses a region: a piecewise Field
   does it;
7. a recovered autosave with Python nodes opens untrusted;
8. no global "always trust" preference yet (no settings file);
9. the console's `h` includes the mean field, and the nodes of an
   untrusted document stay skipped in the console's builds;
10. a build is killed only when it has run 10 s and a newer build of the
    same system is asked for;
11. a classical texture is handed over by reference to the result (a
    `from_result` Field), and a reader of a stale result is flagged, not
    marked stale (section 11);
12. project files keep the results, not the converged mean-field
    Hamiltonian (section 11);
13. sweeps are a calculation kind collecting numbers (section 11);
14. overlays are chosen from a menu, as detaching is a button (a tab
    dropped on another cannot be driven offscreen);
15. a new classical system starts in a supercell its usual order fits in;
16. the k-space canvas stores the vertices where they are drawn and the
    engine names them; typed labels take the nearest image;
17. painting a Field bakes its values into the sites (undo restores it);
18. the engine always runs jax in double precision, and so do exported
    scripts with classical spins (pyqula's precision otherwise depends on
    what was imported before: worth fixing upstream);
19. not built: the Ising temperature scan and the spiral wavevector of
    the classical tensors, the automatic switch to sparse storage (KPM
    now exists; `is_sparse` stays the user's), the calculations of
    section 5 still missing (QPI, entanglement spectrum, RPA and magnons,
    transport, the real-space Chern density against energy); and the
    arrays a `from_result` Field reads travel with every job (build, run,
    console), which is nothing for a texture of a few hundred sites and
    will matter for a large result.
Items 18 and 19 are not decisions: 18 is a fact about pyqula worth
fixing upstream, 19 lists what phase 4 left out. The pyqula facts of
phase 4 (item 18, kdos_bands and write=, the unclear errors of
add_valley_exchange and add_crystal_field, the sign of Geometry.shift,
the .OUT files written without a write= switch, and smaller points) were
sent to the pyqula Claude session on 2026-09-27, at the maintainer's
request; the pyqula repository itself was not touched. Items 11 to 13 settle
three questions of section 11 once confirmed. The maintainer then asked for
phase 5 (2026-09-27) without commenting on items 1 to 17, so they stand as
built, as the uncommented items of phase 2 did; an answer later still changes
them.

**Phase 5 — polish. Done 2026-09-27** (four parts below). Undo everywhere, keyboard shortcuts, theming (light and
dark), tooltips (the registry's one-line docs and formula images), in-app
help from pyqula's own documentation (13.13), guiqula's user guide, example
projects, teaching presets and exports (13.16), performance passes
(pyqtgraph canvas for large islands, if the measurements ask for it).
Built in four parts, the help last so that the answers to its open points
(section 11) can arrive meanwhile: (1) a settings file, light and dark
themes, keyboard shortcuts, undo, tooltips; (2) teaching exports, locked
parameters, example and teaching presets; (3) performance; (4) the in-app
help and guiqula's user guide.
Design (2026-09-27), numbered for the maintainer; items 1 to 7 are the
recommendations for the open points of 13.13, recorded in section 11:
8. a settings file (JSON in the user config directory,
   `$GUIQULA_CONFIG_DIR` for the tests and drivers) holds the theme, the
   recent files and 13.7's "always trust" preference (off by default; it
   was phase-4 item 8);
9. themes light, dark, and following the desktop (the default when Qt
   reports the desktop's scheme, else light); the canvas, the plots, the
   formula images and the console follow; exported figures keep a white
   background;
10. undo: the Undo and Redo entries name the step, an undo history jumps
    back several steps, Ctrl+Y redoes too, the selection follows the step
    undone; a calculation keeps its last few results by key, so undoing an
    edit brings back the result that matched it without a re-run; the view
    state (selection, workspace, sliders, overlays, theme) stays outside
    undo, as in Blender;
11. shortcuts: one table that the menus, a Help > Keyboard shortcuts
    dialog and the user guide share; the canvas tools take single keys only
    while the canvas has focus; a test refuses ambiguous shortcuts;
12. teaching (13.16): Export figure, data and script, one folder per
    result (the figure as PNG and PDF, the arrays as .npz and, for curves,
    .csv, the pyqula script, the document); locked parameters (`lock` and
    `unlock` mutations, a lock in the form, commands refusing a change): a
    guide for students, not a protection, since unlocking is one command;
    teaching presets with locks;
13. example projects are presets (JSON, in the gallery), not `.guiqula`
    files with results kept in git;
14. performance: the choice between matplotlib with a level of detail and
    a pyqtgraph canvas is made from measurements in the window (a
    20,000-site island through tools/drive.py, and a mutation of a document
    holding a painted Field of 20,000 values), reported with the numbers.
    Measured so far (agg, no window): the canvas draws a 21,600-site island
    in 0.25 s and a 60,000-site one in 0.7 s, data-unit circles being half
    of it (a scatter of the same points: 0.03 s); pyqula's island op takes
    10 s and 77 s to build them.
**Part 1 done 2026-09-27.** Built: the settings file (`io/settings.py`:
theme, recent files, always trust; defaults for a missing or broken file,
unknown keys kept; only the interactive program's window reads and writes
it, `MainWindow(use_settings=True)`, so tests and drivers never depend on
it or change it; `$GUIQULA_CONFIG_DIR`, set by the test suite). Themes
(`ui/theme.py`): light and dark palettes, and "follow the desktop"; the
colour names of the module are the active theme's (rebound by `apply`),
every figure is drawn inside `theme.drawing(figure)` (background, rc
settings, tick colours), and a change of theme redraws the canvas, the
k-space tab, every result view, the outliner and the formula images; View
> Theme and the `theme` window action. Keyboard shortcuts (`ui/shortcuts.py`,
one table): the menus, the outliner keys (F2 rename is new), the canvas
keys while the canvas has the focus (P, B, L for the tools, Ctrl+A,
Ctrl+Shift+A, Ctrl+I to select, Del to remove the selected atoms, Home to
show everything), Ctrl+Y as a second Redo, Ctrl+E export, Ctrl+F the
palette search of the workspace, Ctrl+W close the result tab, Ctrl+0 the
Structure tab, Help > Keyboard shortcuts (Ctrl+/). Undo: every step is
named (`commands/steps.py`; a test fails for a mutation without a text),
Edit > Undo and Redo say which step, Edit > Undo history goes back or
forth several steps at once (`undo(steps)`, one event), the selection
follows the step (its entry, or its system when the entry is gone; the
viewport stays), and the Session keeps up to 4 earlier results per
calculation, so that an undo (or a value set back by hand) makes the
matching one current without a re-run (a run that ends after the undo
joins the earlier results: the matching one stays current, fix of
2026-09-28); `undo`, `redo` and `history` are session actions for
drivers. Tooltips: the palette menus show the entry's
label, doc, formula image and the Hilbert space it needs (their tooltips
were set before but never shown: a QMenu hides them unless asked); every
toolbar control has one, with its keys; a parameter's label carries its
doc. File > Open recent and File > Always trust Python code in files (the
Session's `always_trust`). Tests: `tests/core/test_settings.py`, the undo
steps in `tests/core/test_commands.py`,
`test_an_undo_brings_back_the_earlier_result`, `tests/ui/test_polish.py`
(no ambiguous shortcut, every one bound; the canvas keys; the named steps
and the history; the dark theme by pixels and colours, and back; the
settings of the program's window; the tooltips). Facts learned:
matplotlib makes most ticks at the first draw, after an rc context has
ended, so the theme colours them explicitly; Qt rich text shows `data:`
image URIs, so a tooltip carries a formula image without files; PySide
hands `QAction.triggered`'s `checked` to a slot whose parameter has a
default (`undo(steps=1)` got `steps=False`), so such slots are connected
through a lambda; offscreen, `QTest.keyClick` on the focused canvas fires
its widget shortcuts.
**Part 2 done 2026-09-27.** Built: locks (`core/locks.py`,
`Document.locks`): a lock names an entry (`t1`), a parameter (`t1.m`;
`s1.n` for a lattice's) or a system's geometry (`s1/geometry`); the
dispatcher refuses any mutation that changes what a lock covers, by
comparing the Document before and after it, so no mutation needs its own
check; `lock` and `unlock` are undoable mutations; the forms disable what
is locked and say so on the labels, a parameter's label locks or unlocks
it (right click), the outliner marks what is locked and its context menu
locks an entry or a system's geometry, Edit > Unlock everything. Export
figure, data and script (`io/bundle.py`, the Export button of a result
view, File menu, Ctrl+Shift+E, the `export_bundle` window action): one
folder with the figure as PNG and PDF drawn in the light theme whatever
the window shows (`theme.drawing(figure, "light")` also swaps the colour
names while it draws), the arrays (.npz and .json), a CSV of the curves or
of the numbers, the pyqula script and the document, both from the
result's own snapshot, so a stale result is reproduced as it was, and a
README. Presets: two teaching presets with locks (`ssh_chain`: the
infinite chain's bands and a 42-site chain's end states, the modulation
free; `graphene_basics`: bands, DOS and gap, the terms free), two examples
(`zigzag_ribbon_magnetism`: Hubbard edge magnetism in the mean field;
`kagome_flat_band`), and the Haldane preset gained its phase diagram (c4,
a sweep of the Chern number over the imbalance and the Haldane coupling,
117 points in 9 s). The gallery groups the presets that lock something
(teaching) apart from the others (examples). A result on the atoms of a
chain (every site on one line) is drawn as a curve against x: the atoms of
a 42-site chain were too small to read a colour from. Tests:
`tests/core/test_locks.py`, `test_locks_in_the_forms_and_the_outliner`,
`test_export_figure_data_and_script` (the PNG is white in the dark theme,
the CSV equals the arrays, the script reproduces them),
`test_values_on_a_chain_are_a_curve_against_x`, the gallery groups in
`test_presets_gallery`; `test_every_preset_exports` covers the new
presets. Facts learned: a 21-cell supercell of `geometry.bichain()` is
centred on the origin and ends on intracell bonds (a 20-cell one ends on
intercell bonds), so which chain is topological with a given modulation
depends on the parity of the supercell; Qt greys out a list item without
flags, which the gallery uses for its headings.
**Part 3 done 2026-09-27** (performance). Measured in the window
offscreen (a honeycomb island of 21,600 sites, `island` n = 60, through
the interactive worker, and a painted Field on every site), before and
after:
| step | before | after |
|---|---|---|
| first build and draw | 79.5 s | 12.0 s (pyqula's island op: 10 s) |
| an edit: UI process / rebuild and redraw | 469 ms / 38.9 s | 20 ms / 0.7 s |
| select all / a box, and redraw | 26.3 s / 6.1 s | 0.16 s / 0.13 s |
| canvas redraw (zoom) | 173 ms | 103 ms |
| set a painted Field of 21,600 sites / next edit | 11.8 s / 13.4 s | 0.41 s / 0.2 s |
| 9,600 sites, three terms: worker memory after 3 edits | 10.5 GB, growing | 4.8 GB, bounded |
What changed: `core/nearest.py` finds the stored point nearest to a
position within a tolerance through a hash of cells of that size (27 cells
per lookup), one position at a time (`nearest_site`, pure Python, which
the engine's compiled Fields and the exported scripts use) or many with
numpy (`nearest_indices`); the canvas selection, regions by positions and
painted and from_result Fields used it quadratically before (an N x M
distance matrix, or a scan per site). A painted Field's sites are checked
with numpy. The Session reuses the plans and keys of a Document object
until the Document, the results or the trust change (a document event
planned the same system five times). The interactive worker builds a
Hamiltonian above pyqula's dense limit (`limits.densedimension`, 10,000)
with sparse matrices (`build_system(sparse_above=...)`, the construction
report says so), with a cache of its own, and does not draw its
Hamiltonian view; the calculations build as the construction says. The
build cache is bounded by memory (an eighth of the machine's, 1 to 8 GB,
`engine/build.nbytes`), not only by count: a dense Hamiltonian of 9,600
sites is 1.5 GB and every edit added one. The canvas redraws nothing when
only its caption changed (an edit waiting for its rebuild), and draws the
white outlines of the atoms only when they are at least 6 pixels wide
(stroking them was half of a redraw). Decision for the maintainer
(design item 14): no pyqtgraph canvas: matplotlib draws 21,600 sites in
0.1 s, and what was slow was elsewhere; the build of such an island is
pyqula's (10 s for 21,600 sites, 77 s for 60,000 in `islands.get_geometry`).
Tests: `tests/core/test_nearest.py`, the fast lookups in
`tests/core/test_fields_regions.py`,
`test_interactive_builds_are_sparse_above_the_dense_limit`,
`test_the_cache_is_bounded_by_memory`,
`test_plans_are_reused_until_something_they_depend_on_changes`,
`test_a_large_geometry_on_the_canvas`,
`test_sparse_storage_warns_for_position_dependent_couplings`. Facts
learned: pyqula builds a position-dependent Haldane, Rashba, Kane-Mele,
anti Kane-Mele or modified Haldane coupling differently with
`is_sparse=True` than dense (H(k) of a 2x2 honeycomb supercell differs by
up to 0.14 for the Rashba coupling, and the sparse Haldane one is not
Hermitian; constant couplings agree); the planner now warns when a
document asks for sparse storage with such a term, and the canvas never
draws a Hamiltonian it built sparse. Worth fixing upstream. matplotlib's
EllipseCollection and CircleCollection draw thousands of filled circles
equally fast: the outlines cost the time. `islands.get_geometry` is most
of the time of a large island (10 s for 21,600 sites).
**Part 4 done 2026-09-27** (the in-app help of 13.13, built as the
recommendations 1 to 7 of section 11 say, and guiqula's user guide). The
`docs` package, which never imports pyqula: `guide.py` splits a Markdown
guide into sections (headings outside fenced code; a heading's text is its
anchor, "Parent > Heading" when repeated; pyqula's guide has 250 sections
and no repeated heading) and turns the equations into mathtext images
after a few rewrites (`\tfrac`, an unbraced `\mathbf k`, `\frac12`,
`\sqrt3`, `\left(`): 998 of the guide's 1000 equations are drawn, the two
matrices are shown as their source. `docstrings.py` reads pyqula's
docstrings from the source of the copy in use with `ast`, following
relative and star imports, aliases and `@get_docstring`; for the 95 pyqula
calls behind the registry entries the text equals `inspect.getdoc`
(`tests/engine/test_help_docstrings.py`). `entries.py` puts an item's help
together: label, group, doc, formula, the Hilbert space it needs, the
parameters table, the pyqula code with the current values, the docstrings,
the sections the entry names (`EntrySpec.guide`; lattices default to
"Setting up a Hamiltonian") and the reference section of each of its calls
(the guide's "Main functions and methods" chapter: "h.add_zeeman()",
"sm.add_heisenberg()"...), in full, and up to eight links to other
sections whose code calls them; a custom entry declares its calls
(`EntrySpec.pyqula`). guiqula's own items (a system, a region, the
calculations) show a section of guiqula's user guide
(`src/guiqula/docs/user_guide.md`: the window, systems, selections and
regions, terms, Fields, the mean field, classical systems, calculations,
sweeps and sliders, overlays and exports, the k-space tab, Python nodes
and trust, projects and locks, undo and themes, headless use, the
shortcuts, help; its shortcut table is checked against
`ui/shortcuts.py`). The Help dock (`ui/help.py`, tabbed with Properties):
F1, a form's ? button, Help > pyqula user guide and guiqula user guide, the
`help` window action; Markdown in a QTextBrowser whose `loadResource`
serves the equations (`formula:N`), `help:` links between sections, Back;
while it shows an item's help it follows the selection, and a change of
theme draws its page again (the equations take the text colour). A
chapter of pyqula's guide (a top-level section with sections, up to 965
lines) is shown as its introduction and links to its sections: a
lattice's help quoted all of "Setting up a Hamiltonian" (38 equations). Packaging:
`setup.py` copies `vendor/pyqula_user_guide.md` into the wheel as
`guiqula/_vendor/pyqula_user_guide.md`, and guiqula's guide is package
data; `vendoring.find_guide()` takes the guide of an override's tree when
it has one. `tools/update_vendor.sh` stops before copying when upstream
has no guide, and runs the help tests after copying; CLAUDE.md lets anchor
fixes join a refresh commit. Tests: `tests/test_help.py` (sections,
equations, every anchor of the registry, every entry's help, the guides'
contents, an override's guide), `tests/engine/test_help_docstrings.py`,
`tests/ui/test_help.py` (F1, following the selection, links and Back, the
?, the shortcut table, mathtext over the whole guide), the wheel test.
Facts learned: Qt's Markdown drops an image without alt text (`![](x)`)
and does not load `data:` images in Markdown (it does in HTML), while a
QTextBrowser subclass's `loadResource` serves any scheme; link targets need
percent-encoding; pyqula gives no docstring to 20 of the 95 calls guiqula
uses (among them `h.get_dos`, `h.get_chern`, `h.get_berry_curvature`,
`h.get_fermi_surface`, `g.get_supercell`, `islands.get_geometry`,
`ribbon.bulk2ribbon`) and a one-line one to 48, and its guide's reference
chapter has no section for 55 of them (the lattice constructors, most
geometry methods, `disorder.anderson`): worth completing upstream, since
the help shows whatever pyqula writes.
**Phase 5 done 2026-09-27.** Decisions for the maintainer to confirm,
numbered after the design items 1 to 14 above (which were built as
designed, item 14 deciding against a pyqtgraph canvas with the numbers of
part 3):
15. an undo brings back up to 4 earlier results per calculation, by key;
16. locks are checked by comparing the Document before and after any
    mutation; a locked system freezes everything in it; a copy of a locked
    entry is free; `Document.locks` is a new field (the schema version
    stays 1: an older guiqula refuses a file that has it);
17. an export writes the script and the document of the result's own
    snapshot (a stale result is reproduced as it was); since 2026-09-28 a
    result also keeps the results its from_result Fields read
    (`Result.reads`, in its file under the json's `layout`, with the
    geometry of a result on the atoms), so its script reads those, not the
    source calculation's current result or none;
18. a result on the atoms of a chain is drawn as a curve against x;
19. the interactive builds use sparse matrices above pyqula's dense limit
    and then draw no Hamiltonian view; the calculations still follow the
    construction (13.12's automatic switch for them stays unbuilt);
20. a worker's build cache takes at most an eighth of the machine's memory
    (1 to 8 GB);
21. the planner warns when sparse storage meets a position-dependent
    Haldane, Rashba or (anti) Kane-Mele or modified Haldane coupling;
22. "always trust" is the window's setting only: `guiqula run` and
    `tools/drive.py` still need `--trust`;
23. the Help dock follows the selection while it shows an item's help;
    the sections an entry names and the reference sections of its calls
    are shown in full, other sections as links;
24. the Haldane preset gained the phase diagram (c4) instead of a new
    preset; teaching presets are those with locks.

**Phase 6 — distribution and add-on.** PyPI release, conda file, installers for
Mac/Windows, plugin entry points and a plugin template, JSON-RPC server + MCP
wrapper (the Claude add-on).
Asked for on 2026-09-27 ("continue with the plan") without comments on the
phase-5 report, so its items stand as built. Planned in parts, ordered by
what can be verified on this machine: 1, remote control and the MCP add-on;
2, plugins; 3, distribution (only Linux can be tried here; nothing is
uploaded or pushed without the maintainer).
**Part 1 done 2026-09-27** (remote control and the Claude add-on, 3.7).
Built: the `remote` package. `api.py`: `RemoteAPI`, the methods a client
calls over a Session, JSON in and out (`status`: the outline with each
system's entries, Hilbert space, latest build and invalid entries, the
calculations with status and estimate, the undo steps, the window's state;
`document`; `commands`; `catalogue`: registry entries with their
parameters, filtered by family, system kind or words; `do`: any mutation or
action, replying once the geometry is rebuilt, as tools/drive.py waits;
`run`, `wait`, `cancel`; `result`: summary, shapes and ranges, and the
values asked for, thinned along the first axis beyond `max_values`
numbers; `plot`: the result's figure drawn with Agg in the light theme;
`screenshot` and `widgets`; `help`: an item's, an entry's or a guide
section's Markdown, a heading found by its start; `script`; `console`;
`journal`). A method that waits returns a `Pending`, which the server
checks at every poll, so a calculation never holds up the window. `do`
of an action that waits for its job (`console`, `run_calculation` with
`wait`) starts the job and its reply waits for it, at most `timeout`
seconds (a console loop held up `guiqula serve` and the window, and no
client could interrupt it); a timeout or `max_values` that is not a
number is refused before anything is done; without a window a result
that a from_result Field reads rebuilds the systems, as the window does
(fixes of 2026-09-28).
`server.py`: JSON-RPC 2.0, one message per line, on 127.0.0.1 (a free
port), `hello` with the token first or the connection is closed; the host
polls it from its own loop (the window's 30 ms timer, `guiqula serve`), so
the Session is only touched from one thread; a refused command (a
CommandError, a window action's ValueError) is -32000 with its message.
`connection.py`: a connection file per server (port, token, pid, whether a
window) in `$GUIQULA_DATA_DIR/remote`, mode 0600, deleted on close; files
of dead processes are deleted when listed. `client.py`: `connect()`.
`mcp.py`: `guiqula mcp`, the MCP server Claude Code starts (`claude mcp
add guiqula -- guiqula mcp`), 15 tools (status, document, commands,
catalogue, command, run_calculation, wait, result, plot, screenshot,
widgets, help, script, console, connect) and instructions for the model;
it drives the newest running window or `guiqula serve`, else a Session of
its own without a window; `connect` lists, attaches, starts a headless
session or opens a window (`launch`). File descriptor 1 points at stderr
while it runs, so pyqula's prints in the workers never reach the protocol
stream. `window.py`: the window's hooks. The window: File > Allow remote
control (kept in the settings file, off by default), `guiqula --remote`
for one run, a `remote` window action, "remote :port" in the status bar;
the connection file follows the document opened or saved. `guiqula serve
[document]`: a session without a window, which asks for the builds after
every change as the window does; SIGTERM stops it as Ctrl+C does, wherever
it is. The bridge answers a line it cannot parse, or a request that fails,
with an error and goes on; a connection file whose server no longer
listens (a window that crashed) is deleted, and a window the bridge opened
is reaped when it ends (fixes of 2026-09-28). `tools/mcp_check.py` runs the official
MCP SDK's client against the bridge. The user guide has a section on it.
Tests: `tests/remote/test_server.py` (round trip, the token, malformed
requests, a pending reply that does not block another client, connection
files), `tests/remote/test_api.py` (every method over a Session with
workers), `tests/remote/test_mcp.py` (the protocol replies; `guiqula mcp`
as a process with its own session and attached to `guiqula serve`, line by
line, stdout holding only protocol; the SDK's client when
`$GUIQULA_MCP_PYTHON` names a Python that has it), and
`tests/ui/test_remote_window.py` (the offscreen window driven from a
client in another thread: status, screenshots, commands reaching the
outliner, a run drawn in its view, the switch and its setting; the list of
window actions). Verified with the MCP SDK 2.2.0 (in a scratch venv only):
its client negotiates 2025-11-25, lists the tools, reads text and image
results and `isError`. Facts learned: the MCP revision 2026-07-28 replaced
the handshake by a stateless per-request envelope; a 2026 client first
sends `server/discover` and falls back to `initialize` on any error except
an unsupported-version error naming only 2026 revisions, so a server that
answers "method not found" keeps working.
Decisions for the maintainer, numbered after the phase-5 ones:
25. remote control is off by default: File > Allow remote control (kept
    in the settings) or `guiqula --remote` for one run; a client with the
    token can do what the user can, the console and `trust` included
    (Jupyter's model: localhost only, a token in a file only the user can
    read);
26. the transport is TCP on 127.0.0.1 with newline-delimited JSON-RPC 2.0
    (a Unix socket would leave Windows out); no server thread: the host's
    loop polls it and a long request answers later;
27. the MCP protocol is written in guiqula (about 450 lines) instead of
    depending on the MCP SDK, which brings anyio, httpx, starlette, uvicorn
    and more; it speaks the handshake revisions 2024-11-05 to 2025-11-25,
    not the stateless 2026-07-28 one (clients fall back); so the `[claude]`
    extra of section 6 needs no dependency and is dropped;
28. the add-on is `guiqula mcp`, a subcommand, rather than 3.7's separate
    `guiqula-mcp` script;
29. the bridge attaches, at its first tool call, to the newest running
    window or server, else runs a session of its own without a window; it
    never loads a document into a window it attaches to (that would drop
    unsaved work); `connect` switches;
30. `command` replies once the geometry is rebuilt (as tools/drive.py
    waits); `result` sends at most 2000 numbers per array unless asked
    (thinned rows, and says so); `plot` draws in the light theme;
31. a window action's ValueError counts as a refused command (-32000),
    like a CommandError;
32. the "Ask Claude" panel inside the window (3.7) is not built: it needs
    the `anthropic` package, an API key and pays per use, and the MCP
    add-on already lets Claude Code drive the window. If wanted: a dock
    that calls the same `RemoteAPI` in-process through the Claude API's
    tool use, the key from `ANTHROPIC_API_KEY`;
33. a `.mcp.json` in this repository would register the add-on for every
    Claude Code session opened here (the maintainer's own configuration):
    offered, not added.
**Part 2 done 2026-09-27** (plugins, 3.2). Built: `registry/plugins.py`.
A plugin is an installed distribution with an entry point in the group
`guiqula.plugins` (its value a module that registers entries with
`registry.entry(...)` when imported, or a function that does), or a `*.py`
file in the user's plugins folder (`plugins` in the user configuration
directory), both as 3.2 planned. The registry loads them right after its
own entries, in every process that asks for an entry, so the window's
palettes, forms, tooltips ("from the plugin X") and help, the planner, the
workers and the exported scripts treat them as guiqula's own. A plugin that
raises, or registers a kind that is taken, is left out whole (what it
registered before failing is removed) and listed; one that imports pyqula,
jax or numba when loaded is loaded, with a warning (the window would then
load them, 13.15). Every entry names its plugin (`EntrySpec.plugin`, in
`describe()` and so in the remote catalogue). A document using an entry
that no plugin provides opens, the entry skipped and flagged ("unknown
term 'x': neither guiqula nor an installed plugin provides it", with the
plugins that failed to load). Help > Plugins (and the remote `help`,
guide "plugins") lists the plugins, their entries and their problems.
`$GUIQULA_NO_PLUGINS` turns them off; the test suite sets it, so a plugin
installed on the machine cannot change its results. `plugin_template/`:
a plugin package (pyproject with the entry point, one term: pyqula's chiral
Kekule hopping, which guiqula does not offer; a README; a test comparing
the entry with a direct pyqula call and running its exported script). The
user guide has a section on plugins. Tests: `tests/test_plugins.py` (fake
installed distributions on a temporary path, in fresh interpreters: the
template's entry registered, tagged, helped and run in a worker, the
window process free of pyqula; broken, colliding and heavy plugins; a file
of the plugins folder, run in a worker; a document with a missing entry;
the template's own tests; the Plugins page), the Help dock's Plugins page
in `tests/ui/test_help.py`, and the startup test now measures with the
plugins on. Measured: listing the entry points costs 15 ms among the 431
distributions of the development environment; the window's start is 1.1
to 1.2 s either way (budget 2 s).
Decisions for the maintainer:
34. plugins are trusted code, like any installed package: they are not
    behind the trust prompt of 13.7 (which is about code inside
    documents);
35. a plugin whose kind collides with one of guiqula's, or with an
    earlier plugin's, is refused whole rather than overriding it: the
    meaning of a saved document must not depend on which plugins are
    installed;
36. plugins add registry entries only; presets and guide sections shipped
    by a plugin (the gallery, the help) are left for later, if wanted;
37. the documents do not record which plugin an entry came from (no
    schema change): a missing one is reported as an unknown kind.
**Part 3 done 2026-09-27** (distribution, section 6), verified on Linux
only; nothing was uploaded or pushed (there is no remote). Built:
`README.md` (the PyPI description), the metadata of `pyproject.toml` (the
license as an SPDX expression, classifiers, keywords; setuptools 77 or
newer), `MANIFEST.in` (the sdist carries pyqula's user guide, which the
wheel build copies, and `plugin_template/`, not the tests), `environment.yml`
(the scientific stack from conda-forge, Qt and guiqula from PyPI),
`guiqula desktop [--remove]` (`desktop.py`: on Linux a desktop entry, the
icon in the hicolor theme and the MIME type of `.guiqula` files; on Windows
a Start menu shortcut written by PowerShell and the file association in the
user's registry hive; on macOS `~/Applications/guiqula.app`; from a source
checkout the entry carries `src/`), the icon (`resources/guiqula.svg`, a
honeycomb ring in the canvas's sublattice colours; PNG, ICO and ICNS made by
`tools/make_icons.py`, which writes the ICO and ICNS containers itself; the
window uses it), `env.launcher()` (the command that starts guiqula again,
the executable itself when frozen), a "bundled" origin in the vendoring
shim, `packaging/pyinstaller/guiqula.spec` and `launcher.py` (one folder
with two executables, `guiqula` windowed on Windows and macOS and
`guiqula-cli` a console program, sharing `_internal/`; pyqula collected as
source files, for numba's cache and the help's docstrings;
`freeze_support()` so that the frozen executable can start its workers; a
`guiqula.app` on macOS that declares the `.guiqula` document type),
`packaging/windows/guiqula.iss` (Inno Setup: a per-user install with a
Start menu entry and the file association), `.github/workflows/tests.yml`
(the suite on Linux, macOS and Windows with Python 3.11 to 3.13) and
`release.yml` (sdist and wheel, the PyInstaller folders with a smoke test,
a Linux archive, a macOS disk image, the Windows installer, and on a tag
the upload to PyPI by trusted publishing), `packaging/README.md` (what each
build is, what was verified, the release checklist). Tests:
`tests/test_packaging.py` (the conda file mirrors the dependencies; the
wheel built from the sdist, as pip does, with `twine check --strict`),
`tests/test_desktop.py` (the Linux files written and removed, valid for
`desktop-file-validate`; the Windows and macOS files as text),
`tests/test_frozen.py` (builds the PyInstaller folder and drives it when
`$GUIQULA_FROZEN_PYTHON` names a Python with PyInstaller: passed here in
57 s). Measured and verified here: a fresh venv installs the wheel from
PyPI's current dependencies in 61 s (1.2 GB: numpy 2.5.3, scipy 1.18.1,
jax 0.11.2, numba 0.67, matplotlib 3.11.2, PySide6-Essentials 6.11.2);
its `guiqula run` gives arrays equal bit for bit to the development
environment's (17 s with the first numba compilation); its window,
started offscreen with `--remote`, answers in 1.7 s and was driven and
photographed through the remote API. Python 3.13.15 installs the wheel and
runs `guiqula run` (the test suite ran on 3.12 only). PyInstaller 6.22.3
builds the folder in 36 s: 906 MB on Linux, of which jaxlib is 339 MB,
llvmlite 171 MB and Qt 99 MB (pyqula's dependencies dominate); the frozen
`guiqula-cli run` reproduces the arrays exactly, starting its workers; a
frozen `guiqula serve` answers in 0.3 s, with pyqula's docstrings in its
help and the console working; the frozen window was driven and
photographed. The name guiqula is free on PyPI (2026-09-27). Facts
learned: conda's pyside6 does not satisfy pip's PySide6-Essentials, so a
conda environment that also pip-installs guiqula would hold two Qt copies;
setuptools puts a project's top-level `tests/test*.py` into the sdist
unless told otherwise; the wheel builds from the sdist only when the sdist
carries `vendor/pyqula_user_guide.md`; Qt's ICO and ICNS writers are image
format plugins that are not found when only the platform plugin path is
set; after the window is killed its workers end by their watchdog within
seconds (checked with the installed program). A race in
`test_console_in_the_window` showed under load (it clicked the console's
Run while the previous console job was still ending, when the button is
disabled); the test now waits for the button.
Decisions for the maintainer:
38. the first release on PyPI as 0.1.0 (the version stays 0.0.1.dev0
    until you say; the upload is yours, or the release workflow's once the
    repository has a GitHub remote and PyPI knows it as a trusted
    publisher);
39. PyInstaller rather than Briefcase: verified here with the frozen
    workers, one spec for the three systems, maintained hooks for numba,
    jax and Qt; one folder rather than one file (a one-file executable
    would unpack 900 MB at every start);
40. two executables in the folder: `guiqula` (no console on Windows and
    macOS) and `guiqula-cli` (for `run`, `serve`, `script`, `mcp`);
41. the Windows installer and the macOS disk image are not signed (that
    needs a code-signing certificate and an Apple developer account): a
    first start warns once;
42. Linux gets pip (with `guiqula desktop`) and the folder as a .tar.gz;
    no AppImage or Flatpak;
43. the conda file takes Qt and guiqula from PyPI; a conda-forge recipe
    could come later;
44. the classifiers name Python 3.11 to 3.13 (3.12 fully tested, 3.13 a
    headless run); the CI matrix covers all three once it runs;
45. the icon: a honeycomb ring in the sublattice colours (easy to replace:
    the SVG and `tools/make_icons.py`).

Maintainer's answers to the phase-6 report (2026-09-27, asked one by one,
the ten most urgent first; numbered as reported): the repository goes to
GitHub, public, as `joselado/guiqula`, with nothing private in it: the
paths of the maintainer's computer are kept in `CLAUDE.local.md`
(gitignored), the history was rewritten before the first push to drop them
and the Claude session links of the commit messages (new commits carry no
session link), and the public email is jose.lado@aalto.fi; 25, 27, 34 and
35 stand as built; 33, the add-on is registered for the maintainer only
(`claude mcp add --scope local`), no `.mcp.json` is committed; 37, the
documents record which plugin an entry came from (an optional `plugin`
field, the plugin's name and version, on every entry of a plugin kind), so
a missing one is reported by name; 38, the first release is 0.0.1, built
by hand (`python -m build`, `twine check`) and uploaded by the maintainer,
without GitHub CI: the workflows are deleted, so nothing runs on the
repository; 39 to 42 are withdrawn: the frozen builds are dropped
(PyInstaller spec, launcher, Inno Setup script, their test and the
`sys.frozen` code paths), pip is the only way to install, `guiqula
desktop` keeps its icons (ICO, ICNS) for pip installs on Windows and
macOS; 44, Python 3.12 and 3.13 only (what has run: the full suite on
both); 26, 28 to 32, 36, 40, 43 and 45 were not asked and stand as built.

Asked for at the same time: a README for users, condensed matter physicists: how to
install, then what guiqula does, then examples by physical regime with screenshots (flat
bands, Chern insulator, quantum spin Hall, quantum Hall, interaction-driven edge
magnetism, Majorana wire, Aubry-Andre localization, a graphene flake with a gate,
frustrated classical spins, a classical texture seen by electrons). The images are in
`docs/images/` (about 2 MB, not in the sdist), linked by absolute URLs so that PyPI shows
them too, and `tools/readme_images.py` makes them again through `tools/drive.py`: every one
a screenshot of the whole window (the maintainer asked for the whole GUI rather than the
figure alone), with the entry that matters selected so its form shows next to the result. Found
while making them: the `texture_exchange` preset's field `0.6*tanh(x - 10)` assumed a
ladder from x = 0 to 20, but the finite ladder is centred, so the minimized texture was
uniform and there was no domain wall: it is `0.6*tanh(x)` now; `tools/drive.py --run`
failed with a KeyError when the cost guard asked before a slow run (the Haldane phase
diagram), and now answers "Run anyway" (the report's `cost_guard`). Not fixed: a heatmap in
a narrow result view clips its y tick labels (the Berry curvature map in a 1400-pixel
window); bands coloured by sz look noisy wherever the bands are degenerate (a zigzag
ribbon's), since the spin of a degenerate pair is arbitrary, so the README colours the
Kane-Mele ribbon by position instead.

Also asked: "update pyqula", then "do not include the whole pyqula, just src/pyqula". The
vendored copy was refreshed from upstream (19 commits, to 08a8179), and `vendor/` now holds
the package and upstream's user guide only (the guide stays, for the in-app help, the
maintainer's choice); upstream's examples were removed from `vendor/` and from the whole
history before the first push, and `tools/update_vendor.sh` no longer copies them.

**Phase 7, calculations from picks (proposed 2026-09-28; built the same day, in three parts).** Asked
for on 2026-09-28: to do calculations by picking parameters from the plots,
taking some bands and computing the LDOS at an energy selected on them, or
the LDOS at an energy and a k-point picked there, or the Fermi surface at
an energy picked from the bands, with every combination that makes sense
and an architecture of the interface that keeps them open. This block is
the plan as proposed; its decisions for the maintainer are at its end,
numbered 46 onwards after the phase-6 ones, followed by the answers and by
what each part built.

*The idea.* A plot draws one quantity against one or two others, so a
point of it is a small set of physical values: a point of a band structure
is a k-point and an energy, a point of a density of states is an energy, a
cell of a Fermi surface is a k-point at the energy the surface was computed
at, an atom of an LDOS map is a site, and a point of a sweep curve is a
value of the swept parameter. Any calculation whose parameters take those
quantities can be started from the point, or moved to it: the LDOS at the
picked energy, the LDOS at the picked k-point and energy, the Fermi surface
at that energy, the whole Document at that point of a phase diagram. What
keeps this open is that the pairs (bands to LDOS, DOS to Fermi surface) are
never written down: the plot kinds declare what their axes carry and the
parameters declare what they take, both in a closed vocabulary of
quantities, and what a click can do is computed from the declarations, as
sweeps and sliders fall out of the Document being data (13.10). Adding a
source or a target is then one declaration on an existing entry.

*The vocabulary* (`core/picks.py`, numpy only, like `nearest.py`):

- `energy`: an energy in units of the hopping; the y of a band structure
  or a spectral function, the x of a density of states, the `energy` of an
  LDOS, a Fermi surface or a QPI map, the y of a surface spectral function;
- `kpoint`: a point of the Brillouin zone in reduced coordinates (units of
  the reciprocal lattice vectors, as `KPathParam` stores a vertex and as
  pyqula's `hkgen(k)` takes it); the k of a band point or of a column of the
  spectral function, a cell of a Fermi-surface or Berry-curvature map, a
  vertex of a k-path, a click on the k-space tab;
- `sites`: sites, stored by position with a tolerance as regions and
  `remove_atoms` store them (never by index, so a pick survives a change
  upstream as far as it is meaningful); an atom of a result drawn on the
  structure, the canvas selection;
- `parameter`: the value of one parameter of the Document, named as sweeps
  and sliders name it (entry, param, component); the axis of a sweep curve,
  the two axes of a sweep map;
- `frequency`: the x of the optical conductivity, listed so that the
  vocabulary is complete; nothing takes it yet.

*Sources.* A calculation's plot spec names what its axes yield in `picks`:
`{"x": "kpath", "y": "energy"}` for the bands, `{"x": "energy"}` for the
DOS, `{"x": "kmesh", "y": "kmesh"}` for a map over the zone, `{"x":
"kpath", "y": "energy"}` for the spectral function, `{"y": "energy"}` for
the surface one (its k runs along the surface and is not a k-point of the
system), `{"x": "parameter"}` and `{"x": "parameter", "y": "parameter"}`
for a sweep (whose axes `sweeps.axes` already names), and a result drawn on
the atoms yields `sites` by its kind: the nearest atom on a click, or
several with box and lasso tools on the result view (decision 54; the
canvas's own tools, `ui/structure.py`, reused on the result's positions,
so that a box drag or a lasso on an LDOS map picks the atoms inside it and
the menu offers the targets for all of them). `core/picks.py` turns a position on
the plot into the quantities: `pick(result, x, y, radius)` snaps to the
nearest drawn point when the plot has points (a band point, a site, a
sampled value of a sweep: the readout's nearest-point rule, so what the
readout names is what a pick takes) and takes the cursor's coordinates
otherwise (an energy on a DOS or a spectral function, a cell of a map), and
returns `{"energy": 0.3, "kpoint": [1/3, 1/3, 0], ...}`, a label ("E =
0.30, k = (0.33, 0.33, 0)") and the snapped point, to draw. A Fermi surface
yields its own energy with the k-point, so a click on it is a (k, E) pair.
What the results must carry for this, verified on 2026-09-28: the bands
carry the k index (0 to nk - 1) and the spectral function pyqula's fraction
along the path (`ik / len(kpath)`, `kdos.write_kdos_bands`), so both gain a
`kpoints` array, the reduced k of every path point from
`h.geometry.get_kpath(kpath, nk=nk, write=False)`, the call pyqula makes
inside, so the exported script produces it too and `test_script_export`
keeps comparing; a map over the zone (Fermi surface, Berry curvature) is in
pyqula's mesh coordinates (-1 to 1), which the k-space tab already turns
into reduced k with the `k2K` matrix of the build summary, so the engine
attaches `kspace` (the reciprocal vectors and `k2K`, `engine/structure.kspace`)
to such a Result as it attaches `structure` to a result drawn on the atoms,
and a pick uses the result's own snapshot, never the current build; a
surface spectral function's k is 0 to 1 along the surface. A result saved
before phase 7 carries neither `kpoints` nor `kspace` (project files keep
the results), so a pick on it yields the energy alone and the menu says to
run the calculation again for the k-point; a result drawn in 3D (a
geometry that is not flat) has no picks, as its readout has no points.
Found while verifying (a screenshot through drive.py): the vertex ticks of
a spectral function along a custom k-path are placed at the vertices'
indices (`_path`'s note "xticks") on an axis that runs from 0 to 1, so the
vertical lines at 12, 18 and 28 stretch the axis and squash the map into
its left edge; fixed the same day in a commit of its own, by dividing the
tick positions by the number of path points (the arrays and the exported
script unchanged), the same mapping the picks will use to take a fraction
to its index.

Two more sources come at no cost once the targets exist, and the same
target list serves them: the k-space tab (a click on the zone, with Add
points off, yields a k-point: the LDOS or the eigenstate at that k) and the
structure canvas (the selection yields sites: the DOS on the selected sites
next to "region from selection").

*Targets.* A parameter declares the quantity it takes: `FloatParam("energy",
..., quantity="energy")` on the LDOS, the Fermi surface and the QPI map; a
k-point parameter (a `FloatVectorParam` of length 3 with
`quantity="kpoint"`) on the LDOS at a k-point and on the eigenstate;
`PositionsParam(quantity="sites")` on the DOS of sites; `KPathParam` takes a
k-point as a new vertex. `registry/picks.py` (pyqula-free, like
`pipeline.py`) lists what a pick can do on a system, in this order: for
every existing calculation of the system with a parameter taking a picked
quantity, "c3: energy = 0.30" (its other parameters kept: the broadening,
the mesh); for every calculation kind applicable to the system's kind with
such a parameter, "new LDOS at E = 0.30", the other parameters at their
defaults; for a `parameter`, "set t1 m[z] = 0.4", which puts the Document
at that point of the phase diagram; for a k-point, "add k to the k-path of
c1"; for sites, "select" and "region from the sites" (the window's existing
actions); and for an energy one target that is not a parameter, "Fermi
level to E": every calculation that counts the states below zero energy
(the Chern number, the gap, the density, the magnetization, the total
energy; not a mean field at a fixed filling, which pyqula solves at the
Fermi energy that filling needs, whatever the shift) is then computed at
the picked energy. It adds an `onsite` term with `mu = -E` named "Fermi
level", or updates the term of that name a previous pick added; the sign
shifts the spectrum so that the picked energy sits at zero. It is offered
on a stack without pairing only: on a Nambu Hamiltonian `add_onsite` enters
with opposite signs on the electron and hole blocks (`shift_fermi` through
`spinless2full`), a chemical potential that changes the pairing problem
rather than shifting the BdG spectrum, whose zero is the Fermi level
already. Locks (13.16) apply: a pick into a
locked calculation is refused by the dispatcher and the refusal is shown,
as a slider's is.

*The gesture.* Every result view answers a right click at a point, in any
navigation mode, with a menu: a title line with the picked values, then the
targets; choosing one runs a window action, and the readout says what
would be picked before the click. The alternative is a Pick toggle on the
view's toolbar with the left button, as the k-space tab has Add points; a
right click needs no mode and does not fight pan and zoom, whose right
button matplotlib uses for a drag only.

*Actions* (the window's, so they join `WINDOW_ACTIONS`, and drive.py, the
remote API and the MCP add-on get them for free): `pick(calculation, x, y)`
returns the quantities, the label and the targets of a point in data
coordinates; `pick_to(calculation, x, y, target)` does one target, by its
index in that list or as the dict itself. A new calculation is added, named
after its origin ("ldos at E = 0.30 from c1", the `rename` mutation, so the
outliner says where it came from) and shown; a set goes through
`set_param`. Whether it then runs is not the pick's business but a general
switch's (the maintainer's answer to decision 48): Run > Run at once, kept
in the settings like the theme, applying to every calculation, from a pick
or not. With it on, a calculation runs as soon as it is added (from the
palette too) or one of its parameters is set (from its form, a pick, a
command), through the cost guard; with it off, nothing runs until Run (F5)
or the automatic re-run of cheap stale results, which stays as it is,
since it answers another question (a result made stale by a change
upstream). A swept parameter has no calculation of its own, so what runs
after "set t1 m[z] = 0.4" is the sweep's inner calculation, the bands at
that point of the phase diagram; the system's other results go stale as
usual.

*The Document is unchanged.* A pick is a gesture that emits ordinary
commands (`add_calculation`, `set_param`, `add_term`, `rename`,
`run_calculation`), so the schema, the keys, the exported scripts and the
undo texts need nothing, and an undo takes a pick back as one step. The
alternative, a live link stored in the Document (a `from_pick` parameter
analogous to a `from_result` Field, so that the LDOS follows the pick made
on the bands), is not proposed: the picked value is a number the user
chose, and following it live is what part 3 builds, in the view state.

*Markers (part 3): sliders drawn on plots.* After a pick, the value stays
drawn on the source plot: a horizontal line at E across the bands or the
DOS, a dot at k on the Fermi surface, a vertical line on the sweep curve, a
ring around the atom. The marker is bound to what it set (entry, param,
component), which is exactly what a slider holds (13.10), so a marker is a
slider drawn on a result view: dragging it sets the parameter through
`do_merged` and `end_merge` (one undo step per drag) and, with the
automatic re-run on, the LDOS follows the line as it is dragged across the
bands; a slider, a form edit or an undo moves the marker too, since it
shows the parameter's current value. A slider spec gains `on` (the
calculation whose view draws it) and the axis follows from that view's
`picks`; the Sliders dock lists the markers with the sliders; they are view
state next to overlays and sliders (kept in the project's `ui` block,
pruned when the entry goes) and reached through the existing `slider`
(with `on`), `set_slider` and `remove_slider` actions.

*New calculations (part 2)*, each with its case in
`tests/engine/test_entries.py` (exported and run by the script test), a
cost, `guide=` and `pyqula=`:

- the LDOS gains an optional k-point (`k`; empty: the mesh of `nk`):
  pyqula's `get_ldos(ks=[k])` diagonalizes at that k alone
  (`ldos.get_ldos_tb`, mode arpack, which the entry uses; an explicit k is
  incompatible with the Green's function mode), so the cost is one
  diagonalization; the forms' vector editor gains an empty state; old
  documents load unchanged;
- `eigenstate` (Eigenstate at k): the eigenstates at a k-point
  (`htk.eigenvectors.get_eigenvectors(h, k=k)`; a finite system has no k),
  the one whose energy is nearest the picked energy (or a band index), its
  weight per site summed over the spin and Nambu components
  (`h.full2profile`, which handles both), drawn on the structure, the energy
  found in the caption. No guide section covers eigenstates; the entry names
  "Electronic band structures" and "Local density of states";
- `site_dos` (DOS on sites): the density of states projected on chosen
  sites, `h.get_dos(operator=P)` with P a diagonal matrix with 1 on every
  component of the sites within the tolerance of the picked positions (one
  per site spinless, two spinful, four in Nambu, the block sizes
  `full2profile` uses), which `get_operator` takes as a raw matrix. Not
  `get_operator(callable)`, which builds its operator with `add_onsite` and
  so carries opposite signs on the hole block of a Nambu Hamiltonian, where
  it is no projector; an engine test against that call would be wrong on
  both sides. A curve against energy. The same projector as the operator of
  the bands (their weight on the sites) is its natural second use, and a
  region as the operator of any calculation is the generalization, later;
- `qpi` (Quasiparticle interference, listed as missing in section 5):
  `h.get_qpi(energies=[E], nk=, delta=, mode=, write=False)` on a
  two-dimensional system, a map over q at the picked energy; its cost grows
  as nk squared and then the autoconvolution.

*Tests.* `tests/core/test_picks.py`: a band point to its k-point and
energy, a heatmap cell to reduced k through `k2K`, a site and a sweep
sample snapped, a spectral-function column from its fraction;
`tests/core/test_registry.py`: every `picks` and every `quantity` in the
closed vocabulary, and every parameter with a quantity of a type the picks
can set; `tests/engine`: the cases of the new calculations against direct
pyqula calls, a bands result whose `kpoints` equal `get_kpath`'s, a
Fermi-surface result whose `kspace` maps a cell to the reduced k the
k-space tab gives; `tests/ui/test_picks.py`: a pick on the bands view
offscreen (`pick` lists the targets, `pick_to` adds and runs an LDOS whose
energy is the picked one and shows it), the menu of a synthetic right
click (built by a method of its own and shown with `popup()`, never
`exec()`, so the test reads its actions without blocking the event loop),
a locked calculation refused with a message, a box on an LDOS map picking
the atoms inside it, a marker drawn and
dragged setting the parameter in one undo step; the help test for the new
entries' anchors and for the user guide's section "Picking from a plot";
the `WINDOW_ACTIONS` test; drive.py examples in CLAUDE.md.

*Parts.* 1: the vocabulary, `core/picks.py`, `registry/picks.py`,
`kpoints` and `kspace` on the results, the menu, the two actions, the
sources bands, DOS, Fermi surface, spectral function, structure plots and
sweeps, and the targets LDOS, Fermi surface, Fermi level, the swept
parameter, the k-path vertex and the site selection. 2: the new
calculations, and the k-space tab and the canvas as sources. 3: the
markers.

Decisions for the maintainer:
46. a pick is a gesture emitting ordinary commands and the Document does
    not change (against a live link stored in it);
47. a right-click menu on every result view, with no mode to switch
    (against a Pick toggle on the toolbar);
48. a pick runs its target at once, through the cost guard, whether it adds
    a calculation or sets one; the existing calculations of the system are
    listed before the new ones;
49. the LDOS gains an optional k-point (against a separate entry "LDOS at a
    k-point");
50. which of the new calculations to build: the eigenstate at k, the DOS on
    sites, QPI;
51. the markers as sliders drawn on plots, in part 3 (or first, or not at
    all);
52. the Fermi-level target: an onsite term named "Fermi level" with
    `mu = -E`, updated by the next pick;
53. the k-space tab and the structure canvas as sources, in part 2;
54. one site per click on a result drawn on the atoms; several through the
    canvas selection ("select" puts the site there, where box and lasso
    extend it).

Maintainer's answers (2026-09-28, asked one by one): 46, a pick is a
gesture emitting ordinary commands, the Document holds the number, and a
marker of part 3 drives one parameter as a slider does (the live link in
the Document, and a marker driving several parameters, were explained and
not taken); 47, both gestures: a Pick toggle on the view's toolbar (a left
click with it on) and the right click in any mode, two paths to one menu;
48, not a rule of the picks but a general switch, "run at once", applying
to all calculations: on, a calculation runs as soon as it is added or set,
off, only when explicitly asked (assumed: a Run-menu switch kept in the
settings, on by default, going through the cost guard, next to the
existing re-run of cheap stale results, which stays); 49, the LDOS gains
an optional k-point; 50, all three new calculations: the eigenstate at k,
the DOS on sites and QPI; 51, the markers in part 3, after the
calculations; 52, the Fermi-level target as an onsite term named "Fermi
level", on stacks without pairing; 53, the k-space tab and the canvas as
sources, in part 2; 54, several sites at once: the result views drawn on
the atoms get box and lasso tools too, next to the one-atom click.

Part 1, built 2026-09-28. `core/picks.py` holds the vocabulary (`QUANTITIES`,
and `AXES`, what an axis carries: kpath, kmesh, energy, parameter, frequency)
and `pick(result, x, y, index, sites)`, which reads a point as its values:
a place along a k-path through the result's `kpoints`, a cell of a map
through its `kspace` (the node of the mesh nearest the cursor, taken to
reduced k by `k2K`), the swept parameters of a sweep through the
`parameters` its plot spec names, the value a calculation holds through
`fixed` (the Fermi surface's energy), the sites of a result on the atoms by
position. The snapping is the readout's own: the window asks the view for
the drawn point nearest the cursor within its radius, so what the readout
names is what the pick takes, and the readout now says so ("a pick takes
E = 0.3 · k = (0.333, 0.333, 0)"). `registry/picks.py` computes the targets
in the order proposed; the new-calculation targets come from the
parameters' `quantity` (`energy` on the LDOS and the Fermi surface), and a
calculation of two-dimensional systems only says so in `extra["dimensions"]`
(the Fermi surface), so it is not offered on a ribbon. The bands and the
spectral function carry `kpoints` (the exported scripts compute it too, and
`test_script_export` compares it; (0, 3) on a finite system, which has no
k), the Fermi surface and the Berry curvature map carry `kspace` (the
reciprocal vectors and `k2K`, kept in project and result files), and an
engine test takes the brightest cells of a Fermi surface to reduced k and
diagonalizes there, finding a state within the broadening of its energy
(with `k2K` transposed the test fails, which was checked). The window has
the actions `pick` and `pick_to`, the menu (`pick_menu`, shown with
`popup()`), the right click in any mode and the Pick toggle (decision 47:
both), and Box and Lasso toggles on a result drawn flat on the atoms
(decision 54); Run > Run calculations at once is the general switch of
answer 48, kept in the settings (`run_at_once`, on by default), with the
action `run_at_once`; it runs a calculation after `add_calculation`,
`set_param` or `set_params` on it, unless an earlier result came back
(an undo, a value set back), and after the release of a slider on one of
its parameters, never during the drag. Tests: `tests/core/test_picks.py`,
the vocabulary in `tests/core/test_registry.py` and on every result of
`tests/engine/test_entries.py`, `tests/ui/test_picks.py`; the guide's
section "Picking from a plot", named by the bands, the LDOS and the Fermi
surface.

What the plan did not say, and was decided while building it (for the
maintainer to confirm or change):

- names: the plan names a new calculation after where it came from and
  keeps the Fermi level as a term "of that name", but calculations and
  terms had no name, so the Document gains one schema addition, an
  optional `name` on ops, terms and calculations, left out of the JSON when
  empty (documents without names are written byte for byte as before) and
  never in a key; `rename` takes them, `add_term` and `add_calculation`
  take `name`, the outliner shows it after the kind;
- run at once is off in a window that does not read the settings (the
  tests and `tools/drive.py`), as the theme is left alone there, so that
  nothing a driver adds starts a run it did not ask for; the program
  (`guiqula`, `--offscreen` too) reads it and starts with it on; a
  calculation that is not set up yet (a sweep that names no calculation,
  a Python calculation in an untrusted document) is not run at once, and
  a vertex dragged in the k-space tab re-runs the bands at once when the
  drag ends (a plain `set_param`, as a form edit is);
- the Fermi level adds to the shift the picked result saw: an energy is
  picked on a spectrum the previous Fermi-level term (if the result's
  snapshot had one) had moved already, so the new mu is that term's mu
  minus the energy, not minus the energy alone;
- a pick on a sweep sets its parameters as one undo step (a merged step,
  as a slider's drag) and runs the swept calculation there when Run at
  once is on;
- found and fixed on the way: the progress of a band structure counted
  `nk` points where pyqula walks one on a finite system (it stopped at 0.1)
  and `nk + 1` on its default three-dimensional path; it now counts the
  points walked.

Part 2, built 2026-09-28. The LDOS gains `k` (empty: the k-mesh, as before;
a k-point: `get_ldos(ks=[k])`, one diagonalization), and three calculations
join the registry, each with its engine case against a direct pyqula call
(exported and run by the script test), a cost, `guide=` and `pyqula=`:
`eigenstate` (Eigenstate: `htk.eigenvectors.get_eigenvectors` at `k`, the
state nearest `energy` or the one of index `band`, its weight per site by
`h.full2profile`, the energy on the colour bar), `site_dos` (DOS on sites:
`h.get_dos(operator=P)` with P the diagonal projector on the components of
the sites within `tol` of `positions`, sparse, found with
`core.nearest.nearest_site`, which the exported script defines; an engine
test checks that the projectors of all the sites add up to the whole DOS,
in Nambu too), and `qpi` (Quasiparticle interference: `h.get_qpi` at one
energy, `response` or `pm`, two-dimensional systems only, a map over q
whose click yields its energy, since q is not a k-point of the system).
The k-space tab picks the k-point under a click (Add points off) or a
right click, snapped as a vertex would be, and the Structure tab has
Calculate on selection next to Region from selection; the window's `pick`
and `pick_to` take `system` and `values` for both. Tests: the new cases
in `tests/engine/test_entries.py`, the eigenstate of a picked band point
at the band's energy, a click in the k-space tab and the selection's menu
in `tests/ui/test_picks.py`.

Decided while building part 2:

- a parameter that may be left empty, which is a mode of its own (the
  LDOS's `k`: over the k-mesh), gives two new-calculation targets, without
  it and with it, so a pick on the bands still offers the LDOS at that
  energy over the whole zone (the first example of the request) as well as
  at that k-point; an existing calculation that leaves it empty keeps it
  so when it is moved;
- the eigenstate's `k` is a plain vector, Γ by default, rather than an
  optional one (it has no mode without a k), and the entry is called
  Eigenstate (the menu read "new Eigenstate at k at E = ...");
- the DOS on sites is computed by exact diagonalization only (the Green's
  function and KPM modes of the DOS would need their own projector
  handling);
- a calculation's `helpers` now reach its exported script (they reached it
  from terms and ops only), which the DOS on sites needs.

Part 3, built 2026-09-28: the markers. A value a pick set stays drawn on
the plot it was picked on, as a slider with `on` (the calculation whose
view draws it), `axis` (the axis of that plot that carries the parameter:
x, y, "xy" for a k-point of a map, "sites") and `quantity`: a dashed line
at an energy or a swept value, a vertical line at the point of a k-path
where a picked k-point is, circles at a k-point of a map and at all its
images inside the map (the Fermi surface's mesh spans more than one zone,
and the image nearest the centre was not where the click was), rings
around picked sites. `pick_to` adds the markers of what it set; the
`slider` action takes `on` (its range, when not given, is the drawn range
of that axis); `set_slider` takes a k-point for a marker of one; the
view reports a drag (`marker_moved`) and the window turns the position
into the value (`move_marker`: the number on the axis, or the k-point
under it, read as a pick reads it), one undo step per drag, with Run at
once after the release; every document change redraws the markers
without redrawing the plots, so a form, a slider, a command or an undo
moves them and the zoom stays. The Sliders dock lists the markers ("c3
energy on c1"; a marker of a k-point or of sites has its value and no
range), they are kept in the project's `ui` block and pruned with their
entry or their calculation. Tests (`tests/ui/test_picks.py`): a line on
the bands after a pick, dragged in one undo step, moved by a command and
by an undo, kept in the view state, pruned with its calculation, and the
LDOS following the drag with the automatic re-run on; a circle on a Fermi
surface dragged to another cell, the eigenstate's k-point following it.

Phase 7 report (2026-09-28). Built as planned in its three parts, with
the answers to decisions 46 to 54; the whole suite passes (1057 tests, the
wheel build included). `tests/ui/test_startup.py` failed in two of the
runs along the way, at 2.04 and 2.05 s against its 2.0 s budget, and the
start before phase 7 is as slow on this machine (2.0 to 2.4 s for both,
measured side by side), so that is the load, not the phase. What each part
decided that the plan did not say is listed with the part; the ones worth
your answer:

55. names: the one schema addition, an optional `name` on ops, terms and
    calculations (left out of the JSON when empty, never in a key), which
    the naming of what a pick adds and the "Fermi level" term need;
56. Run at once is off in a window that does not read the settings (the
    tests, `tools/drive.py`), on in the program; a k-path vertex dragged in
    the k-space tab re-runs the bands at once when the drag ends;
57. the Fermi-level target adds to the shift the picked result saw (the
    energy is read on a spectrum the previous Fermi-level term had moved),
    and turns the term on again if it was off;
58. an optional quantity (the LDOS's k-point) gives two targets, without
    and with it; an LDOS over the mesh stays so when moved;
59. the eigenstate's k-point is a plain vector (Γ by default), and the
    entry is called Eigenstate;
60. the DOS on sites is by exact diagonalization only;
61. a k-point marker on a map is drawn at every image of the k-point
    inside the map;
62. a marker of sites (rings) is drawn and listed, but not dragged.

Maintainer's answers to the phase-7 report (2026-09-28, asked one by one,
the three that change behaviour): 55, the optional `name` stays in the
Document; 56, Run at once stays off in the tests and drivers and on in the
program; 57, the Fermi-level target keeps adding to the shift the picked
result saw. 58 to 62 were not asked and stand as built.

**After phase 7: the 3D drawing with pyvista (asked and built 2026-09-29).**
The maintainer asked that 3D drawings (magnetization, structures) can
optionally be made with pyvista, turned and zoomed as when using pyvista
normally. Built: `ui/pyvista_view.py`, a scene (`draw_scene`, the overlays
of `draw_structure_3d` one by one: sites by sublattice or by value with a
colour bar, bonds or the Hamiltonian view's hoppings coloured by phase,
the faded neighbouring cells, the unit cell, arrows, the region, the
removed positions, the selection) and its widget (`SceneView`: Reset view,
Save image, a hint of the gestures); View > 3D drawing (matplotlib or
pyvista), the window action `renderer_3d` (in `remote/api.py`'s
`WINDOW_ACTIONS` too) and the setting of the same name; the structure
canvas and every result view on the atoms swap their matplotlib canvas for
the scene when they draw in 3D. Asked before building (one question): a
result on the atoms follows the canvas's 3D box, so "3d" draws the
magnetization of a flat lattice in 3D as well, and "auto" keeps it flat
with its picks (the maintainer's answer, the recommended option). Found
while building: a widget on a QToolBar is shown and hidden by its action,
Qt ignores the widget's own setVisible, so the Pick, Box and Lasso buttons
of a result drawn in 3D were never hidden (they only looked so when the
toolbar overflowed); `PlotView` now hides them through their actions.
Verified offscreen (tests/ui/test_pyvista_view.py, screenshots), with
VTK's events sent without a mouse; not verified: the widget on the Wayland
desktop with a real mouse, and a HiDPI screen (the image is rendered at
the device pixel ratio, which is 1 offscreen). Decisions taken while
building, for the maintainer to confirm:

63. pyvista renders off-screen and the widget paints its image, the mouse
    going to a VTK interactor with the trackball camera style (pyvista's
    default), not pyvistaqt's QtInteractor, which embeds a VTK window in
    Qt: VTK's QVTKRenderWindowInteractor crashed on the offscreen platform
    the tests, drive.py and the remote screenshots use (verified), and in
    its default form it draws into an X window, which Qt on a Wayland
    desktop does not have (not tried here); about 20 ms a frame for a
    diamond cell here; pyvistaqt is not a dependency;
64. the choice is a setting (matplotlib by default), not part of the
    Document, since it depends on what is installed on the machine; the
    tests and drivers start with matplotlib;
65. Export (io/bundle.py) and the remote `plot` keep matplotlib's figure,
    in the same projection (mplot3d in 3D); Save image in the scene writes
    the view as drawn;
66. the camera stays when the same system (the same result view) is drawn
    again, after an edit, a new result or a change of theme, and fits the
    sites again from the same angle when they changed; Reset view is the
    oblique view fitted to the sites and the unit cell, not to the faded
    cells around them;
67. above 4000 sites they are points drawn as spheres, not sphere glyphs;
    the hoppings of the Hamiltonian view take six line widths by amplitude,
    since VTK draws one width per actor; atoms under arrows are drawn
    smaller, so that an arrow centred on its site shows;
68. no readout, picks or markers in the scene, as in mplot3d; the canvas
    keys (Home, Ctrl+A, Del) work on the scene too;
69. a pyvista that cannot draw leaves the drawing to mplot3d and the
    caption says why; one that cannot start (no OpenGL) is not tried again
    in the session, and the menu entry is greyed out when pyvista is not
    installed;
70. the `[3d]` extra is `pyvista>=0.48`, the version tested.

**The look (2026-09-29).** The maintainer asked for a better-looking
interface, naming two things, the text of the plots (bigger axis labels
and ticks, better centred) and the check boxes (a box to see that one can
tick), and answered four pick lists on the rest: what "centred" meant
(the axes box in the middle of its panel, the title over the panel, the
labels on their axes, the k-space drawing filling its panel), how the
plot text size is set (a View menu switch, kept like the theme), and
which of the other things noticed to do now (all of them: the structure
canvas's small ticks, pyvista's title, the forms' enabled row, a slightly
larger UI font, the outliner's headers, the menu buttons' arrows, the
colour bar labels, the check marks of the menus). Built in `ui/theme.py`
(the sizes in `mpl_rc`, `CheckStyle`, `centre` and `Centring`, the font)
and stripped from the drawing modules, with View > Plot text, the window
action `plot_text` (in `remote/api.py`'s `WINDOW_ACTIONS`) and the
setting of the same name; verified offscreen (tests/ui/test_polish.py,
screenshots in both themes, the README's images made again). Decisions
taken while building, for the maintainer to confirm:

71. the plot text size is a setting with three sizes, small, normal and
    large (9, 11 and 14 points as matplotlib's `font.size`, at the
    figures' 100 dpi), normal bigger than before (matplotlib's 10); the
    axis labels are a fifth larger than the base, the ticks and the title
    at the base, a legend, a marker's label and a k-point's name smaller,
    through matplotlib's relative sizes, so one number scales every
    drawing: the result plots, the structure canvas (whose ticks were 8
    points and its 3D labels 7), the k-space tab, the exported figures,
    and pyvista's title and colour bar (in pixels, times the screen's
    pixel ratio);
72. the check boxes are drawn by a proxy style over Fusion
    (`theme.CheckStyle`), since Fusion derives their border from the
    window colour, faint in the light theme and invisible in the dark one
    and out of the palette's reach: a box with a border of its own colour
    (`CHECK_BORDER`), filled with the highlight colour and a white mark
    when checked, a bar when partial, greyed when disabled; Fusion routes
    the item views' boxes (the outliner) and the checkable menu entries
    through the same primitive, so they get the same box;
73. the axes box of every figure sits in the middle of its panel: after
    each drawing the margins are measured and the constrained-layout rect
    moved so that what the y label and the ticks take on one side and a
    colour bar on the other balance (`theme.centre`; `Centring` does it
    after every draw of a canvas, so a resize keeps it, with at most three
    extra drawings, and `settle()` draws at once where the transforms are
    read right after); the title, centred on the axes, is then centred on
    the panel too; the exported figure is centred the same way; the
    structure canvas moved from `tight_layout` to constrained layout for
    this;
74. a colour bar label of six characters or fewer (sz, LDOS, DOS, chern)
    is upright above the bar at the axis labels' size; a longer one runs
    along the bar; a horizontal bar keeps its label below;
75. the widgets' font is the desktop's, raised to 10 points when it is
    smaller (Qt's default is 9); the forms' titles went from 11 to 12;
76. the k-space zone is drawn in an axes box that fills the panel
    (`adjustable="datalim"`, the limits widened to the aspect) with an 8
    percent margin instead of 15, rather than a square box in the middle
    of a wide panel;
77. pyvista's title is a text of fixed size centred at the top edge (a
    corner annotation scales with the window and was drawn at twice
    matplotlib's size);
78. the forms' enabled box is a row labelled "enabled" like the
    parameters; the outliner's headers are "Entry" and "Status"; a menu
    button (New system, Add op, Select, Overlay) shows its drop-down arrow
    centred at the right with room for it (a stylesheet rule on the
    menu-indicator subcontrol; Fusion drew a small one under the text's
    corner);
79. the axis labels sit 3 points from the ticks (matplotlib's 4).

**Moving in space (asked and built 2026-09-29).** The maintainer asked that
the 3D plots have the same controls as Blender has to move in space, and the
2D geometry plots the same controls as Inkscape. Asked before building (one
pick list): what draws in 3D by default, since the Blender controls need
pyvista's scene; the maintainer picked pyvista when it is installed. Built:
`ui/navigation.py` (the arithmetic without Qt, VTK or matplotlib: the
turntable camera `Turntable`, the limits of a flat view, the zoom history),
`ui/canvas_navigation.py` (Inkscape's controls on a matplotlib canvas:
`CanvasNavigation`, `bind_keys`), the camera and keys of
`ui/pyvista_view.py` rewritten (`SceneCanvas` moves the camera itself;
`SceneView` gets the View menu and `set_view`), the window action `view_3d`
(in `remote/api.py`'s `WINDOW_ACTIONS` too), the shortcut table's contexts
"2D canvas" and "3D canvas", "Moving in space" in the user guide. Verified
offscreen (tests/ui/test_navigation.py, tests/ui/test_pyvista_view.py, the
window's keys with QTest, screenshots); not verified: a real middle button
and wheel on the Wayland desktop, a touchpad, a numpad with NumLock off, and
the typed "+", "~" and "`" on a real keyboard layout (QTest sends the key
codes, not the platform's mapping). The manuals of both programs could not
be fetched: Blender's keymap source confirmed the numpad views, the orbit
and pan steps, numpad 5, Home and numpad period, and the rest of both
mappings (Inkscape's keys and steps, the sign and speed of Blender's drags,
alt and the left button) is from memory, so a key that differs from the
program is a one-line change in `ui/navigation.py` or `ui/pyvista_view.py`.
Decisions taken while building, for the maintainer to confirm:

80. the pyvista scene is moved as Blender's viewport, replacing 63's
    trackball camera: the camera is `navigation.Turntable` (a target, a
    distance, an azimuth about z and an elevation, so z stays up), the widget
    applies the mouse and the keys to it and sets the pyvista camera; no VTK
    interactor style is involved (the interactor only sizes the render
    window). Middle drag orbits (0.007 radians a pixel, upside down past a
    pole with the horizontal drag reversed, as Blender's turntable), shift
    pans, ctrl zooms (dragging up zooms in, the distance following the
    pointer's distance from the top edge); the wheel zooms by 1.2 a notch,
    ctrl and shift with the wheel pan by 32 pixels; the numpad gives the
    front, right and top views (ctrl: the opposite side), steps the orbit
    by 15 degrees (ctrl: the pan), toggles the projection (5), half a turn
    (9), zooms (+, -), frames the selected sites (.); Home frames everything;
81. an axis view is orthographic and turning away from it returns to
    perspective, as Blender's auto perspective; toggling with 5 is a choice
    that turning does not undo. The view is named as Blender names it (User
    Perspective, Top Orthographic) on the View button of the scene bar,
    which is also a menu of the views, the projection and the framing, for
    a keyboard without a numpad. Top-row digits do not emulate the numpad
    (Blender's option is off by default), so 3 and 4 keep Inkscape's
    meaning on both kinds of drawing;
82. the plain left button does nothing in the scene (Blender keeps it for
    selecting, and the scene has no selection); alt and the left button
    emulate the middle button always, alt+shift the pan and alt+ctrl the
    zoom (Blender's emulation of a three button mouse, which is a preference
    there); on a Linux desktop that takes alt and a drag to move windows
    this needs the desktop setting changed, and the user guide says so;
83. not built of Blender's navigation: roll (shift and numpad 4 or 6), the
    navigation gizmo, zooming towards the pointer, the fly and walk modes,
    the camera view (numpad 0), the trackball orbit;
84. the flat drawings move as Inkscape's canvas, on the structure canvas
    and the results drawn flat on the atoms only (not the bands, the
    densities of states, the k-space tab, nor a curve against x, which keep
    matplotlib's toolbar): the wheel scrolls 40 pixels a notch, shift and
    the wheel scrolls sideways, ctrl and the wheel zooms about the pointer
    by the square root of two a notch, the middle button drags (a click zooms
    in, with shift out), Space turns the left button into the same drag
    (the box and lasso step aside), ctrl and the arrows scroll, + or = and -
    zoom, 3 zooms to the selected sites (everything when none), 4 and Home
    show the whole drawing, the backtick and the shifted backtick (or ~) go
    to the previous and the next zoom; a zoom, not a scroll or a drag, is
    put on the history. The plain wheel no longer zooms there (it did until
    now); the toolbar's Pan and Zoom modes are kept, and the mouse belongs to
    them while one is on. Not built of Inkscape's: 1:1, the page keys (there
    is no page), the rotation of the canvas, autoscroll at the edges, the
    zoom tool;
85. the keys are in the table under two contexts the widgets handle
    themselves, "2D canvas" and "3D canvas", bound as QShortcuts on the
    canvas (`bind_keys`), not as the window's actions; + - 3 4 and ctrl and
    the arrows work in the scene too (zoom, frame the selected sites, frame
    everything, pan); the numpad keys of the scene accept the shortcut
    override, so that numpad 3 is the right view and not the digit's zoom;
86. pyvista is the default in the program's window when it is installed
    (`renderer_3d` in the settings, replacing 64's matplotlib), and matplotlib when it is not and the
    user never chose it, without a message; a user who chose pyvista and
    lost it is told, as before. Tests and drivers still start with
    matplotlib. So that "never chose it" can be told, the settings file now
    holds only what was set (it wrote every default before, which would have
    frozen a default for good in a file written earlier), and
    `settings.chosen(name)` says whether a setting is in it;
87. the window action `view_3d` (name: front, back, right, left, top,
    bottom, perspective, orthographic, flip, all, selected, reset; and a
    calculation for a result view instead of the canvas) moves the scene for
    drivers, and refuses when nothing is drawn with pyvista there;
88. a detached result is a plain top-level window (`ResultWindow`, in
    `ui/plots.py`) and not a floating dock (2026-09-29, after the maintainer could
    not move a detached plot). On a Wayland desktop (GNOME, Qt 6.11 here) a
    floating `QDockWidget` is a frameless tool window with frame margins of
    zero, which draws its own title bar and moves itself by asking for a new
    position, and a compositor does not let a client place its windows; a plain
    window gets the decoration of the desktop (Qt's client-side one on Wayland,
    the window manager's elsewhere, margins of 11, 49, 11 and 11 here), which
    asks the compositor for the move. Closing the window hides it and selecting
    the calculation shows it again, as the dock did, and Attach puts the view back
    in its tab. The other docks (outliner, properties, jobs, log, console, help)
    are still `QDockWidget`s, so floating one of them has the same limit on
    Wayland; that is left as it is;
89. the k axis of the bands and of the spectral function names the high-symmetry
    points of pyqula's default path when no k-path is given (asked 2026-09-29,
    built 2026-09-30, after the maintainer saw that the bands of a preset carried
    the index of the point, "k-path point", and no names: all nine presets use the
    default path, so names came only with a path typed in the form). `_path` now
    returns the points of the default path as well (`kpaths.default_path`), and
    `kpaths.default_ticks` finds every point of `special_points`, with its images
    along the periodic directions, on the polyline of those points, at its
    fractional index (index / number of points for the spectral function). The
    names are the ones of `label2k` for Γ, K and K', so the first corner of the
    default path on the honeycomb, triangular and kagome lattices is K', where
    pyqula's guide and `BANDLINES.OUT` call it K (the maintainer chose the
    `label2k` naming). M is named by its kind, which the maintainer also chose:
    the M, M1, M2 and M3 points of a hexagonal zone are all M, and elsewhere
    (1/2, 0) is X, (0, 1/2) is Y and (1/2, 1/2) is M, giving Γ K' M K Γ, Γ M Γ
    (square), Γ X Γ (one dimension) and Γ X M Γ R (three dimensions), the last
    as pyqula's own labels of that path. A typed label still resolves as pyqula
    does, so `M` typed in a k-path is (1/2, 0), which is not the M the default
    path crosses on the honeycomb (there it is `M3`), and on a honeycomb without
    C3 the two are different points. The axis is labelled k, as with a typed
    path. In two dimensions pyqula's default path stores each point after the
    step, `bm * (i + 1) / nk`, so its opening Γ is not on it. The maintainer
    picked that the path start on Γ, which needed a change in pyqula, and then
    asked that pyqula not be edited from here; guiqula therefore walks the path
    itself: every point pyqula gives, unchanged, with Γ put first, so a
    two-dimensional default path has nk + 1 points and its arrays are those of a
    direct pyqula call given that path (`kpath=`). The one and three
    dimensional paths, which start on Γ, are passed as pyqula makes them
    (the same points as a bare call), and a finite system has no k, no ticks
    and keeps the index of the point on its axis. The exported script writes the
    path (`ks`, the Γ added when the dimensionality is 2) and passes `kpath=ks`,
    and the k-space tab draws the same points as its dashed default path. A result
    saved in a project before this keeps its old axis until the calculation is run
    again (its key hashes the kind, the parameters and the system, not the code). Not changed: the names of the coordinate
    vertices of a typed path still follow the k-space tab (on a square zone
    (1/2, 0) reads M and the corner (1/2, 1/2) reads M3, on a one-dimensional
    one the edge reads M), and a vertex typed as 0.333 is not K' but its
    coordinates, since the match is to 1e-6.

Maintainer's answers after building (2026-09-29, asked one by one, the
three that change behaviour): 82, alt and the left button emulate the
middle button always (not a switch, not off); 84, Space and the left
button as a pan is kept (it is not Inkscape's own default, whose Space
toggles to the selector), and the Inkscape controls stay on the structure
canvas and the results drawn on the atoms, not on the k-space, bands or
density of states tabs. 80, 81, 83, 85, 86 and 87 were not asked and stand
as built.

**Phase 8, the interface (planned 2026-10-03; built 2026-10-03 and
2026-10-04 on branch phase8, reported at the end of this section).** The
maintainer asked for a more user friendly interface, substantial
redesigns being acceptable, and for a plan rather than the work, to be
executed later, possibly by a workflow of several agents. This plan was
made by driving the window offscreen with `tools/drive.py` at 1200x800,
1400x900 and 1600x1000 on the shipped presets and reading the screenshots,
and by reading `ui/`. It is written so that one agent can build one
package of it without those screenshots: each package says what the user
gains, what is built (widget names, where it sits, what a click does, what
an empty state says), which files it owns, which tests it adapts by name,
which it adds, how it is accepted, and what it depends on. The window
looks as PLAN.md section 4 drew it, and the redesign keeps that frame (one
window, three workspaces, outliner, viewport, properties) and changes what
sits in it; section 4's mockup is replaced by the one below when the last
package lands (it was: section 4 now draws the window as built, and the
drawing below stays as the plan made it).

*What the screenshots show.* The problems, each with the condition that
shows it, so that the maintainer can reproduce it and the agent can see
the fix:

1. The program opens on a blank canvas with the line "No system yet: add
   one with New system (Geometry toolbar)" and nothing else (the empty
   window at 1200x800); the presets are behind File > Presets gallery
   (Ctrl+Shift+O), a plain list without pictures. A student's first minute
   is spent finding where to begin.
2. Adding a term needs the Hamiltonian workspace tab, since the Add term
   button lives in its toolbar row, and the tabs do not follow the
   selection: after New system, Add term and Add calculation through the
   window the workspace is still Geometry while the result tab of c1 is
   shown (the fresh document at 1400x900, `window.new_system`,
   `add_term`, `add_calculation`). Selecting a term in the outliner leaves
   the Geometry toolbar in place.
3. The Geometry toolbar row holds twelve text buttons (New system, New
   classical system, Add op, a search box, Add region, Pick, Box, Lasso,
   Select, Region from selection, Calculate on selection, Remove selected),
   of which only the first four add anything; the selection tools act on
   the canvas but sit a row above it.
4. Run is a small button at the top right of the first toolbar row, next
   to a "Calculation" combo that is a third place to choose a calculation
   (the outliner and the result tabs are the other two). A stale result
   says "(stale)" in its tab and has no Run again on the plot; a running one
   shows its progress in the Jobs dock only.
5. Help is a tab behind Properties, so F1 on a term hides the form it
   explains (`honeycomb_zeeman_rashba`, t1 selected, F1, 1400x900).
6. At 1200x800 the right column gives Properties 270 px: the three
   components of the Zeeman field are cut off and need a scroll, while
   Jobs below keeps 180 px to show one row (`honeycomb_zeeman_rashba`, t1
   selected). The Log takes 130 to 200 px of the bottom to show "j2 c1
   done"; the Console is a tab behind it; the Sliders are a tab behind Jobs.
7. The canvas bar is matplotlib's navigation toolbar (home, back, forward,
   pan, zoom, "configure subplots", "edit axis, curve and image
   parameters", save) followed by guiqula's Show, 3D and Paint controls;
   on a result tab the same eight buttons are followed by Export, Save
   data, Detach, Overlay, Pick, Box and Lasso. At 1200x800 both overflow
   into a "»" chevron. Subplots and Customize are matplotlib's developer
   tools and do nothing useful here.
8. The outliner's Status column is clipped at its default width:
   "quantu", "base la", "n [2, 2,", "→ spinf" (every preset at 1200x800
   and 1400x900), and it mixes the Hilbert space after a term, an op's
   parameters, a result's status and the lock marks.
9. The k-space tab is there for a finite system, which has no Brillouin
   zone (`graphene_island`, 0D).
10. A slider is made in the Sliders dock by typing an entry id, a
    parameter name and a range ("t1, op2, c3, s1/..."); nothing in a
    parameter's form offers one (`honeycomb_hubbard`, 1400x900).
11. The f(r) button opens a panel whose kind box and long help text repeat
    for each of the three components of a vector Field; the kind of a
    Field is not visible until the panel is opened.
12. The system form says "spinful (requested)", "Nambu (requested)",
    "neighbour hoppings", "sparse": the engine's words, not the physics'.
13. No control has an icon; every dock carries Qt's float and close
    buttons, and floating does not work on Wayland (decision 88).

A doubled dock tab bar seen in a screenshot of the right column at
1200x800 vanished once the layout had settled (ten `processEvents` and
`qWait(100)` rounds before the grab, as `tools/readme_images.py` does): an
artefact of the grab, not a bug, and an agent taking screenshots should
let the layout settle the same way.

*What does not change.* The Document schema and its `ui` block, the
command API and the undo steps, the registry declarations and their
groups, the engine, the worker and its protocol, the remote protocol and
`RemoteAPI`'s methods, the result files, the presets' contents, the
session. The redesign is of `ui/` (plus `io/settings.py` for two new
settings, `resources/` for the icons and thumbnails, `tools/` for the
thumbnail script, and the documentation).

*Constraints every package keeps.*

- A renamed or removed widget `objectName` breaks `tests/`, `tools/drive.py
  --widget`, the remote `screenshot` and `widgets` methods and the example
  commands of CLAUDE.md: each package lists its renames, and keeps the old
  name where it can.
- A new window action joins `WINDOW_ACTIONS` in `ui/mainwindow.py` and in
  `remote/api.py` (`test_window_actions_are_listed` checks), and `tools/
  drive.py`'s help names it.
- The UI process never imports pyqula, scipy, jax or numba
  (`tests/ui/test_startup.py`, with its 2 s budget): the start page's
  pictures are PNG files made by a tool script, never computed in the
  window.
- `test_every_toolbar_control_and_palette_entry_has_a_tooltip` applies to
  every new control; the tooltips name the shortcut through
  `shortcuts.text`.
- A new key goes in `ui/shortcuts.py`, the one table, whose copy in the
  user guide is tested.
- Floating docks cannot be moved on Wayland (88): nothing depends on
  floating one.
- The Inkscape and Blender controls of the drawings (80 to 87) stay as
  they are; `CanvasNavigation` and the tests that read the matplotlib
  toolbar's mode (`test_pan_or_zoom_takes_the_clicks_until_a_tool_is_chosen`,
  `test_pan_or_zoom_unchecks_the_selection_tools`) keep a
  `NavigationToolbar2QT` instance to read, hidden, whose `pan()` and
  `zoom()` our own buttons call.
- Where a package changes a decision of 63 to 89 it names it: P3 revisits
  84's "the Pan and Zoom buttons of the toolbar are still there" (they
  are, as guiqula's own buttons) and the k-space tab that was always there
  since phase 4; P5 revisits 88's "the other docks are still QDockWidgets"
  (they are, without the float button).
- The test suite passes after each package (`python -m pytest -m "not
  slow"`, then the whole suite before a merge); `tools/readme_images.py`
  is rerun by the last package only.
- Nothing is committed or pushed without the maintainer; the packages
  land on branches, merged in the order below.

*The window after the redesign* (1200x800; the plan's drawing, kept as
planned, while section 4 carries the window as built):

```
+------------------------------------------------------------------------------------------+
| File Edit View Run Help   [Geometry] [Hamiltonian] [Calculate]      New system v   Add v  |
|                                                 > Run c1 . bands v   Cancel   [ ] Follow  |
+---------------------------+-------------------------------------------+------------------+
| OUTLINER                  | Structure | k-space | c1 bands x          | PROPERTIES       |
| v s1 graphene       2D    | fit pan zoom | pick box lasso Select v    | Zeeman field   ? |
|   v Geometry           +  |  Region.. Calculate.. Remove | Show v 3D  | [x] enabled      |
|     Honeycomb lattice     |                                 save image| sum_i m(r_i).s_i |
|     [x] op1 Supercell 2x2 |             . . . . . .                   | acts everywhere, |
|     Regions            +  |           . . [. . .] . .                 |  restrict to..   |
|   v Hamiltonian        +  |             . . . . . .                   | field x [0   ] v |
|     [x] t1 Zeeman  spinful|                                           |       y [0   ] v |
|     [x] t2 Rashba  spinful|                                           |       z [0.1 ] v |
|     [ ] Mean field    off |                                           | spinful after it |
| v Calculations         +  |                                           +------------------+
|     c1 Band structure done| s1 . 2D . 8 sites . spinful               | Help|Sliders|Jobs|
|     c2 Density of st. stale                                           | (t1's help)      |
+---------------------------+-------------------------------------------+------------------+
| s1 . 2D . 8 sites . spinful . dimension 16 . c1: under a second         j2 c1 done   Log |
+------------------------------------------------------------------------------------------+
```

When the document has no system the central area shows the start page
instead of the viewport: the lattices as pictures, the presets as pictures,
the recent files.

*The packages.* P1 to P7 and P9 are needed (must); P8 is polish (nice).
They are listed by what they are worth to the user; the order in which
they are built is under "Order" below.

**P1, the start page (must).** The program opens on something to do: a
preset to open, a lattice to start from, a file to reopen, instead of a
blank canvas. `ui/start.py` holds `StartPage(QWidget)`, object name
`startPage`, a scrolled page of three bands. "Start from a lattice" lists
the registry's lattices by group (0D, 1D, 2D, 3D, Layered) as cards
(`startLattice_<kind>`): a picture of the lattice, 160 by 120 px, and its
label; a click runs the window's `new_system(kind)`. Three cards close the
band for the classical systems (`startClassical_<kind>`, "Classical
spins", "Lattice gas", "Ising model", running `new_classical_system`).
"Open an example" lists the presets as cards (`startPreset_<name>`): a
picture, the title and the first sentence of the notes, the teaching ones
marked "teaching, some parameters locked"; a click runs `open_document`,
which asks about unsaved changes as it does today. "Recent files" lists
the settings' recent files (`startRecent_<n>`) and an "Open a project..."
button (`startOpenButton`). A filter box at the top (`startSearch`)
narrows every band as the user types. A footer line says what comes next:
"Then add terms in the Hamiltonian workspace and a calculation in
Calculate; Run (F5) computes it, F1 explains any entry", with a link that
opens guiqula's guide in the Help panel. The central widget becomes a
`QStackedWidget` (`centralStack`) holding the start page and the
viewport; `_document_changed` shows the page when the document has no
system and the viewport otherwise, File > New shows it again, and the
window without a session shows it too. The pictures are PNG files in
`src/guiqula/resources/thumbnails/lattices/<kind>.png` and
`.../presets/<name>.png`, made by `tools/make_thumbnails.py`, which drives
one offscreen window in the light theme through `tools/drive.py`'s
machinery (`new_system` for each lattice and a grab of `structureCanvas`;
each preset opened, its selected calculation run, its plot or its
structure grabbed; a geometry that is not flat drawn by matplotlib in the
3D projection from mplot3d's default angle, so the set is consistent
whatever is installed), scaled with Pillow, 10 to 20 kB each, added to the
package data; the page loads them as `QPixmap` when it is first shown, so
the start budget holds. The page needs every preset's title and first
sentence at start, which today means loading each preset's JSON
(`gallery.preset_notes`); if `test_startup` says that does not fit the
budget, the tool also writes `resources/thumbnails/presets.json`, an index
of titles and descriptions, which the page reads instead. The gallery dialog (`ui/gallery.py`, Ctrl+Shift+O)
is rebuilt from the same preset cards so it gets the pictures, and the
File > Open preset submenu stays. Files owned: `ui/start.py` (new),
`ui/gallery.py`, `tools/make_thumbnails.py` (new), `resources/thumbnails/`,
`pyproject.toml` and `MANIFEST.in` (package data), and in
`ui/mainwindow.py` the central stack of the constructor, `_document_changed`
and `new_document` only. Renames: none. Tests to adapt:
`test_presets_gallery`, `test_window_screenshot_without_session`,
`test_main_window_builds_without_workers`, `test_startup` (the budget with
the page), `test_packaging` (the data files in the wheel). Tests to add
(`tests/ui/test_start.py`): every lattice and every preset has a picture
(a preset added without one fails here); the page shows at start and
goes when a system is added, and comes back after File > New; a lattice
card adds a system, a preset card opens it, the filter narrows the cards.
Acceptance: `python tools/drive.py --no-session --size 1200x800 --shot
start.png` (every band visible, no horizontal scroll), the same at
1600x1000 with `--do '{"do": "theme", "name": "dark"}'`, and
`python tools/drive.py --no-warm --python
"window.start_page.card('preset', 'haldane_chern').click()" --shot
opened.png` showing the preset. Depends on nothing; its touch of
`ui/mainwindow.py` is three places.

**P2, adding things where they appear, and workspaces that follow
(must).** An op, a term or a calculation is added from the place where it
will appear, with one searchable menu, and the workspace tabs follow what
is selected. `ui/palette.py` (new) holds `PaletteMenu(QMenu)`: a search
line at its top (`paletteSearch`, a `QWidgetAction`), then the entries of
one family by group with the formula tooltips as today (the actions keep
their names `addOp_<kind>`, `addTerm_<kind>`, `addCalc_<kind>`,
`newSystem_<kind>`); typing filters the entries with `search_entries`
and Enter adds the best match, so the three search boxes of the toolbars
(`opSearch`, `termSearch`, `calculationSearch`) go. The outliner's section
rows carry a "+" tool button at their right, an item widget in the status
column (`outlinerAdd_<system>_geometry`, `_regions`, `_hamiltonian` or
`_model`, and `outlinerAdd_calculations`), opening the `PaletteMenu` of
that family for that system; the Regions menu lists "Region by
expression" and "Region from selection" (enabled with a selection); the
Hamiltonian menu ends with "Mean field (interactions)", which enables the
mean-field block and selects its row. The first toolbar row becomes: the
workspace tabs, "New system" (`newSystemButton`, a `PaletteMenu` of the
lattices with the three classical systems as a last section,
`newClassical_<kind>` kept; `newClassicalButton` goes), "Add"
(`addButton`, the `PaletteMenu` of the current workspace's family: ops,
terms, calculations; Ctrl+F opens it, `focus_search` becomes that), and
the run controls built as P4 designs them. The second toolbar row
(`geometryToolbar`, `hamiltonianToolbar`, `calculateToolbar`, with
`addOpButton`, `addTermButton`, `addCalculationButton`, `addRegionButton`,
`meanfieldButton`) goes, except that `geometryToolbar` stays as a reduced
row holding the selection controls only (`tool_pick`, `tool_box`,
`tool_lasso`, `selectSitesButton`, `regionFromSelectionButton`,
`calculateOnSelectionButton`, `removeSelectedButton`), shown in every
workspace, so that the selection tests pass on P2 alone; P3 removes that
remnant when it builds the canvas bar. `select()` sets the workspace of what is
selected (a system, the base lattice, an op, a region: geometry; a term,
the mean field, a model: hamiltonian; a calculation: calculate), and since
adding an entry selects it, an add switches too; `set_workspace` keeps
its meaning (the canvas view, the family of Add) and Ctrl+1, Ctrl+2,
Ctrl+3 stay; `apply_view_state` applies the saved `ui` block's
`workspace` after its `selected`, so that a restored workspace is not
overwritten by the selection. Files owned: `ui/palette.py` (new), `ui/outliner.py` (the
"+" buttons and their signal), and in `ui/mainwindow.py` `_build_toolbars`,
`_menu_button`, `_fill_menu`, `_search_box`, `add_searched`, `_offered`,
`_update_palettes`, `set_workspace`, `select`, `focus_search`, `add_region`.
Renames: the ones named above. Tests to adapt:
`test_workspaces_switch_palettes`, `test_palettes_add_and_select`,
`test_term_search`, `test_every_toolbar_control_and_palette_entry_has_a_tooltip`
(it reads `window.term_button.menu()`: it reads the Hamiltonian
`PaletteMenu` instead), `test_canvas_keys_and_the_shortcuts_dialog`,
`test_select_action_drives_properties_and_viewport`,
`test_formulas_in_the_palettes_follow_the_theme`, `test_meanfield_block`,
`test_a_classical_system_in_the_window`, `test_project_remembers_the_view`,
and `tests/test_drive.py` where it clicks a palette. Tests to add (`tests/ui/test_palette.py`): the menu
lists by group and filters, Enter adds the best match, the "+" of a
section adds to its own system in a document with two, selecting a term
switches the workspace to Hamiltonian and a calculation to Calculate, Ctrl+F
opens the Add menu of the workspace. Acceptance: `python tools/drive.py
honeycomb_zeeman_rashba --size 1200x800 --do '{"do": "select", "entry":
"t1"}' --shot t1.png` reports `"workspace": "hamiltonian"` and shows one
toolbar row; `--python "window.outliner.add_button('s1/hamiltonian').
click()"` with a shot of the open menu. Depends on nothing; P3, P4 and P7
follow it.

**P3, the canvas and plot bars (must).** A drawing's bar holds what the
drawing needs, fits at 1200 px, and the selection tools sit on the canvas
they act on; a stale plot says so and offers Run again on the spot, a
running one shows its progress and Cancel. `ui/canvasbar.py` (new) holds
`CanvasBar(QToolBar)`, built over a `NavigationToolbar2QT` that is
created, hidden and kept as `canvas.toolbar` (so `CanvasNavigation`, the
mode checks and the tests that read `toolbar.mode` keep working): Fit
(home), Pan and Zoom (checkable, calling the hidden toolbar's `pan()` and
`zoom()`, unchecked by the navigation as today) and Save image (its
`save_figure`); the Back, Forward, Subplots and Customize buttons are not
offered. The structure bar (`structureBar`): Fit, Pan, Zoom, a separator,
Pick, Box, Lasso and Select (the widgets of P2's reduced geometry
toolbar, names kept, that toolbar removed), Region from selection,
Calculate on selection, Remove selected (enabled with a selection, as
today), a separator, Show (`canvasView`),
3D (`view3dBox`), the Paint group when a Field is previewed, and Save
image at the end. The plot bar (`plotBar_<calc>`): Fit, Pan, Zoom, a
separator, Pick, Box, Lasso (`pickTool_<calc>` and the others, names
kept), a separator, Overlay, Export, Save data, Detach, Save image. The
k-space bar: Fit, Pan, Zoom, then "path of", Add points, Remove last,
Default path. The pyvista scene bar (`structureSceneReset`,
`structureSceneView`, `structureSceneSave`) keeps its three controls in
the same bar when the scene is shown. Above a plot's canvas a status row
(`plotStatus_<calc>`, hidden when the result is current) says "stale: the
model changed since this was computed" with a Run again button
(`plotRun_<calc>`, the window's `run_guarded` for that calculation),
shows a progress bar (`plotProgress_<calc>`) and Cancel
(`plotCancel_<calc>`) while its job runs, and "failed: <message>" after a
failure; the readout line stays. The k-space tab is hidden
(`setTabVisible`) while the selected system has no periodic direction and
shown again otherwise (`_refresh_kspace`). Files owned: `ui/canvasbar.py`
(new), `ui/structure.py`, `ui/plots.py`, `ui/kspace.py`, `ui/pyvista_view.py`
(its bar only), and in `ui/mainwindow.py` `_selection_changed`,
`_refresh_kspace`, `_job_changed` (feeding the status row) and
`_draw_result` (stale into the row). Renames: `structureToolbar` becomes
the hidden matplotlib toolbar's name and `structureBar` the visible one.
Tests to adapt: `test_pan_or_zoom_takes_the_clicks_until_a_tool_is_chosen`,
`test_pan_or_zoom_unchecks_the_selection_tools`, `test_box_and_lasso_tools`,
`test_selection_to_removal_and_region`, `test_selection_geometry`,
`test_result_tabs_readout_and_detach`, `test_the_window_draws_in_3d_with_pyvista`,
`test_the_view_menu_and_names`, `test_a_large_geometry_on_the_canvas`,
`test_hexagonal_zone`, `test_the_path_on_the_zone`,
`test_a_click_on_a_vertex_passes_through_it_again`,
`test_every_toolbar_control_and_palette_entry_has_a_tooltip`,
`test_undo_and_stale_marking`. Tests to add: the status row shows stale
and Run again recomputes; the row shows progress and Cancel stops the
job; `graphene_island` has no k-space tab and `honeycomb_zeeman_rashba`
has one; no bar overflows at 1200 px (the toolbar's extension button is
not visible). Acceptance: `python tools/drive.py graphene_island --size
1200x800 --run c1 --shot island.png` (two tabs, no chevron);
`python tools/drive.py honeycomb_zeeman_rashba --size 1200x800 --run c1
--python "session.do('set_param', entry='t1', name='m', value=[0, 0, 0.3])"
--widget plot_c1 --shot stale.png` showing the row. Depends on P2.

**P4, Run where the result is (must).** Run is one obvious control acting
on what the user looks at, and a calculation is chosen in one place. The
"Calculation" combo (`calculationBox`) goes; `selected_calculation()`
returns the calculation selected in the outliner, else the one whose
result tab is shown, else the first; the Run button (`runButton`) reads
"Run c1 · bands" (`_update_actions` renames it) and carries a menu arrow
(`runMenu`) listing the other calculations ("Run c2 · dos") and "Run every
stale result" (`runStaleAction`); `cancelButton` stays next to it and is
enabled while a job of the selected calculation runs; the cost guard is
unchanged; F5 runs the selected one; `select_calculation(calc_id)` keeps
its name for `tools/drive.py --run` and the remote API, and now selects
the calculation in the outliner. A calculation's form ends with the
estimate line and a button (`formRun`): "Run", "Run again" when its result
is stale, "Cancel" while it runs. The automatic re-run (Run > Re-run cheap
results automatically) is mirrored by a checkable "Follow" button
(`autoRerunButton`) next to Cancel, whose tooltip says that cheap results
are computed again as the model changes. The toolbar widgets are created
by P2 in `_build_toolbars`; P4 owns their behaviour. Files owned: in
`ui/mainwindow.py` `_refresh_calculations`, `selected_calculation`,
`select_calculation`, `_calculation_chosen`, `_update_actions`,
`run_selected`, `run_guarded`, `set_auto_rerun`, `_update_status`; in
`ui/properties.py` the calculation form's button. Renames:
`calculationBox` removed. Tests to adapt: `test_run_button_draws_the_result`,
`test_cancel_running_job_keeps_window_usable`,
`test_cost_guard_asks_before_a_long_run`, `test_a_run_shows_in_the_window`,
`test_status_and_screenshots`, `test_sliders_and_a_sweep_in_the_window`,
`test_run_at_once`, and the tests of `tests/ui/test_mainwindow.py` and
`tests/ui/test_window_session.py` that read `calc_box`.
Tests to add: the button names the selected calculation and follows the
outliner and the tabs; "Run every stale result" runs exactly the stale
ones; the form's button runs and cancels. Acceptance: `python tools/
drive.py honeycomb_zeeman_rashba --size 1200x800 --do '{"do": "select",
"entry": "c2"}' --shot run.png` shows "Run c2 · dos"; `--run c1` still
works unchanged. Depends on P2.

**P5, the help beside the form, and the panels (must).** The help no
longer hides the form it explains, the panels that matter are visible,
the ones that rarely matter are out of the way, and the arrangement is
remembered. The right column is Properties alone at the top, 60 percent of
the height, and below it one tabbed area of Help, Sliders and Jobs in that
order (`helpDock` raised by F1 and by a form's ?, `jobsDock` raised when a
job starts only if Help is not showing an item). The bottom area (Log,
Console) is hidden by default; the status bar shows the last message
(`statusMessage`, in the error colour for an error, after the system
summary) and a "Log" toggle button at its right (`logToggle`) that shows
the bottom area; the error bar behaves as today. Every dock keeps its
title and loses the float button (`DockWidgetClosable | DockWidgetMovable`
only, since floating does not work on Wayland, 88); View > Panels is a
submenu of the docks' toggle actions and View > Reset layout
(`resetLayoutAction`) restores the default arrangement. The arrangement
and the window size are a setting: `QMainWindow.saveState()` as base64
under `layout` in `io/settings.py`, written on close and restored at start
when `use_settings` is on (the Document's `ui` block is unchanged, and the
tests, which run without settings, see the default). View > Interface
text (`uiTextMenu`, normal or large: `theme.UI_POINTS` 10 or 12 points,
setting `ui_text`) joins Plot text, for a projector. Files owned: the
docks of the constructor of `ui/mainwindow.py`, `_build_menus` (View),
`message`, `closeEvent`; `io/settings.py`; `ui/theme.py` (`UI_POINTS` as
a setting); `ui/bars.py`. Renames: none. Tests to adapt:
`test_the_settings_of_the_interactive_window`,
`test_f1_shows_the_help_of_the_selected_entry`,
`test_the_guides_and_the_question_mark`, `test_dark_theme_and_back`,
`test_project_remembers_the_view`, `test_errors_are_logged_not_raised`,
`test_the_jobs_panel_keeps_the_newest_finished_rows`. Tests to add: F1
shows the help while the form stays visible; the layout setting round
trips and Reset layout restores the default; the Log toggle shows the
bottom area; the interface text setting. Acceptance: `python tools/
drive.py honeycomb_zeeman_rashba --size 1200x800 --do '{"do": "select",
"entry": "t1"}' --do '{"do": "help"}' --shot help.png` shows the form and
the help at once with the three field components visible without a
scroll; the same at 1600x1000 in the dark theme. Depends on nothing but
edits the constructor, which P1 touches: P5 goes before P1 (Order).

**P6, forms that read as physics (must).** A term's form says what each
number is in the words of the physics, shows the knobs that matter first
and folds the rare ones, and offers a slider or a sweep from the number
itself. The form head is the title with the enabled switch in its row
(`check_enabled` kept), the group and the doc line, the formula, then the
parameters; the region row is shown when the system has regions, else a
muted line "acts everywhere · restrict to a region" (`regionLink`) whose
link opens the Regions "+" menu of P2; the "Hilbert space after it" line
stays. The f(r) button (`fieldButton_<p>`) becomes a menu button showing
the kind when it is not a number ("expression", "piecewise", "profile",
"interpolated", "painted", "from result"), whose menu lists the kinds
(`fieldKind_<p>_<kind>` actions, replacing the `fieldKindBox_<p>` combo);
choosing one opens the panel of that kind only (`fieldPanel_<p>` kept),
the long help becoming a tooltip and one line ("x, y, z, r; sin, exp,
tanh; (x > 0) is 1 or 0"); a vector Field's components keep one panel
each. A parameter label's context menu (`label_<p>`, which has Lock and
Unlock) gains "Attach a slider" (the `slider` action with a range from
the value: between 0 and twice the value, ordered, or -1 to 1 for zero),
"Sweep this parameter"
(adds a sweep calculation of 11 points over that range, selects it) and,
for a Field, "Preview on the canvas". The system form's words: a "spin"
combo, spinless or spinful, in place of "spinful (requested)", and
"superconducting (Nambu)" in place of "Nambu (requested)", both with the
tooltip that the terms decide by themselves (a Zeeman field makes the
Hamiltonian spinful, a pairing makes it Nambu) and that the choice here
asks for it without such a term, which is what "(requested)" said;
"hopping range
(neighbours)" in place of "neighbour hoppings"; "sparse matrices (large
systems)" in place of "sparse"; the Document's fields keep their names.
The mean-field form folds V and J beyond the first neighbours under a
checkable group "further neighbours" (nice, inside this package). Files
owned: `ui/forms.py`, `ui/properties.py`, `ui/sliders.py` (the range
helper). Renames: `fieldKindBox_<p>` removed. Tests to adapt:
`test_field_editor_goes_piecewise_and_back`, `test_new_field_kinds_and_the_brush`,
`test_a_texture_feeds_an_exchange_field`,
`test_a_from_result_field_opens_before_its_result_exists`,
`test_every_entry_has_a_form`, `test_new_editors_commit`,
`test_lattice_parameters`, `test_locks_in_the_forms_and_the_outliner`,
`test_the_forms_and_the_outliner_read_as_they_should`,
`test_undo_of_a_piece_whose_box_has_the_focus`,
`test_a_number_the_field_panel_cannot_read_is_refused`,
`test_text_being_typed_survives_a_finished_build`,
`test_a_form_rebuilt_while_a_value_is_typed`,
`test_sliders_of_removed_or_locked_parameters`,
`test_neighbour_hoppings_that_are_not_finite_are_refused_in_the_system_form`,
`test_undo_keeps_the_form_of_the_mean_field_or_the_model`, and the field
tests of `tests/test_drive.py`. Tests to add: the kind menu shows the
kind and opens the right panel; the label menu attaches a slider with the
expected range and adds a sweep; the region link appears only without
regions; the system form's words. Acceptance: `python tools/drive.py
honeycomb_zeeman_rashba --size 1200x800 --do '{"do": "select", "entry":
"t1"}' --widget propertiesDock --shot form.png`; the same for `s1` and
for `s1/meanfield` of `honeycomb_hubbard`. Depends on P2 for the region
link only (the link may be a no-op until P2 lands); runs in parallel.

**P7, the outliner (must).** The tree says what each row is and in what
state, nothing is cut off, and a row's state reads the same everywhere.
The Status column is sized to its contents with the full text as the
row's tooltip and the Entry column takes the rest; the system row's
status is the summary "2D · 8 sites · spinful" (the kind is in the
icon or the label); the marks are one set for the tree, the tabs and the
status row of P3: done "✓", stale "↻", running "70%", failed "✗" in the
error colour, invalid "✗" in the error colour, disabled "○", locked "locked"
(Unicode until P8 draws them as icons); the Mean field row reads
"off" or "U = 3, runs with the calculations" unclipped. Files owned:
`ui/outliner.py` (P2 adds the "+" buttons there first). Renames: none.
Tests to adapt: `test_the_forms_and_the_outliner_read_as_they_should`,
`test_invalid_entry_is_flagged_in_the_tree`,
`test_outliner_checkbox_toggles_and_undo`, `test_drag_to_reorder`,
`test_the_outline_lists_a_classical_model_and_its_terms`,
`test_undo_and_stale_marking`, `test_locks_in_the_forms_and_the_outliner`.
Tests to add: no status text is elided at the default width for every
preset (the column's width covers its longest text). Acceptance: the
outliner of every preset at 1200x800 (`--widget outlinerDock`), nothing
clipped. Depends on P2.

**P8, icons and the look (nice).** The controls are recognizable at a
glance, as in Blender and Inkscape, and the bars take less room. `ui/
icons.py` gives `icon(name)`, a `QIcon` from `resources/icons/<name>.svg`
tinted with the theme's text colour (the SVG files use `currentColor`,
replaced at load, cached per theme, the cache cleared by `theme.apply`,
after which the window sets its icons again); the files are a vendored
subset of Tabler Icons (MIT, the licence kept at `resources/icons/LICENSE`),
about thirty: new, open, save, undo, redo, run, cancel, follow, add,
search, fit, pan, zoom in, zoom out, pick, box, lasso, select, paint,
image, export, data, overlay, detach, help, lattice, op, term, calculation,
region, mean field, python, done, stale, failed, locked, log, panels. They
go on the toolbar row, the canvas bars, the outliner's rows and marks,
the status row of a plot and the start page's buttons; the text of a
toolbar button stays beside its icon where the row has room (Run, Add,
New system) and becomes the tooltip elsewhere. `tests/ui/test_icons.py`
renders every name `icons.NAMES` lists in both themes. Files owned:
`ui/icons.py` (new), `resources/icons/`, `pyproject.toml` and
`MANIFEST.in`, and one `icon(...)` call per control in the owners' files.
Depends on P2, P3 and P7 (the controls it decorates); the must packages
do not wait for it.

**P9, the documentation and the record (must, last).** `docs/user_guide.md`:
"The window" and "Getting started" rewritten for the start page, the "+"
menus, the Run button, the panels and the Log toggle; the shortcut table
regenerated from `ui/shortcuts.py` (no new keys are planned: Ctrl+F opens
the Add menu); `tools/readme_images.py` rerun and README's words about
the toolbar updated; PLAN.md section 4's mockup replaced by the one above
and this phase's report written in section 7 with what each package
built and left; CLAUDE.md's code map gains `ui/start.py`, `ui/palette.py`,
`ui/canvasbar.py`, `ui/icons.py`, `tools/make_thumbnails.py`, its example
commands follow the widget names, and its status paragraph says the phase
is done. All of it in the voice of `~/.claude/CLAUDE.md`. Depends on
every other package.

*Order, and how a workflow runs it.* `ui/mainwindow.py` (2966 lines) is
touched by seven packages, so the ones that rewrite whole parts of it are
one serial lane and the ones that own other files run in parallel, each
in a worktree of its own, merged in a fixed order with the suite run
after each merge. The lane: P5 (the constructor's docks, the View menu),
then P2 (the toolbar row, the palettes, `select` and `set_workspace`),
each merged before the next starts. Then in parallel: P1 (start page),
P3 (bars), P4 (run), P6 (forms), P7 (outliner), whose touches of
`ui/mainwindow.py` are the named methods only; merged in that order,
conflicts resolved by the merging agent with the package text as the
reference. Then P8 (icons across the files), then P9. Splitting
`ui/mainwindow.py` into modules first was considered and not chosen: a
3000-line refactor by an agent before any visible change is a risk the
serial lane avoids, and the lane is two packages long. An agent building
a package reads this phase, the package's paragraph, CLAUDE.md (its
"Good practices for the interface", written with this plan, say how
the interface is designed, built and checked here) and the constraints
above, takes the acceptance screenshots at 1200x800 and 1600x1000 in both
themes with the layout settled, and reports the names it renamed and the
tests it adapted.

Decisions for the maintainer to confirm, numbered after 89; the first
option of each is the one the plan recommends and builds unless answered:

90. the empty program shows the start page (lattices, presets and recent
    files as pictures) in place of the viewport; or the gallery dialog at
    start; or the blank canvas with a longer hint;
91. the pictures are PNG files shipped in the package, made by
    `tools/make_thumbnails.py` and checked by a test; or drawn in the
    window from a build (blank until the worker answers); or none, the
    cards carry text only;
92. entries are added from "+" buttons on the outliner's section rows and
    one Add menu with a search line (Blender's Add menu, Inkscape's
    search); or from a palette panel of its own on the left; or from the
    toolbar rows as today;
93. the three workspace tabs stay and follow the selection; or the tabs go
    and the outliner's sections take their role; or they stay and do not
    follow;
94. the Calculation combo goes: Run names the selected calculation and
    its menu lists the others and "every stale result"; or the combo stays;
95. the Help panel moves below Properties, tabbed with Sliders and Jobs;
    or stays tabbed with Properties; or opens as a window;
96. the bottom area (Log, Console) is hidden by default, the last message
    in the status bar with a Log toggle; or shown as today;
97. the docks lose their float button, the arrangement and the window
    size are a setting, and View > Reset layout restores the default; or
    as today;
98. the canvas, plot and k-space bars are guiqula's own (Fit, Pan, Zoom,
    Save image and the tools of each drawing) over a hidden matplotlib
    toolbar, without Back, Forward, Subplots and Customize (revisiting
    84's wording, whose Pan and Zoom stay as our buttons); or matplotlib's
    toolbar stays;
99. the k-space tab is hidden for a system without periodic directions;
    or stays with a caption;
100. a stale result shows a row with Run again on its tab, a running one
     its progress and Cancel; or the Jobs dock alone;
101. a slider or a sweep is attached from a parameter's context menu, the
     Sliders dock's typed form staying for drivers; or the dock's form
     alone;
102. the f(r) button becomes a kind menu that shows the kind; or as today;
103. the icons are a vendored subset of Tabler Icons (MIT), tinted by the
     theme; or Material Symbols (Apache 2.0); or no icons;
104. the interface text size is a setting, normal or large; or the
     desktop's alone;
105. the system form says spin (spinless, spinful), superconducting
     (Nambu), hopping range (neighbours) and sparse matrices (large
     systems); or keeps the engine's words;
106. the packages are built by a workflow, a serial lane for the two that
     rewrite parts of `ui/mainwindow.py` and the file owners in parallel in
     worktrees, merged in the stated order with the suite after each merge;
     or one after another by one agent.

Maintainer's answer (2026-10-03, before building): 93, the workspace tabs
stay and follow the selection, as recommended; the other decisions stand
as recommended unless answered.

**Phase 8 as built (2026-10-03 and 2026-10-04, branch phase8).** The phase
was built as its "Order" says (decision 106): P5 and then P2 in a serial
lane on branch phase8, each built by one agent and reviewed by another,
which fixed what it found before the commit; then P1, P3, P4, P6 and P7 in
parallel, each in a worktree of its own from the head of the lane (cc7629a,
which also gave `ui/marks.py`, the one set of marks the parallel packages
were to share), merged in that order with the fast suite after each merge,
the last merge ending on 48138a7; then P8, the icons, whose foundation was
built beside the parallel packages, merged after them and finished on phase8
(d995b1e), while P9, the documentation and this record, was written in
parallel on a branch of its own from 48138a7 and merged after P8 (188d92f),
and a last step brought the record to P8 as built. Each package took its
acceptance screenshots at 1200x800 and 1600x1000 in both themes with the
layout settled, and the merge took them all again on the merged tree (104
shots, `ui_dump/phase8/merged/`, which is not tracked). Verified offscreen,
with the shots read; not verified: a real desktop session (the panels
dragged on Wayland, the menus, cards and bars used with a mouse, a screen
taller than the offscreen one, whose 800 px made every Add menu scroll at
1600x1000 too). What each package built and left, then where they met, the
start budget, what is still open, and the decisions:

*P5, the help beside the form, and the panels.* The right column is
Properties at 60 percent of its height over Help, Sliders and Jobs, tabbed
in that order, so F1 or a form's ? raises Help and the form stays in sight:
at 1200x800 the three components of the Zeeman field show without a scroll,
the help below them. Help says "Select an entry and press F1 for its help."
until the first help is asked. A new job raises Jobs, except while Help
shows an entry's help or Sliders is in front, and never reopens a Jobs
panel that was closed. The Log and the Console start hidden; the status bar
shows the last message (`statusMessage`, in the error colour for an error)
and at its right the Log toggle (`logToggle`). The panels lost their float
button (decision 97) and are `Dock`, a `QDockWidget` subclass painting its
title in its own font, since Qt keeps the font a dock was made with and
View > Interface text would leave the titles behind. View gains Panels
(`panelsMenu`, one `panel_<dockName>` action per panel, its tooltip saying
what the panel holds), Reset layout (`resetLayoutAction`) and Interface text
(`uiTextMenu`). The settings gain `ui_text` and `layout`, written on close and
read at start by the program's window only, and `LAYOUT_VERSION` (now 3)
discards an arrangement stored before a change of the bars. Window actions
`ui_text`, `reset_layout`, `log` and `panel`; the window's `WINDOW_ACTIONS`
tuple became complete, and a test compares it with `remote/api.py`'s. Left:
the console's and the code editor's fixed fonts and the formula images do
not grow with the interface text (they do since P8, decision 143), and the
help browser keeps the horizontal scroll bar it had before.

*P2, adding things where they appear, and workspaces that follow.*
`ui/palette.py` holds `PaletteMenu`, one menu per family: a search line
(`paletteSearch`, the active item when the menu opens, so one Down reaches
the first entry shown) over the entries by group, with their formulas in
the tooltips (the actions keep `addOp_`, `addTerm_`, `addCalc_` and
`newSystem_<kind>`). Typing filters with `search_entries`, the best match is
drawn in bold and Enter adds it once; the menu's own items (the mean field,
the classical systems) match on their text and tooltip, so "hubbard" finds
Mean field (interactions). Each section row of the outliner has a "+"
(`outlinerAdd_<system>_geometry`, `_regions`, `_hamiltonian`, `_model`, and
`outlinerAdd_calculations`), an item widget at the right of the status cell,
which opens that menu for that system with `popup()`, since `exec()` from a
click never returns offscreen; the Regions menu (`regionsMenu`) offers
Region by expression and Region from selection, and the terms of a quantum
system end with Mean field (interactions) (`addMeanfield`). The first
toolbar row became the workspace tabs, New system (`newSystemButton`, the
lattices with the classical systems last), Add (`addButton`, the menu of the
workspace's family, opened by Ctrl+F) and the run controls, and the second
rows with their search boxes went. `select()` brings forward the workspace
of what is selected, so an add switches it too, and a saved workspace is
applied after the saved selection. Window actions `add_menu` and
`run_stale`. Left to the packages after it, and done there: Run naming its
calculation (P4), the selection row (P3), the widths of the outliner (P7).

*P1, the start page.* The empty program opens on `StartPage` (`ui/start.py`,
`startPage`), which stands with the viewport in a `QStackedWidget`
(`centralStack`) below the recovery, trust, error and cost bars, so that a
recovery offered at start shows over it. It has a filter box
(`startSearch`) and three bands: the lattices in the order of New system's
menu (`startLattice_<kind>`) and the three classical systems
(`startClassical_<kind>`); the presets (`startPreset_<name>`), the two
teaching ones first, marked "teaching, some parameters locked", each with
the first sentence of its notes; the recent files (`startRecent_<n>`) with
Open a project... (`startOpenButton`); then a footer whose link opens
guiqula's guide in the Help panel. Each band shows its first row until its
Show all (`startMore_<band>`) or a text in the filter (decision 107), and
has one line for a band without cards and one for a filter that leaves
none. `_document_changed` shows the page whenever the document has no
system, so an add, an undo back to nothing, File > New and an open all land
on the right side, and the window without a session shows it too. The 52
pictures (1 to 9 kB each, about 200 kB) are PNG files in
`resources/thumbnails/{lattices,classical,presets}/`, drawn by
`tools/make_thumbnails.py` in one offscreen window in the light theme with
the plugins off, and read when a card first comes into sight; the titles
and first sentences come from the presets' JSON files (4 ms for the
sixteen), so no index was needed. The gallery (Ctrl+Shift+O) is made of the
same cards (`galleryPreset_<name>`): a click selects, a double click or Open
opens. Window action `start` (search), and `drive.py`'s report says whether
the page shows (`start_page`). Left: three 3D pictures (buckled honeycomb,
cubic, diamond) show one dot in their cell and texture_exchange's a thin
ladder, faithful grabs of what the canvas draws; the gallery's headings do
not follow a change of the interface text while it is open; at large text
on 1200x800 the footer drops below the fold.

*P3, the canvas and plot bars.* `ui/canvasbar.py` holds `CanvasBar`, built
over a `NavigationToolbar2QT` cut down to Home, Pan, Zoom and Save, hidden
and kept as `canvas.toolbar` (`HiddenToolbar`), so that `CanvasNavigation`
and the tests read matplotlib's own mode; its Fit, Pan and Zoom drive the
hidden toolbar and show which mode is on (decision 98, 84's Pan and Zoom
kept as our buttons). The viewport is about 480 px wide at 1200x800 and the
structure bar's controls take about 1000 px of text, so a bar is a widget
whose groups, each a small toolbar, flow onto further lines rather than
behind a chevron (decision 119). The structure bar (`structureBar`) holds
Fit, Pan and Zoom, the selection tools that were the second toolbar row
(`geometryToolbar` is gone, its widgets keep their names), Show, 3D, the
brush in the field view and Save image; a result's bar (`plotBar_<calc>`)
Fit, Pan, Zoom, Pick, Box, Lasso, Overlay, Export, Save data, Detach and
Save image; the k-space bar (`kspaceBar`) its path tools; in the pyvista
scene Reset view, View and Save image take the place of Fit, Pan, Zoom and
Save image in the same bar. Fit is the drawing's own fit, and Pan or Zoom on
a plot unchecks its pick tools. Above a plot, the status row
(`plotStatus_<calc>`) says stale with Run again (`plotRun_<calc>`), queued
or running with its progress (`plotProgress_<calc>`) and Cancel
(`plotCancel_<calc>`), or failed with the first line of the message and Run
again, and is hidden for a current result (decision 120); the tab and a
detached window's title carry the mark. The k-space tab is hidden while the
selected system has no periodic direction, and without a system (decision
99). No window action was needed. Left: in the pyvista scene the structure
bar takes four lines at 1200 px, since the View button is as wide as its
longest text (two since P8, decision 142); the failure line begins with the
engine's exception chain, so at 1200 px the useful part is in the tooltip;
`theme.centre` may take five drawings to settle (three before), which the
taller bar needed.

*P4, Run where the result is.* The Calculation combo (`calculationBox`) is
gone (decision 94). `selected_calculation()` returns the calculation
selected in the outliner, else the one whose tab is shown, else the first;
`runButton` reads "Run c1 · bands", its tooltip naming the system and F5,
and is disabled with a line saying how to add a calculation when there is
none; its arrow (`runMenu`) lists the other calculations and Run every stale
result (`runStaleAction`); `cancelButton` is enabled while a job of that
calculation is queued or running; Follow (`autoRerunButton`) mirrors Run >
Re-run cheap results automatically. Showing a result's tab while another
calculation is selected selects the tab's calculation, by a click, Ctrl+Tab,
the keys or the wheel on the tab bar, a pick that shows another result, or a
result put back in its tab (decision 122). `select_calculation` keeps its
name for `drive.py --run` and the remote API, and now selects in the
outliner. A calculation's form ends with its estimate (`formEstimate`) and a
button (`formRun`, decision 124). Window action `run`. Left, and settled by
P8 (decisions 140 and 141): at 1200x800 the run row of the eight-parameter
density of states is below the fold of Properties and the surface spectral
function's is cut at its edge, and the form's "result: running" above
"running, 0%" says the same thing twice.

*P6, forms that read as physics.* A form's head is the title with its
enabled switch (`check_enabled`, now in the title's row) and ?, the group and
doc line, then the formula. A term of a system without regions reads "acts
everywhere · restrict to a region" (`regionLink`), whose link opens P2's
Regions menu below it; with a region the form has its region box. The f(r)
button (`fieldButton_<p>`) is a menu button reading f(r) for a number and the
kind otherwise; its menu (`fieldKindMenu_<p>`) lists the seven kinds
(`fieldKind_<p>_<kind>`, replacing the combo `fieldKindBox_<p>`), and choosing
one makes a Field of that kind and opens the panel of that kind only
(decisions 102 and 128); the expression's help is one line, the long text
its tooltip, and the kind buttons of a vector Field take one width so that
its boxes line up. A parameter's label has a menu (`paramMenu_<p>`, which
was `lockMenu`): Lock or Unlock, Attach a slider, Sweep this parameter, and
for a Field of a term or of the mean field Preview on the canvas, with a
submenu per component for a vector (decisions 101, 125 to 127). The system
form says spin (a combo, spinless or spinful), superconducting (Nambu),
hopping range (neighbours) and sparse matrices (large systems), with the
engine's names and what "(requested)" meant in the tooltips (decision 105),
and the mean field folds V2, V3, J2 and J3 under further neighbours
(`furtherNeighbours`, decision 129). The Sliders panel's empty line points at
the label's menu. After the merge, the field view's caption and the paint
action's refusal name both ways into a preview (a click into a Field, or
Preview on the canvas), where they named "its f(r) panel". Left: a sweep
from the label of a system whose calculations give no number runs the first
one and fails when it is run; the kind buttons of different scalar rows do
not line up.

*P7, the outliner.* The Status column holds the state only and is exactly
as wide as its longest text (`Outliner.status_width`, applied after every
refresh, progress report and change of font), the Entry column taking the
rest, so nothing scrolls sideways and every "+" stays in sight; the label
says what the row is (id, kind, name, an op's parameters printed as %g, a
region's selection, the region of a term) and is elided from its tail
(decision 131). The marks are `ui/marks.py`'s, through `mark()`: done ✓,
stale ↻ (dimmed), running "70%", failed and invalid ✗ in the error colour,
disabled ○ with the row dimmed, locked, a warning ⚠, and the words queued
and cancelled; a term reads the Hilbert space after it, a region its sites,
a scalar result its value after the mark ("✓ 1"), a calculation never run
nothing (decision 133). The system's row and the mean field while it is on
are detail rows across both columns (`DETAIL_ROLE`, decision 132): the
system's name in bold with "2D · 8 sites · spinful", the mean field's "U =
3, runs with the calculations" and, after a run, "U = 3, E = -1.68089",
broken by `wrapped()` at the spaces, and inside a word only when the word
alone is wider than the line, so that nothing is cut, also with large text
in a squeezed outliner. Every row's tooltip is the same on both columns:
the full label, then the state in words and the messages. `ui/marks.py`
gains `WARNING`, `QUEUED`, `CANCELLED`, `DIM_STATES` and `calculation_state`.
Left: the labels are elided at 1200x800, where the dock is 279 to 320 px,
with the whole text in the tooltip.

*P8, icons and the look.* Its foundation was built on branch phase8-p8a
(aefb014, on cc7629a) beside the parallel packages and merged after them
(b36ab51, whose one conflict was the package-data line of `pyproject.toml`,
which now carries the start page's pictures and the icons alike); the icons
went on the controls on phase8 (50be2f7), and a review fixed what it found
(d995b1e). `ui/icons.py` gives `icon(name, color="TEXT")`, a `QIcon` drawn
from `resources/icons/<name>.svg` with `currentColor` replaced by a colour of
the active theme, its disabled state in the theme's DISABLED grey, so that a
disabled button's icon greys with its label, and its selected state in the
highlighted text's colour. Icons are cached per theme; `theme.apply()` ends
with `icons.theme_changed()`, which empties the cache and calls back what
`on_theme_change` registered, and `icons.follow(widget, method)` sets a
widget's icons at its first show and again after every change of theme, so
that what is out of sight at start (the structure canvas behind the start
page, the k-space tab, the menus) costs nothing then. The 51 files are
Tabler Icons 3.35.0 under the MIT licence (`resources/icons/LICENSE`; the
README lists our name, Tabler's name and style, and its table is what the
fetch loop and a test read): the 38 the package lists, twelve for the marks
and the outliner (remove, run_stale, kspace, structure, settings, theme, 3d,
show, slider, invalid, disabled, running) and `view` for the scene's View
menu, all in the outline style but `cancel`, the filled stop square
(decision 137). Each is drawn at 16 and 24 px, and at their multiple on a
screen whose pixel ratio is above 1, tinted through `DestinationIn`, since
a Python `QIconEngine` subclass crashes PySide6 6.11 when the icon is
detached.

On the first row New system, Add and Run keep their text beside the icon,
and Cancel and Follow show the icon alone, their names leading their
tooltips (decision 136). The bars of the structure canvas, of each result
and of the k-space tab do the same for Fit, Pan, Zoom, the selection tools,
Show (an eye, `canvasViewLabel`), 3D (a cube beside the check box of
`view3dBox`, whose text went to its accessible name and its tooltip),
Paint, Overlay, Export, Save data, Detach and Save image, and for the
scene's Reset view and View; the k-space bar's path tools, the brush's
value and radius and the start page's Show all keep their words. The
viewport's Structure and k-space tabs, the Log toggle, the form's ?,
`formRun`, the start page's filter and Open a project..., the status row
of a plot (its state as an icon, `plotStatusMark_<calc>`, with Run again
and Cancel) and thirteen menu entries have theirs too; the Run button's
menu sets `run` on the other calculations and `run_stale` on Run every
stale result each time it opens, so in the active theme, and a checkable
menu entry carries none (decision 139). The outliner draws a row's kind as
an icon before its label (a system, the lattice, an op, a region, a term,
the mean field, a calculation, Python code) and the marks of its Status
column as icons (decision 138), both at paint time, so that they follow the
theme without a refresh, while the text of the column keeps `ui/marks.py`'s
Unicode, which the tooltips, the tabs and the tests read; it indents by 14
px, which gives a term's label back the room its icon takes.

The look, from the merge's open list. The scene's View button, as wide as
its longest name, put the pyvista bar on four lines at 1200x800; it shows
its icon now, and the view's name leads its tooltip and the hint line over
the scene ("User Perspective · ...", where Blender writes it in the corner
of its viewport), so the bar takes two (decision 142). A calculation's
estimate and Run moved from the end of its form to a footer of Properties
(`propertiesFooter`, under the scrolled form, `propertiesScroll`), so that
the eight-parameter density of states and the surface spectral function
keep Run in sight at 1200x800 (decision 140). The form's result line reads
`marks.calculation_state`, as the tab, the status row and the tree do, and
its run row says "running in a worker, no progress reported yet" until the
job reports one (decision 141). The start page's footer names the "+" of
the outliner's rows, where it said "in the Hamiltonian workspace". The
formula images and the fixed-width fonts of the console and of a Python
node follow View > Interface text (decision 143). A result view never
computed is cleared again when a change of theme or of plot text redraws
it, so that its empty figure takes the theme's background (it stayed white
in the dark theme since before phase 8). `LAYOUT_VERSION` is 4, since the
first row changed its widths, so an arrangement of the panels saved before
gives the default once.

P8 also paid back the start of phase 8. The plugins are looked for first in
the `entry_points.txt` files on the path (`plugins.none_declared`, about 5
ms where `importlib.metadata` takes 30, and which still decides whenever a
file names the group); the start page makes its cards as they come into
sight, one row of each band at start (decision 144), and is built from the
top down; the central column is put in the window before it is filled,
since with the application's style sheet every new parent restyles its
whole subtree; the console takes its fixed-width font at its first show;
and the icons are set at the first show of their widget (decision 145). A
card made later joins the Tab order after the nearest card made before it
in its band, or after the band's heading row (`Band._chain`), so that Tab
walks the filter, Show all and the lattices, Show all and the examples,
Open a project... and the recent files, then the footer.

Left: the icons stay 16 px at large interface text; the detail rows' marks
and the warning sign ⚠ stay text, so that an invalid entry's red triangle
and a warning's ⚠ are two triangles that mean different things; a quantum
and a classical system share the structure icon; the vendored `zoom_out`,
`slider` and `settings` have no control (the menu of a parameter's label
has no icons); and a folded card of the start page is not a widget until
Show all, the filter (the `start` action) or `StartPage.card()` makes it,
so `findChild`, `drive.py --widget` and the remote `widgets` and
`screenshot` methods do not see it before.

*P9, the documentation and the record.* guiqula's guide: "Getting started"
and "The window" rewritten for the start page, the "+" menus and Add, the
workspaces that follow, Run and its menu, the outliner, the bars and the
status row, the panels and the forms, and the sections on selections, terms,
Fields, the mean field, results, sweeps and sliders, locks and settings
brought to the window as built; its shortcut table, checked against
`ui/shortcuts.py`, needed no change, since no key was added. README's words
on the window, section 4 of this file, CLAUDE.md's status, code map, window
actions and examples. Of the merge's open list, the items that document the
interface for its drivers: `tools/drive.py`'s help names every window action
(nine were missing since before phase 8, and
`test_the_help_names_every_window_action` reads `remote/api.py`'s list), and
its report gains `selected_calculation`; the remote `plot` titles a figure as
the window does, with the mark of its state in place of " (stale)", and
replies with the state (decision 134); `remote/window.py`'s `state()` gains
`start_page` and `selected_calculation`. Left to the step after P8, and
done there: words that live in `ui/`, which P8 owned while this was
written (the start page's footer, which P8 changed, and View > Find in
palette with the `find` shortcut's words, which now name the Add menu: View
> Find in the Add menu, "the Add menu of the workspace, with its search
line", copied in the guide's table), the parts of the guide, README and
CLAUDE.md that describe P8's icons, and the README's screenshots. The fast
suite on P9's tree: 1175 passed, 1 skipped, and `test_startup` failed at
2.28 s at a load average of about 7.5 (alone, once under the budget, then
2.21 and 2.36 s); P9 changes nothing the window imports at start.

*The last step* (after the merge of P9, 188d92f). It wrote P8's paragraph
and decisions 136 to 145 into this record, the icons, the run row in the
footer and the start page's keys into the guide, and `ui/icons.py`, the
footer and the folded cards into CLAUDE.md, `tools/drive.py`'s help and
`remote/window.py`; it changed the words of View > Find in palette and of
the `find` shortcut; and it made `tools/readme_images.py` select its entry
again after the runs, since `--run` selects the calculation it runs since
P4, so that the README's pictures, redrawn from the finished tree, show the
form of the term, the op or the mean field that their captions name, with
the last result in front.

*Renames.* The objectNames renamed or removed, which the tests,
`tools/drive.py --widget`, the remote `screenshot` and `widgets` methods and
CLAUDE.md's examples follow (each package kept every name it could, and the
new ones are in its paragraph above):

- removed by P2: `newClassicalButton` (its `newClassical_<kind>` actions are
  the last section of New system's menu), `addOpButton`, `addTermButton` and
  `addCalculationButton` (Add, and the outliner's "+"), `addRegionButton`
  (`regionsMenu`), `meanfieldButton` (`addMeanfield`), `opSearch`,
  `termSearch` and `calculationSearch` (`paletteSearch` in each
  `paletteMenu_<family>`), `hamiltonianToolbar` and `calculateToolbar`;
- removed by P3: `geometryToolbar`, whose widgets keep their names on
  `structureBar`; `structureToolbar` names the hidden matplotlib toolbar now,
  and the plots' and the k-space tab's are `plotToolbar_<calc>` and
  `kspaceToolbar`, hidden under `plotBar_<calc>` and `kspaceBar`;
- removed by P4: `calculationBox`;
- removed or renamed by P6: `fieldKindBox_<p>` (the actions
  `fieldKind_<p>_<kind>` of `fieldKindMenu_<p>`), `lockMenu` (`paramMenu_<p>`);
- the same name on another class: `runButton`, `cancelButton`,
  `regionFromSelectionButton`, `calculateOnSelectionButton`,
  `removeSelectedButton`, `kpathRemoveLast` and `kpathDefault`
  (`QToolButton`), `fieldButton_<p>` (a menu button), `construction_has_spin`
  (a combo), `presetList` (a scroll area of cards), the seven docks (`Dock`),
  and by P8 `properties`, the Properties panel, a `QWidget` now that holds
  the scrolled form (`propertiesScroll`, the scroll area it was) and the
  footer of a calculation's run row (`propertiesFooter`); its
  `verticalScrollBar()` is still the form's;
- P8 renamed nothing else and removed nothing: `view3dBox` lost its text
  (its accessible name and tooltip say 3D), and the start page's folded
  cards exist only once they are made (see P8 above).

Python names went with them (`window.calc_box`, `window.palettes`,
`term_button`, `show_meanfield` for `add_meanfield`, `PlotView._navigation`,
`Gallery.list.count()`), and the tests that read them were adapted.

*Where the packages met.* P1 merged without a conflict. P3 met P1 in the
imports of `ui/mainwindow.py` and in the widget list of
`test_main_window_builds_without_workers`, which now checks the names of
both, and a test of P3 asked whether `structureBar` was visible in a window
without a session, where P1's page hides the viewport (it asks
`isVisibleTo` now). P4 met P1 in `WINDOW_ACTIONS` (`start` and `run`, in both
lists and in `drive.py`'s help) and P3 in the imports and at the end of
`_job_changed`, where P4's update of the run controls follows P3's
`_show_state`, so that a job event updates the tab, the status row and Run
together. P6 met P4 at the end of `EntryForm`, keeping P6's
`restrict_to_region` and P4's `_add_run_row`. P7 met P3 in
`test_undo_and_stale_marking`, which checks P3's row and P7's marks. Three
fixes of the integration followed: the field view's captions of P6 above;
after a run that failed over an earlier result the tab and the row said
failed while the tree said stale, since the tree read `Session.status` alone,
so `marks.calculation_state(session, calc, job)` now holds the rule the three
read (decision 121), and the tree reads running, not 0%, before a job's first
report; and a progress report rewrote the tooltip of the row's first column,
which `Outliner._item_changed` took for a toggle of the check box, putting
"set_enabled: only ops and terms can be disabled" in red in the status bar
at every report, so a change of the first column is a toggle now only on a
row that has a check box. P8 was built on phase8 after these merges, so
its touches of the other packages' files were edits rather than merges:
P1's `ui/start.py` (the cards made as they come into sight, `Band._chain`),
P3's `ui/canvasbar.py` (`set_icon`, a check box's text kept as its
accessible name), P4's run row (moved into the footer) and P7's outliner
(the kinds and marks as icons). P9 met nothing when merged after P8, since
it touched only the documentation, PLAN.md, CLAUDE.md, `tools/drive.py` and
`remote/`, and its remote plot reads `ui/marks.py` and `ui/plots.py`, which
P8 left as P9 read them. The window actions the phase added are `ui_text`,
`reset_layout`, `log` and `panel` (P5), `add_menu` and `run_stale` (P2),
`start` (P1) and `run` (P4), in both lists and in `drive.py`'s help. The fast
suite passed after each merge but for the start budget, and the whole
suite, with the wheel, on 48138a7: 1173 passed, 1 skipped, in 29 minutes;
on P8's review (d995b1e) the fast suite gave 1198 passed and 1 skipped,
and on the finished tree the whole suite, with the wheel, gave 1203
passed and 1 skipped in 27 minutes, `test_startup` included, with three
warnings of matplotlib (see "Still open").

*The start budget.* `tests/ui/test_startup.py` keeps its 2.0 s, and it is
the one test that failed in some of the suites of the phase: on this
machine, under the load of several suites at once, the base of the
parallel packages was over the budget too. Before P8, run alternately on
three trees, ten rounds at a load average of about 8, the probe took a
median of 2.09 s on cc7629a, 2.13 s with P1 and 2.17 s on the merged tree
(48138a7), with 191 modules in each and nothing heavy loaded, and at a
load of 3.5 the medians were 1.96 s and 2.06 s: phase 8 had added about 80
ms to the start, the start page's cards about 45 to 60 ms of it, after P2
took about 0.76 s out of the start by filling the Add menus at their first
showing (decision 110). P8 took that back and a little more (decisions 144
and 145): its review measured medians of 1.193 s on cc7629a against 1.177 s
on d995b1e (ten rounds each, at a load of 1.4 to 1.5), and the last step,
on the finished tree, 1.299 s on cc7629a against 1.276 s (twenty rounds
each, alternating, each in a fresh interpreter with fresh data and
settings and the plugins on, at a load of 2.5 to 3.2). The window thus
starts, start page and icons included, in the time it took before phase
8. The budget was not raised (decision 135).

*Still open* (by the file that would change; none blocks a use of the
program):

- `ui/plots.py`: the failure line of the status row begins with the
  engine's exception chain, so at 1200 px the useful part is in the
  tooltip;
- `ui/start.py`, `ui/gallery.py`: a folded card is not a widget until it
  is made (decision 144); Ctrl+F opens New system while the page shows
  (decision 113); three 3D pictures (buckled honeycomb, cubic, diamond)
  show one dot in their cell, which is what one cell of them holds from
  mplot3d's angle (a choice: a supercell, another angle or stronger
  neighbours), and texture_exchange's a thin ladder, its first calculation
  being a chain drawn at equal aspect (a choice of calculation or of
  aspect); at large text on 1200x800 the footer drops below the fold;
- `ui/outliner.py`, `ui/marks.py`: the entry labels are elided at 1200x800
  (the whole text in the tooltip), and so is a long system name in its
  detail row ("Hubbard model on the honeycomb la…"); the detail rows' marks
  and the warning ⚠ are text beside icons, an invalid entry's red triangle
  and a warning's ⚠ two triangles of different meaning; one icon for both
  system kinds;
- `ui/icons.py` and the controls: the icons stay 16 px at large interface
  text; `zoom_out`, `slider` and `settings` are vendored without a control;
  the k-space path tools and Show all are words;
- `ui/forms.py`, `ui/properties.py`: a sweep from the label of a system
  whose calculations give no number runs the first one and fails when run,
  with the sweep's own message ("c1 gives no number to collect"), which is
  decision 125 as built (a choice: refusing the sweep at once instead);
- `ui/help.py`: a displayed equation wider than the panel (nine of the 281
  sections of the two guides at the default width, "The screened
  interaction" the widest at about 610 px) still gives its page a
  horizontal scroll bar (a choice: the scroll bar for those pages, or the
  equation's image scaled to the panel's width, smaller to read);
- `tests/ui/test_startup.py`: the budget under load (decision 135), which
  the base of the phase misses as well.

Decisions taken while building, for the maintainer to confirm; the first
option of each is the one built:

107. the start page's bands fold to their first row (the recent files to
     three) until their Show all or a text in the filter, so that the three
     bands and the footer are in sight at 1200x800 (where the folded
     lattices are Dimer and Bipartite chain, a 2D lattice one click away),
     and the filter and Show all survive File > New; or the full grid of
     every card (about 2900 px of lattices at two cards a row, the examples
     below the fold), cleared at each return;
108. one set of pictures, drawn in the light theme and kept on its light
     background in the dark one, the classical systems with pictures of
     their own; or a second set drawn in the dark theme;
109. a selection that changes the workspace changes the canvas view as the
     tab would, so a Field preview ends when another workspace comes forward
     (it stays while moving between terms); or the field view kept across
     workspaces;
110. the Add menus are filled at their first showing, which took about 0.76
     s out of the start and costs it at the first opening of the terms'
     menu; or filled at start;
111. a menu taller than the screen scrolls (on an 800 px screen Mean field
     (interactions) sits behind the scroll arrow, and the search reaches
     it), and a menu that shrinks while typing stays where it opened, so the
     search line does not move under the cursor; or columns, a more compact
     menu, or the menu moved back below its button;
112. the "+" of a locked section stays enabled, and the lock's refusal is the
     answer; or disabled, with a tooltip naming the lock;
113. the "+" of a system's section adds to that system, while Add and the
     "+" of Calculations add to the system of the selected entry; without a
     system Add and that "+" are disabled and Ctrl+F opens New system, also
     over the start page, whose filter has the focus when the page first
     shows; or Ctrl+F focusing the start page's filter while it shows;
114. Run every stale result runs the cheap ones at once and asks about the
     slow ones together, in one question of the cost bar; or one question
     each;
115. a new job brings Jobs to the front unless Help is showing an entry's
     help or Sliders is in front, which keeps a slider in sight while its
     drag re-runs results but also keeps Jobs behind for an explicit Run
     after a slider was added, and a closed Jobs panel is never reopened; or
     the Sliders exception narrowed to a drag in progress;
116. Help is the front tab below Properties and says "Select an entry and
     press F1 for its help." until the first help is asked, following the
     selection only after that (the first rendering of an entry costs about
     0.3 s); or the help rendered at every selection from the start;
117. the arrangement of the panels and the window's size are a setting
     (`saveState` and `saveGeometry`), written on close and read at start by
     the program's window only, an arrangement of another `LAYOUT_VERSION`
     giving the default, and Reset layout keeps the window's size; or Reset
     layout restoring the size too;
118. large interface text is two points above normal, normal being the
     desktop's size with a floor of 10 points, and the panels' titles are
     painted in the panels' font so that they follow it; or fixed sizes (10
     and 12 points) whatever the desktop;
119. the canvas bars wrap: a bar is a row of small toolbars flowing onto
     further lines (four on the structure at 1200 px with the brush, two on
     a plot), never a chevron, with a separator only between sections on a
     line; or one row with a chevron, or shorter labels (which P8's icons
     give anyway);
120. a result that is not simply current has a status row above its plot
     (stale with Run again; queued or running with its progress and Cancel;
     failed with the first line of the message and Run again), hidden when
     it is current, a result never computed keeping its caption; the tab
     carries the mark (the word queued while queued, nothing when done), and
     a result going stale is not redrawn, so it keeps its zoom and its title
     no longer says STALE; or the Jobs panel alone (decision 100's
     alternative), or the stale title kept;
121. a calculation has one state for the tree, the tab and the status row
     (`marks.calculation_state`, from the merge): a run that failed over an
     earlier result reads failed while no current result is there, the
     earlier result staying drawn under the row, and an undo that brings a
     current result back clears it; or the tree reading stale there, as
     `Session.status` says;
122. nothing remembers a chosen calculation: the outliner and the tab shown
     decide, showing a result's tab while another calculation is selected
     selects the tab's (but not the neighbour Qt shows when a tab goes
     away), and a selected term or op keeps its form while Run follows the
     tab; or a remembered choice of calculation;
123. the toolbar's Run stays enabled while its calculation runs, a second
     press queuing a second run, and Cancel beside it is enabled only while
     a job of that calculation is queued or running; or Run disabled while
     its calculation runs;
124. a calculation's form ends with its estimate and a button reading Run,
     Run again only for a stale result, or Cancel while queued or running,
     through the window action `run` and so the cost guard, the estimate
     saying why there is none (invalid, until the system is built, a kind
     with no declared cost); or the toolbar's Run alone;
125. a sweep from a parameter's label runs the calculation itself for a
     calculation's parameter, else the first calculation of the system known
     to give numbers (its result has them, or its declaration draws a
     scalar: the gap, the Chern number), else the first one, with a tooltip
     saying that it has given no number so far, and is refused without a
     calculation; or the sweep added with an empty calculation for its form
     to refuse;
126. a slider or a sweep from a label spans 0 to twice the value, ordered,
     or -1 to 1 for zero, clipped to the parameter's declared bounds, and a
     sweep takes 11 values; or the range unclipped, for the sweep's check
     to refuse;
127. Attach a slider is refused on a locked parameter while Sweep this
     parameter is offered (a sweep changes copies of the document only), the
     numbers of a sweep itself get the lock alone, and attaching twice adds
     a second slider; or one slider per parameter, and both refused under a
     lock;
128. the kind menu: choosing expression on a number stores nothing until an
     expression is typed, a change of kind keeps what it can (a number
     becomes the default of piecewise, a profile its formula), and the panel
     of a structured kind is open while the Field is of that kind, with no
     toggle to hide it; or the checkable f(r) button that hid the panel;
129. further neighbours is a check box over a framed group, ticked whenever
     V2, V3, J2 or J3 is not zero, unticking it setting the four to zero in
     one undo step, and nothing else folds, since the registry declares no
     rarity; or a declaration of the rare parameters in the registry,
     folded on every form;
130. the spin combo shows what is asked, so it reads spinless while a Zeeman
     field makes the Hamiltonian spinful (the line under the form says so);
     or the combo showing what was built, or a hint beside it;
131. the outliner's Status column holds the state only, as wide as its
     longest text, and the label says what the row is (an op's parameters, a
     region's selection, a term's region), elided at 1200x800 with the whole
     text in the tooltip; or the mixed column of before, scrolled sideways;
132. the system and the mean field are detail rows across both columns, the
     status at the right of the label when it fits and wrapped under it
     otherwise (two lines for most systems at 1200x800), the mean field
     reading its interactions and, after a run, its total energy; or one
     line each and a wider Status column;
133. a calculation never run reads nothing, a queued or cancelled one its
     word, a scalar result its value after the mark, a calculation names its
     system only in a document with several, and a system's kind is the last
     word of its summary and its tooltip, with no icon of its own; or a mark
     for never run, and an icon of the kind (P8);
134. the remote `plot` titles a figure as the window does ("c1 · bands ·
     spinful"), followed by the mark the window shows in the tab when the
     state is stale, queued, running or failed, and replies with the state,
     which the MCP tool's text spells out ("stale: the model changed since
     it was computed"); or the window's title alone, with the state in the
     reply;
135. the start budget stays at 2.0 s, and the start is kept within it by
     what P8 built (decisions 144 and 145): the finished tree starts in a
     median 1.276 s against 1.299 s for the tree before phase 8, at a load
     of 2.5 to 3.2, while under the load of several suites at once both
     trees can miss it; or the budget raised;
136. the first row shows New system, Add and Run with their text beside the
     icon and Cancel and Follow as icons alone, and the bars show icons
     alone, their names leading the tooltips, but for the k-space path
     tools, the brush's labels and the start page's Show all, which keep
     their words; or the text beside every icon, or icons alone everywhere;
137. Cancel is Tabler's filled stop square, the one filled icon of an
     outline set, since the outline square, greyed while nothing runs,
     reads at 16 px as the empty check box of the 3D switch, beside Follow,
     another icon alone; or the outline stop, or a crossed circle;
138. the outliner draws its marks as icons (a check mark; a circular arrow,
     dimmed; an hourglass with the percentage; a cross in the error colour
     for a failed run and a warning triangle in the error colour for an
     invalid entry; a crossed-out circle, dimmed; a padlock), while its text
     and the tabs keep the Unicode signs, and a row's kind is an icon before
     its label, one for both system kinds; or P7's Unicode marks in the
     tree, or an icon per system kind;
139. a checkable menu entry carries no icon, since Fusion then draws it
     without its check box, its state a faint frame around the icon (Re-run
     cheap results automatically lost its icon for this); or the icon kept,
     the frame the only sign of the state;
140. a calculation's estimate and Run sit in a footer of Properties, under
     the scrolled form, so that they stay in sight however long the form
     is; or at the end of the form, as P4 built them;
141. the form's result line reads the state the tab, the row and the tree
     read, and the run row says "running in a worker, no progress reported
     yet" until the first report; or P4's "running, 0%" and the result
     line on `Session.status`;
142. the scene's View button shows its icon, and the view's name leads its
     tooltip and the line over the scene, as Blender writes it in the
     corner of its viewport, so that the bar takes two lines at 1200 px; or
     the button reading the view's name, on four lines;
143. the formula images and the fixed-width fonts of the console and of a
     Python node follow View > Interface text; or their fixed sizes;
144. the start page makes a card when it comes into sight (one row of each
     band at start, the others at Show all or a filter), in its band's Tab
     order whatever order the cards were made in, the recent files before
     the footer, so that a folded card is no widget for `findChild` and the
     drivers until it is made; or every card made in an idle timer after
     the first paint (about 15 ms soon after the start), which keeps
     `findChild` working;
145. the icons are set at the first show of their widget and again at each
     change of theme (`icons.follow`), and the plugins are looked for in the
     `entry_points.txt` files before `importlib.metadata`; or the icons set
     as the window is built, about 70 ms of the start.

Maintainer's answers to the phase-8 report (2026-10-05, asked one by one,
in the order of the report): 107 to 115, 123 and 130 were answered as
recommended, and the others stand as recommended at the maintainer's word,
except 121, answered with its alternative: a run that fails while an
earlier result of that calculation is kept reads stale, as `Session.status`
says, in the tree, the tab and the status row alike (the row with Run
again, the earlier result staying drawn under it), and the failure itself
is read in the Jobs panel; a run that fails with no earlier result still
reads failed. Built on branch still-open: `marks.calculation_state` gives
`Session.status`'s state but for a job still queued or running, so the
tree, the tab, the status row, the form's result line (decision 141) and
the remote `plot` state (decision 134) read stale there together, a result
that still matches the document reading done.

**After the report: the items still open that needed no decision
(2026-10-05, branch still-open).** The three warnings of matplotlib in the
tests ("constrained_layout not applied because axes sizes collapsed to
zero") were a defect of the window that the tests showed: the Jobs panel's
line of the workers, one line of about 770 px once the console worker had
started (interactive, batch and console, each with its pid and state), was
the minimum width of the right column, which took it from the viewport, so
the structure canvas was left about 180 px wide, too narrow for the axes
and a colour bar. The line now wraps (`ui/jobpanel.py`), the column keeps
the 340 px the window gives it (`resizeDocks`), where before it grew to
about 430 px as soon as two workers had reported, which is the width of
the screenshots of phase 8, and the warnings are gone, the one in
`test_the_scene_moves_as_in_blender` included, since it was a pending draw
of the previous module's window. In the Hamiltonian view, the Field
preview and a result drawn on the atoms, an atom coloured by a value is
outlined in the bonds' grey (`structure.atom_edge`), since its outline was
the background's colour, white in the light theme, around the near-white
middle of the diverging scale, so that an onsite energy of zero was a disc
lost on the background; the sublattice colours of the structure view keep
the background's outline, which separates them. The help browser's
horizontal scroll bar came from the code blocks, whose lines Qt keeps
whole, so that one line of pyqula's examples longer than the panel (the
`add_zeeman` example of t1's help, about 560 px in a panel of 410) made
the whole page scroll sideways; their lines now wrap at the panel's width
as the prose does (`HelpBrowser._wrap_code`), and of the 281 sections of
the two guides only the nine with a wider equation keep the bar. The
gallery's group headings are the start page's `Title`, painted in the
interface font at each paint, so that they follow View > Interface text
while the gallery is open (a font set on a `QLabel` stayed at its size), and
a closed gallery is deleted (`WA_DeleteOnClose`) rather than kept hidden
with its pictures, each opening making one of its own as before. The
kind buttons of a form are as wide as the widest of the form
(`forms.line_up`, called by every form after it sets its values), the rule
a vector's components already followed, so that an expression's button over
a number's f(r) no longer narrows that row's box.

Decisions taken while fixing them, for the maintainer to confirm; the first
option of each is the one built:

146. the lines of a code block in the help wrap at the panel's width, as
     the prose does (a copied line stays whole); or the code kept on whole
     lines, with the horizontal scroll bar for its pages;
147. an atom coloured by a value is outlined in the bonds' grey in both
     themes, the sublattice colours keeping the background's outline; or a
     darker outline (the text's colour), or the outline only on the
     light background.

Maintainer's answers to the open items (2026-10-05, asked one by one):
the right column keeps the 340 px the window gives, and the README's
pictures are made again at that width; the hoppings of the Hamiltonian view
are coloured with `twilight_shifted` in the dark theme, so that phase zero
is light there, the light theme keeping `twilight`; the status row of a
failed result shows the last line of the message, the final exception,
the whole chain staying in the tooltip and in Jobs (amending decision
120); the icons are drawn at 20 px at large interface text, set again when
View > Interface text changes; a displayed equation wider than the help
panel is scaled down to its width; the 3D pictures of the buckled
honeycomb, cubic and diamond lattices are a small supercell (3x3x1, 2x2x2
and 2x2x2) seen from an oblique angle with its bonds, and texture_exchange's
picture is drawn without equal aspect; the sweep from a label stays as
built (decision 125, confirmed).

Built on branch still-open, one commit each. The hopping phases' scale is
the theme's `PHASE_MAP` (`ui/theme.py`), which `theme.drawing` rebinds
with the other colours, so an exported figure takes the scale of the
theme it is drawn in.

### Where the section 13 items land

| Phase | Items |
|---|---|
| 0 | 13.4 vendored layout and path shim; 13.15 startup measured from the first test |
| 1 | 13.1 systems list in the schema; 13.3 headless runner (it is the test driver); regions in the schema (13.2); 14.2 thin UI; 14.3 skip semantics; seeds and `h.copy()` in the engine (3.3) |
| 2 | 13.2 selection tools on the canvas; 13.6 plain Qt theme; 13.14 crash reports |
| 3 | 13.12 cost guard; 13.8 Hamiltonian view (first version: bonds and onsite); Fields: constant, expression, piecewise (section 3.8) |
| 4 | 13.5 classical systems; 13.7 trust prompt (arrives with Python nodes); 14.1 remote console; 13.9 Brillouin-zone canvas; 13.10 sliders and sweeps; 13.11 overlays; Fields: profile, interpolated, painted, from_result (section 3.8) |
| 5 | 13.16 teaching presets and exports; 13.13 in-app help from pyqula's documentation |
| 7 | 13.17 calculations from picks |
| 7 (proposed) | 13.17 calculations from picks |

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| numba compile latency on first use (12 s measured) | warm-up in the worker at startup, `NUMBA_CACHE_DIR` |
| pyqula writes `.OUT` files even with `write=False` | every job runs in its own scratch cwd; pass `write=False` where accepted |
| numba/BLAS not thread-safe with Qt threads | calculations only in the worker process |
| Windows `spawn` cannot pickle lambdas | expressions are strings compiled in the worker; Python nodes are source strings |
| Qt plugin discovery under conda | launcher sets `QT_QPA_PLATFORM_PLUGIN_PATH` when the default lookup fails |
| OpenGL under conda for 3D | 3D is an optional extra; 2D canvas never needs it; pyvista renders off-screen with whatever VTK finds (X through XWayland, else EGL, verified without a display), and a pyvista that cannot draw leaves the drawing to mplot3d, saying why in the caption |
| jax as a pyqula hard dependency on Windows | CPU wheels exist; mean-field solvers that need jax degrade to linear mixing if import fails |
| scope creep (pyqula has ~150 modules) | registry-driven design; Python nodes cover the long tail; phases fix the first wave |
| `add_*` upgrades spinless → spinful → Nambu silently | engine pre-scans the stack's requirements and sets the mode once; outliner shows the mode after each term (3.1) |
| unseeded randomness in disorder terms and guesses | explicit `seed` per stochastic entry, seeded by the engine before applying (3.3) |
| pyqula calculations return arrays, files or figures | one adapter per calculation entry; `.OUT` files parsed from the scratch dir; figures never cross the process boundary (3.3) |

## 9. Relation to quantum-lattice

guiqula is a new program, not a refactor. It keeps quantum-lattice's good
ideas (formula images, the "pyqula code" view, the atom picker, the
presets; its hand-written physics tooltips give way to pyqula's own
documentation, 13.13) and drops what limited it: one form per mode, `.ui`
files, plotting through `.OUT` files and subprocesses, cwd-based state, a
hand-maintained applicability table. Per decision 5, guiqula does not need to
supersede quantum-lattice; both can coexist.

## 10. Repository conventions (to be kept in CLAUDE.md)

- Upstream pyqula is read-only; only `tools/update_vendor.sh` touches `vendor/`.
- No Qt imports outside `src/guiqula/ui/` and `remote/`. pyqula imports only
  in `engine/` and `worker/`, and in `registry/` only inside function bodies
  (the UI imports the registry for its forms and must never load pyqula,
  13.15); `core/`, `commands/`, `io/` only see the Document. Enforced by
  `tests/test_layering.py` since phase 0.
- Anything that mutates the Document goes through a Command.
- Every registry entry has an engine test against direct pyqula.
- Every calculation runs in a scratch cwd, never in the repo or `vendor/`.

## 11. Open questions for later phases

Every question this section held has been settled by a decision recorded
where it was built, so what follows says where each one went (2026-09-28);
the recommendations for the in-app help are kept in full, since they are
written nowhere else, and the last point that was open to the maintainer
closes the section.

- The k-path editor for non-standard cells is the Brillouin-zone canvas of
  phase 4, part 4b (13.9, `ui/kspace.py`, phase-4 decision 16): it draws the
  Wigner-Seitz cell of the geometry's own reciprocal lattice and stores the
  vertices in reduced coordinates, snapping them only onto the points pyqula
  names for that geometry, so a non-standard cell needs nothing of its own.
  A 3D zone is drawn by its k3 = 0 cut, so a vertex off that plane is typed,
  as a label or in reduced coordinates, rather than clicked.
- How much of a mean-field result a project file keeps is phase-4 decision
  12 (part 4a): the results, with the total energy in their reports, and not
  the converged mean-field Hamiltonian.
- Sweeps are a calculation kind collecting numbers, not a study object of the
  outliner, phase-4 decision 13 (part 4a, `registry/sweeps.py`).
- A classical texture reaches a quantum system's exchange term by reference,
  through a `from_result` Field, phase-4 decision 11 (part 3): a reader of a
  stale result is flagged, not marked stale itself, and its key follows the
  data it read (`Result.reads`).
- Review item 8, the build cache lost on every cancel, was settled by phase 1
  once review item 7 was adopted: cancelling a calculation kills only the
  batch worker running it, so the interactive worker's cache survives, and
  the interactive worker is killed only when a build has run 10 s and a newer
  build of the same system is asked for (phase-4 decision 10).

The in-app help (13.13) had seven open points, found by the code review of
that decision after phase 1: docstrings that pyqula sets only at import
time, which a parse of the source misses; pyqula's guide missing from the
wheel; entries with no section in the guide or no single pyqula call behind
them; the guide's LaTeX, with no QtWebEngine in PySide6-Essentials; a refresh
of the vendored copy against "commit a refresh on its own"; stale text about
hand-written help; and what an anchor is, with a few smaller points. The
recommendations below answer them in that order (2026-09-27, the phase-5
design, where they are items 1 to 7 in section 7). Phase 5, part 4 built them
as written, and they stand as built, since the phase-5 report was not
commented on.

  1. Read the docstrings statically in the UI process, from the source of
     the pyqula copy in use (an AST parse, lazily at the first help
     request): `helptk.get_docstring(f)` is a decorator that copies `f`'s
     docstring, which the parser follows. No worker round trip (a long
     build would delay the help) and no generated file. A test compares
     the result with `inspect.getdoc` of the imported pyqula for every
     pyqula call behind a registry entry.
  2. `setup.py` copies `vendor/pyqula_user_guide.md` into the wheel next to
     the vendored package (`guiqula/_vendor/pyqula_user_guide.md`);
     `vendor/` stays an exact copy; the wheel test checks the guide is there.
  3. An entry's help is assembled, not written: its label, formula and
     one-line doc; its parameters (from the declarations); the pyqula code
     it generates with the current values (quantum-lattice's "pyqula code"
     view, section 9); the docstrings of the pyqula calls behind it (the
     Call's target, or `pyqula=` on a custom entry); and the guide sections
     it names (`guide=`; none when the guide has none). The concepts that
     are guiqula's own (systems, Fields, regions, Python nodes, sweeps, the
     console, trust) are described in guiqula's user guide, shipped with the
     package and shown by the same panel; it describes the program, never
     pyqula's physics.
  4. Qt's Markdown renderer (`QTextBrowser`, in PySide6-Essentials) with
     every equation drawn by mathtext after a few rewrites (`\tfrac`, an
     unbraced `\mathbf k`, `\mod`), and its LaTeX source shown as code when
     mathtext cannot draw it (matrices, multi-line environments). Measured
     before the rewrites: mathtext draws 56 of the 69 display equations and
     897 of the 931 inline ones.
  5. `tools/update_vendor.sh` runs the help tests (anchors, docstrings)
     after copying and prints what broke; the anchor fixes a renamed upstream
     section forces may join the refresh commit, nothing else (CLAUDE.md's
     "commit a refresh on its own" says so).
  6. Sections 4, 7 and 9 are corrected (2026-09-27). An entry's `doc` stays
     guiqula's one-line summary (tooltip, palette, search) and its
     `formula` the image; neither replaces pyqula's text. 3.2's declaration
     gains `guide=` and `pyqula=` (its example was brought up to date on
     2026-09-28).
  7. An anchor is a heading's text as written in the guide, found outside
     fenced code blocks; a heading used twice is addressed as "Parent >
     Heading", and the test refuses an ambiguous one. The refresh script
     fails when the upstream guide is missing, before writing anything.
     With `$GUIQULA_PYQULA_PATH` set, the help reads the guide and the
     docstrings from that tree when it has them, and says which copy it
     shows. The help is a dock tabbed with Properties, opened by F1 or a ?
     button on each form, with Help > pyqula user guide and guiqula user
     guide for the whole texts.

The last point that was open to the maintainer, the arithmetic of the
expressions (3.8, a review decision of 2026-09-28), was answered the same
day: a comparison stays the number 1.0 where it holds and 0.0 elsewhere, as
built, rather than numpy's booleans (whose `+` is an or and whose `-`
fails) or a refusal of any arithmetic on a comparison. Nothing is open.

## 12. Decisions (made by the maintainer, 2026-09-26)

1. **Framework**: PySide6.
2. **Plots**: matplotlib embedded in Qt for everything; pyqtgraph only for the
   structure canvas if large systems need it.
3. **pyqula in releases**: vendored inside the package (section 6), not a PyPI
   dependency.
4. **Embedded Python console and Python nodes**: included (phase 4).
5. **quantum-lattice**: guiqula does not need to supersede it; presets are a
   convenience, not a one-to-one reproduction of its modes.
6. **Repository**: `git init` done, GPLv3 (`LICENSE`), name guiqula.
7. **Platforms**: Linux for phases 1 to 5; Mac and Windows packaging in phase 6.

## 13. Further considerations (decided 2026-09-26)

All items were accepted by the maintainer, with item 5 changed from "quantum-only
v1" to "classical models included, with their own features", and item 13 decided
later the same day (after phase 1), with its content taken from pyqula's own
documentation. Items 1 to 7 touch the Document schema or the package layout; items 8
onward are features (placement per phase at the end of section 7).

1. **Several systems per document.** Transport needs leads and a central
   region, embedding needs a host and a defect, and comparing two variants
   needs two systems. Blender's scene holds many objects; the outliner here
   should too. Phase 1 builds one system, but the schema is `systems: [...]`
   from the start and calculations reference systems by id. Retrofitting this
   later means a painful migration.

2. **Selections and regions as first-class objects.** Inkscape's core gesture
   is select, then set a property. Selecting atoms by click, lasso, expression,
   sublattice, layer or distance to the edge yields a named region stored by
   positions. Any term can be restricted to a region (pyqula takes callables
   of `r`, so this maps directly), which gives impurities, domain walls, edge
   terms and layer-dependent fields without code. Geometry ops (remove, shift,
   rotate) act on the current selection too.

3. **Headless runner and provenance.** `guiqula run project.guiqula --calc
   bands` executes through the same engine with no Qt, so heavy jobs can run
   on a cluster or in a terminal and their results load back into the GUI.
   It opens a project with its results (a from_result Field reads the one
   the file keeps), and runs a calculation whose system reads another's
   result after that one (fixes of 2026-09-27). `guiqula script` opens it
   the same way, so it prints the script `run --script` writes; an entry
   pyqula rejected is a comment only when the result that says so is
   current; a document, calculation or output folder that cannot be used
   is one line on stderr, exit status 2 (fixes of 2026-09-28).
   Every result stores its Document snapshot and the vendored pyqula commit,
   and can emit its own reproducing script.

4. **Vendored packaging.** Settled in section 6: `guiqula/_vendor/pyqula` plus
   a `sys.path` shim in both processes, dependencies mirrored, drift recorded
   by the refresh script.

5. **Classical models: included, with their own features.** pyqula's
   classical spin, lattice-gas and Ising models take a geometry but no quantum
   Hamiltonian. A system's `kind` (`quantum`, `classical_spin`, `lattice_gas`,
   `ising`) selects its term palette and calculation palette; geometry,
   regions, canvas, jobs, results and script export are shared. Scope is in
   section 5 ("Classical systems").

6. **Plain Qt widgets with a QSS theme, not qfluentwidgets.** quantum-lattice
   depends on PySide6-Fluent-Widgets; it looks good but adds a dependency with
   its own release cadence and promoted-widget quirks. Fusion style plus a
   light/dark palette gives a clean look with nothing extra to install.

7. **Python nodes in shared files.** Opening a project executes its Python
   nodes and expressions. Do what Blender does: show them but do not run them
   until the user trusts the file (or enables auto-run globally). Expressions
   run in a restricted namespace but are still code.

8. **Hamiltonian view on the canvas.** Show what the terms did: bonds with
   thickness and colour by |t| and phase (Peierls, Haldane), atoms coloured by
   onsite energy, arrows for exchange, colour for pairing. pyqula's
   `get_multihopping()` and `extract` provide the data. A debugging and
   teaching view quantum-lattice never had.

9. **Brillouin-zone canvas.** A k-space tab with the zone, high-symmetry
   points, an editable k-path (drag points, add segments), and the Fermi
   surface drawn on it. `get_default_kpath` and the label registry give the
   defaults.

10. **Drivers, sliders and sweeps.** Any parameter can be attached to a slider
   for live updates of cheap calculations, or swept over a range or a 2D grid
   to produce phase diagrams (gap, Chern number, magnetization against two
   parameters). This falls out of the Document being data.

11. **Result overlays and comparison.** Two band structures on one axes, or
   the difference of two DOS curves, by dropping one result tab onto another.
   Results keep their snapshots, so a difference is always explainable.

12. **Cost guard.** Freedom means someone can build a 100,000-site system and
   ask for a Chern number. Show the Hilbert-space dimension and a rough cost
   per calculation in the status bar, switch to sparse above pyqula's
   `limits.densedimension`, and warn before jobs that will take minutes.

13. **In-app help from pyqula's documentation** (accepted after phase 1: "in app
   help ok, but get from pyqula docs"). The help text is pyqula's own, not
   written again in guiqula: each registry entry names the section of the
   vendored user guide (`vendor/pyqula_user_guide.md`, upstream
   `documentation/user_guide.md`) that covers it, and a help panel renders
   that section together with the docstring of the pyqula call behind the
   entry. quantum-lattice's `TERM_TOOLTIPS` no longer seed it. Refreshing the
   vendored copy refreshes the help; a test checks that every anchor a
   registry entry names exists in the vendored guide, so a renamed upstream
   section fails at refresh time. The guide ships with the package next to
   the vendored pyqula. Phase 5. The code review of this decision found
   design points it leaves open; section 11 records them with the
   recommendations phase 5 built (part 4), which stand as built.

14. **Crash reports.** On an unexpected error, write a bundle with log,
   traceback, Document snapshot and versions to the user data directory and
   offer to open its folder. A student's bug report then reproduces.

15. **Startup budget.** jax imports in about 0.5 s warm and much more cold,
   numba similar. Keep jax and pyqula out of the UI process entirely (they live
   in the worker), start the worker while the window appears, and measure
   startup in the test suite. Measured in phase 0 (2026-09-26, warm cache,
   offscreen): 0.23 s from the first guiqula import to a shown window, 0.3 s
   wall-clock with interpreter start, none of pyqula, jax, numba, numpy or
   matplotlib loaded; importing pyqula alone takes 0.7 s.
   `tests/ui/test_startup.py` asserts the module set and a 2 s budget.
   Phase 1: 0.63 s to a shown window, now with matplotlib and numpy for the
   plot tab; the workers are started after the window is shown. Phase 2:
   0.68 s with the full shell; scipy joined the modules the UI process must
   not load (the worker computes the bonds).

16. **Teaching use.** A preset gallery, one-click export of figure plus data plus
   script, and presets with locked parameters, for use in courses.

17. **Calculations from picks** (asked 2026-09-28, proposed in section 7,
   phase 7, built the same day). A point of a plot is a set of physical values (an
   energy, a k-point, a site, a parameter value), and any calculation whose
   parameters take them can be started from it or moved to it: the LDOS at
   an energy picked on the bands, the LDOS at a picked k-point and energy,
   the Fermi surface at that energy, the Document at a point of a phase
   diagram. Plot kinds declare what their axes carry and parameters what
   they take, in one closed vocabulary, so the combinations are computed,
   never listed; a pick emits ordinary commands and the Document does not
   change; a picked value can stay on the plot as a draggable marker, a
   slider drawn on the plot.

## 14. Plan review (2026-09-26)

A read-through of this document against the vendored pyqula before phase 0.
Items keep the numbers of that review so they can be referred to. The
maintainer's answers are recorded here; the verified facts were folded into
sections 3.1, 3.3, 3.8, 6, 7 and 8; review item 8, the one without an
answer then, is settled in section 11. Items 6 to 10 were answered after phase 0 ("7 9 10 13
14 ok as your recommendation").

1. **Console as a remote REPL** (review item 6; resolves section 4 against
   13.15). The embedded console executes in the worker process, where `g`,
   `h`, `np` and `pyqula` live, and streams text (and arrays on request) back
   to the UI. `doc` and the commands are available there too and go through
   the dispatcher. Lands in phase 4 with the console.
2. **Thin UI in phase 1** (review item 12). Phase 1 ends with a minimal window
   with a job panel (run, progress, cancel, respawn) and one plot tab, so the
   worker ↔ Qt event-loop integration is exercised before the real UI shell.
3. **Invalid entries are skipped, not blocking** (review item 11). An entry
   pyqula rejects is flagged and skipped; the rest of the stack still builds,
   the canvas stays live, and a result built with a skipped entry says so.
4. **Corrections applied** (review items 15 to 18): phase 0 installs only
   `pytest-qt` and `pyqtgraph`; the dependency is `PySide6-Essentials`;
   presets are bare JSON and the loader accepts both forms; autosave is
   debounced.
5. **Verified pyqula facts folded in** (review items 1 to 5): silent
   Hilbert-space upgrades inside `add_*` (3.1); explicit seeds for stochastic
   entries and `h.copy()` before replaying a cached prefix (3.3); one adapter
   per calculation for pyqula's mixed return conventions (3.3); the per-term
   list of which pyqula calls accept a callable of position (3.8).
6. **Interactive worker** (review item 7). Builds, canvas previews and Field
   previews run in a dedicated interactive worker process, separate from the
   batch workers that run calculations, so a running calculation never
   blocks an edit. From phase 1.
7. **Mutations and actions** (review item 9). The dispatcher keeps two kinds
   of operation: *mutations* change the Document and go on the undo stack;
   *actions* (run or cancel a calculation, save, export) are journaled but
   not undoable. From phase 1.
8. **Expressions are data** (review item 10). Field expressions are
   evaluated by an AST-whitelisted numpy evaluator (arithmetic, comparisons,
   a fixed set of numpy functions, the position variables; no attributes
   other than `np.<whitelisted function>`, no subscripts, no calls to
   anything else), so they need no trust prompt; only Python nodes do
   (13.7). Shared presets with expressions open without a prompt.
9. **DAG-aware hashing** (review item 13). The content hash of every
   pipeline entry includes the hashes of what it references (regions now;
   other systems and results once `from_result` Fields exist), so staleness
   propagates along references across systems and calculations. From
   phase 1.
10. **Non-daemonic worker** (review item 14). Workers are started
    non-daemonic, so pyqula's own process pool (`parallel.set_cores`) can
    start inside them, and are shut down explicitly on exit; a phase-1 test
    runs a parallel pyqula call inside the worker.
