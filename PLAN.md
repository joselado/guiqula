# guiqula — design and development plan

guiqula is a graphical workbench for [pyqula](https://github.com/joselado/pyqula),
the Python tight-binding library. This document records the requirements, the
framework decision, the architecture, and the phased plan. It is the reference
for every later design discussion; update it when a decision changes.

Status: **all decisions in sections 12 and 13 made on 2026-09-26 (13.13, in-app
help from pyqula's documentation, decided after phase 1, with open design
points in section 11); the plan review of the same day is in section 14
(decided items) and at the end of section 11 (items still open).** Phases 0 to 3 were
done on 2026-09-26 and phase 4 on 2026-09-27 (section 7); the maintainer asked
for phase 5 without commenting on the phase-4 report, so its items stand as
built. Phase 5 (polish) was done on 2026-09-27; its report (design items 1
to 14, the first seven being the recommendations for the open points of the
in-app help in section 11, and decisions 15 to 24) was not commented on
(phase 6 was asked for), so its items stand as built. Phase 6 (distribution and the add-on) was done on 2026-09-27 in
three parts (remote control and the MCP add-on; plugins; distribution,
verified on Linux); the maintainer answered its report (decisions 25 to 45
in section 7) the same day: a public GitHub repository without CI, pip as
the only installer (the frozen builds dropped), Python 3.12 and 3.13, the
plugin recorded in the documents, and 0.0.1 as the first release, which
the maintainer uploads.

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
  floating dock.
- **pyqtgraph** (pip, pure Python, installed in phase 0) as the fast path for the
  structure canvas once systems have thousands of atoms, and for slider-driven
  live updates. Not needed for phase 1; the canvas starts on matplotlib too.
- **3D structures**: pyqtgraph.opengl first (light). pyvista/vtk are already
  installed here and can back an optional `[3d]` extra later; they are heavy
  and need a working OpenGL stack, so they stay optional. (Phase 4 part 1
  drew 3D with matplotlib's mplot3d instead, because Qt refuses OpenGL
  widgets offscreen; a decision for the maintainer, section 7.)

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
  Nambu) so an upgrade is never invisible. A mid-stack `turn_spinful` on a
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

One Python module per entry, discovered at import (built-ins) or from a
plugins directory (the per-user config directory from `platformdirs`, plus a `guiqula.plugins`
entry-point group for pip-installed extensions; built in phase 6, part 2:
`registry/plugins.py`, `plugin_template/`). An entry declares:

```python
@term("zeeman", label="Zeeman / exchange field", group="Magnetism",
      formula=r"\sum_i \vec m(\vec r_i)\cdot\vec\sigma_i",
      doc="Adds a local exchange field; breaks time reversal.",
      requires=("spin",))
class Zeeman:
    m: Vec3Expr = (0.0, 0.0, 0.0)   # each component scalar or expression
    def apply(self, h, ctx): h.add_zeeman(ctx.vec3(self.m))
    def script(self, ctx): return f"h.add_zeeman({ctx.py(self.m)})"
```

From this single declaration the program derives the properties form, the
tooltip/formula, the validation, the outliner label, the script-export line,
and the JSON schema for save/load. An entry also declares the system kinds it
applies to (`quantum`, `classical_spin`, `lattice_gas`, `ising`), so each kind
gets its own palette from one registry. Calculations declare the same way plus a
`plot` kind (see 3.4). Adding a term or a calculation is one file and one
test; nothing else changes.

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
  calculation that killed it.

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
The lattice constants are not in scope yet. The engine and the exporter
accept `constant` and `expression` from phase 1; the UI editor for them
is phase 3.

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

## 4. The user interface

One window, one document, three workspaces switched by tabs in the header
(Blender-style), sharing the same outliner, viewport and properties panel:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ File Edit View Run Help      [ Geometry ] [ Hamiltonian ] [ Calculate ]     │
├───────────────┬───────────────────────────────────────────┬─────────────────┤
│ OUTLINER      │ VIEWPORT                                   │ PROPERTIES      │
│ ▾ Geometry    │ ┌ Structure ┐┌ Bands ┐┌ DOS ┐┌ LDOS E=0 ┐   │ Zeeman field    │
│   ● honeycomb │ │  · · · · · · · · · ·                  │   │ group Magnetism │
│   ● supercell │ │ · · · ·[· · ·]· · ·   (pan/zoom/pick) │   │ mx  [0.0     ]  │
│   ○ ribbon    │ │  · · · · · · · · · ·                  │   │ my  [0.0     ]  │
│   ● remove 3  │ │ · · · · · · · · · · ·                 │   │ mz  [0.3*tanh(x/4)] f(r)│
│ ▾ Hamiltonian │ │        cell, bonds, sublattice colours │   │                 │
│   spinful     │ └───────────────────────────────────────┘   │ Σ m(r)·σ  (formula)│
│   ● zeeman  ▲ │                                             │ breaks TRS ...  │
│   ● rashba    │                                             │ [Apply] [Reset] │
│   ✗ haldane   │                                             ├─────────────────┤
│   ○ python    │                                             │ JOBS            │
│ ▾ Calculate   │                                             │ bands   ██░ 70% │
│   bands ✓     │                                             │ chern   queued  │
│   dos  stale  │                                             │                 │
├───────────────┴───────────────────────────────────────────┴─────────────────┤
│ LOG / CONSOLE   >>> h.get_gap()   0.412                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2D · 18 atoms · spinful · 36 orbitals · worker idle · autosaved 12:04        │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Outliner** (left): the whole pipeline as one tree, with one top-level
  node per system (the mockup shows a document with a single system; a
  classical system shows a *Model* stack in place of *Hamiltonian*, and the
  middle workspace tab reads *Model* while it is selected). Icons: ● enabled, ○
  disabled, ✗ invalid (with message on hover), ✓ result up to date, *stale*
  result. Drag to reorder, right-click for duplicate/delete/convert-to-python.
  Selecting an item shows it in Properties and highlights what it affects on
  the canvas (e.g. the atoms a removal op deletes, the bonds a hopping term
  touches).
- **Workspace tabs** change what the toolbar offers and what the viewport
  emphasises, not the data: Geometry shows lattice picker and sculpting tools
  (pick atoms, box/lasso, circle/polygon cut, supercell, ribbon, film, stack
  layers, twist); Hamiltonian shows the term palette grouped by physics
  (hopping, onsite, magnetism, spin-orbit, superconductivity, fields,
  disorder, interactions) with a search box; Calculate shows the calculation
  palette (spectral, real space, topology, response, transport, mean-field
  diagnostics, sweeps) and the results table.
- **Viewport** (centre): a Structure tab always present (2D canvas with
  pan/zoom, atom picking, colour by sublattice/onsite/magnetization/LDOS,
  unit cell and neighbour cells, 3D view for 3D lattices), plus one closable
  tab per result. Tabs can be dragged out as floating docks to compare plots
  side by side.
- **Properties** (right): the form for the selected entry, generated from its
  schema. Each numeric field has an `f(r)` toggle to switch to an expression.
  Live preview: changing a geometry or term parameter updates the structure
  canvas immediately (cheap) and marks results stale; results re-run on
  demand (Run button, F5) or on an opt-in "auto re-run" for cheap
  calculations.
- **Log / console** (bottom): job output, errors with tracebacks folded, and a
  Python console (Blender's console). It is a *remote* REPL (decision 14.1):
  the code runs in the worker process, where `g`, `h`, `np` and `pyqula`
  live, and its text output (and arrays on request) streams back, so pyqula
  stays out of the UI process (13.15) and a crash in the console cannot take
  the window down. `doc` and the commands are available in the console too;
  those go through the same dispatcher, so they are undoable and journaled.
- **Presets**: quantum-lattice's seventeen modes become a gallery of presets
  (documents) so the old workflows are one click away, while remaining fully
  editable. Tooltips are the registry's one-line docs and formula images;
  the longer help is pyqula's own documentation (13.13), in a Help dock
  tabbed with Properties (F1 shows the help of the selected entry).

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
- Optional extras: `[3d]` (pyqtgraph.opengl / pyvista), `[fast]` (pyqtgraph).
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
interactive program), 7 (recovery offers only autosaves with unsaved
changes) and 8 (island size from n alone) were not commented on and stand
as built. Facts
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
Save data, Detach into a floating dock and back (a button: dragging a tab
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
them; rebuilt when the Document or the system changed since the last
command that used them), `do()`/`act()` for dispatcher commands
(undoable), `np`, `pyqula`; a final expression is echoed; an error prints
its traceback from the console's own code and the job still ends normally;
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
recommendations for the open points of 13.13 at the end of section 11:
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
matching one current without a re-run; `undo`, `redo` and `history` are
session actions for drivers. Tooltips: the palette menus show the entry's
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
    snapshot (a stale result is reproduced as it was);
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
checks at every poll, so a calculation never holds up the window.
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
every change as the window does. `tools/mcp_check.py` runs the official
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

### Where the section 13 items land

| Phase | Items |
|---|---|
| 0 | 13.4 vendored layout and path shim; 13.15 startup measured from the first test |
| 1 | 13.1 systems list in the schema; 13.3 headless runner (it is the test driver); regions in the schema (13.2); 14.2 thin UI; 14.3 skip semantics; seeds and `h.copy()` in the engine (3.3) |
| 2 | 13.2 selection tools on the canvas; 13.6 plain Qt theme; 13.14 crash reports |
| 3 | 13.12 cost guard; 13.8 Hamiltonian view (first version: bonds and onsite); Fields: constant, expression, piecewise (section 3.8) |
| 4 | 13.5 classical systems; 13.7 trust prompt (arrives with Python nodes); 14.1 remote console; 13.9 Brillouin-zone canvas; 13.10 sliders and sweeps; 13.11 overlays; Fields: profile, interpolated, painted, from_result (section 3.8) |
| 5 | 13.16 teaching presets and exports; 13.13 in-app help from pyqula's documentation |

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| numba compile latency on first use (12 s measured) | warm-up in the worker at startup, `NUMBA_CACHE_DIR` |
| pyqula writes `.OUT` files even with `write=False` | every job runs in its own scratch cwd; pass `write=False` where accepted |
| numba/BLAS not thread-safe with Qt threads | calculations only in the worker process |
| Windows `spawn` cannot pickle lambdas | expressions are strings compiled in the worker; Python nodes are source strings |
| Qt plugin discovery under conda | launcher sets `QT_QPA_PLATFORM_PLUGIN_PATH` when the default lookup fails |
| OpenGL under conda for 3D | 3D is an optional extra; 2D canvas never needs it |
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

- k-path editor UX for non-standard cells (pyqula's `get_default_kpath` covers
  the common ones).
- How much of a mean-field result to persist in project files (size vs
  reproducibility).
- Whether sweeps should be a calculation kind or a first-class "study" object
  with its own outliner section.
- How a classical texture is handed to a quantum system's exchange term
  (result reference in the Document, or a copied array), and how staleness
  propagates across that link.
- Raised in the 2026-09-26 review (section 14) and not yet decided (review
  items 7, 9, 10, 13 and 14 were decided the same day, section 14 items 6
  to 10):
  - (review 8) the build cache lives in worker memory and a cancel kills the
    worker, so every cancel discards it; accept the loss (builds are cheap),
    or keep the cache in the interactive worker and only kill batch workers.
    With review 7 adopted, phase 1 does the latter: a cancel kills only the
    batch worker running that job, whose cache is lost; the interactive
    worker's cache survives.

- In-app help (13.13): open points found by the code review of the decision
  (2026-09-26, after phase 1), numbered as reported to the maintainer. None
  affects phase 1 code; settle them when phase 5 is designed.
  1. Docstrings: the UI process never imports pyqula (13.15), and pyqula
     sets many docstrings only at import time (`helptk.get_docstring`, 14
     methods in `hamiltonians.py` and one in `geometry.py`, e.g.
     `set_filling`, `get_ldos`), so
     parsing the source misses them. Candidates: extract the text when
     `tools/update_vendor.sh` refreshes the copy, or ask the worker.
  2. Packaging: `vendor/pyqula_user_guide.md` is not in the wheel. Shipping
     it needs a packaging change, since `vendor/pyqula` must stay an exact
     copy of upstream and `guiqula/_vendor` is not a package.
  3. Coverage: the guide has no section for many entries (the lattice
     constructors including `lieb_lattice`, `bulk2ribbon`, Anderson
     disorder), and custom entries (bands, DOS, remove_atoms) have no single
     pyqula call whose docstring could be shown; where a docstring exists it
     is often one line (`add_zeeman`) or missing (`get_dos`,
     `bulk2ribbon`). The plan needs a rule for these, consistent with "not
     written again in guiqula", and for guiqula-only concepts (Fields,
     regions, Python nodes).
  4. Math: the guide is LaTeX-heavy (`$$` blocks, `pmatrix`), and
     PySide6-Essentials has no QtWebEngine, so a MathJax view would work on
     the development machine (the Addons wheel is installed) but not for a
     pip install. Candidates: matplotlib mathtext per equation, or images
     rendered at refresh time. (Phase 2 renders the registry's formulas
     with mathtext, `ui/formulas.py`; mathtext has no `pmatrix` or
     multi-line environments, so the guide's equations may still need the
     second route.)
  5. Refresh workflow: the anchor test runs in pytest, not in
     `update_vendor.sh`, so an upstream section rename makes the refresh
     commit red, and fixing the anchor means editing the registry, which
     "commit a refresh on its own" (CLAUDE.md) forbids. Decide which rule
     gives: the script runs the anchor test, or anchor fixes may join the
     refresh commit.
  6. Stale text: PLAN.md still says help and tooltips are written in
     guiqula or reused from quantum-lattice in the phase 5 description
     (section 7), section 4 ("tooltips and formula images can be reused"),
     section 9 ("tooltips with physics") and the 3.2 example (hand-written
     `doc=`). Every registry entry has a hand-written `doc` and `formula`
     whose role next to pyqula's text is undecided, and 3.2 lists no anchor
     field.
  7. Smaller points: "anchor" is undefined, and a naive heading scan picks up
     `#` comment lines in the guide's code blocks (some duplicated); the
     refresh script copies the guide with a bare `cp` after the package
     rsync, so a moved upstream guide leaves a mixed copy and an outdated
     VENDOR.md; with `GUIQULA_PYQULA_PATH` set, the help and the running code
     come from different pyqula versions; section 4's layout has no place
     for a help panel.

  Recommendations (2026-09-27, phase-5 design; numbered as the points, and
  items 1 to 7 of the phase-5 design in section 7), built as written in
  phase 5, part 4, pending the maintainer's confirmation:
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
     gains `guide=` and `pyqula=`.
  7. An anchor is a heading's text as written in the guide, found outside
     fenced code blocks; a heading used twice is addressed as "Parent >
     Heading", and the test refuses an ambiguous one. The refresh script
     fails when the upstream guide is missing, before writing anything.
     With `$GUIQULA_PYQULA_PATH` set, the help reads the guide and the
     docstrings from that tree when it has them, and says which copy it
     shows. The help is a dock tabbed with Properties, opened by F1 or a ?
     button on each form, with Help > pyqula user guide and guiqula user
     guide for the whole texts.

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
   design points it leaves open; they are listed at the end of section 11
   with the recommendations phase 5 built (part 4), for the maintainer to
   confirm.

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

## 14. Plan review (2026-09-26)

A read-through of this document against the vendored pyqula before phase 0.
Items keep the numbers of that review so they can be referred to. The
maintainer's answers are recorded here; the verified facts were folded into
sections 3.1, 3.3, 3.8, 6, 7 and 8; the items without an answer yet are at
the end of section 11. Items 6 to 10 were answered after phase 0 ("7 9 10 13
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
