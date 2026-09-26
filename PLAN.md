# guiqula — design and development plan

guiqula is a graphical workbench for [pyqula](https://github.com/joselado/pyqula),
the Python tight-binding library. This document records the requirements, the
framework decision, the architecture, and the phased plan. It is the reference
for every later design discussion; update it when a decision changes.

Status: **all decisions in sections 12 and 13 made on 2026-09-26 (only 13.13 is
still open); the plan review of the same day is in section 14 (decided items)
and at the end of section 11 (items still open).** Nothing in `src/` exists
yet; phase 0 is next.

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
- **pyqtgraph** (pip, pure Python, not installed yet) as the fast path for the
  structure canvas once systems have thousands of atoms, and for slider-driven
  live updates. Not needed for phase 1; the canvas starts on matplotlib too.
- **3D structures**: pyqtgraph.opengl first (light). pyvista/vtk are already
  installed here and can back an optional `[3d]` extra later; they are heavy
  and need a working OpenGL stack, so they stay optional.

## 3. Architecture: headless core, command API, Qt view

```
src/guiqula/
  core/       Document model (JSON-serializable). No Qt, no pyqula imports.
  registry/   Declarative catalogue: lattices, geometry ops, terms, calculations,
              operators. Each entry = parameter schema + applicability rules +
              a build function + docs/tooltip/formula. Plugins register here.
  engine/     Turns a Document into pyqula objects. Content-hash cache so that
              editing one term rebuilds only from that point down.
  worker/     Runs engine jobs in a separate OS process (multiprocessing spawn),
              in a scratch cwd. Returns numpy arrays + metadata, never widgets.
  commands/   Every mutation of the Document is a named Command with undo.
              This is the single API used by the UI, the tests, the embedded
              console, the CLI driver and the future Claude add-on.
  io/         Project save/load (.guiqula), autosave journal, crash recovery,
              pyqula script export.
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
        "meanfield": {"enabled": false, "U": 2.0, "V1": 0.0, "filling": 0.5, "mf": "random", "solver": "linear_mixing"}
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
entry-point group for pip-installed extensions). An entry declares:

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

### 3.8 Spatial modulation of any parameter (requirement 12)

Every parameter of every term is typed as a **Field**, never as a bare float.
A Field is a constant or one of these, all JSON-serializable and compiled to
a callable of position inside the worker:

| Field kind | what the user gives | pyqula side |
|---|---|---|
| `constant` | a number | the number |
| `expression` | `0.3*tanh(x/4)`, with `x,y,z,r,np` and the lattice constants in scope | `lambda r: ...` |
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
as a two-point function. Not `add_valley_exchange` and not
`add_crystal_field`. A registry entry declares whether its pyqula call takes
a Field natively; otherwise it declares a fallback designed per term (one
candidate: apply the term with a unit amplitude and scale the resulting
onsite or hopping entries per site or per bond through `get_multihopping()`,
which still has to be checked for bond terms that mix with existing
hoppings), or the parameter is constant-only and the form says so. `rashba.py:97` calls a position-dependent strength once
per bond from Python, so a compiled Field must be cheap per call (a compiled
numpy expression or an array lookup, never a re-parse).

Phase 3 delivers `constant`, `expression` and `piecewise`; phase 4 adds
`profile`, `interpolated`, `painted` and `from_result`.

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
  editable. quantum-lattice's tooltips and formula images can be reused.

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
  work.
- Optional extras: `[3d]` (pyqtgraph.opengl / pyvista), `[fast]` (pyqtgraph),
  `[claude]` (MCP server).
- Look and feel: plain Qt Widgets with the Fusion style and a light/dark
  palette (QSS), no `qfluentwidgets` dependency (section 13, item 6).

## 7. Phases

Each phase ends with tests that run headlessly and, where there is UI, with
screenshots Claude can inspect. No phase starts a new layer before the
previous one has tests.

**Phase 0 — bootstrap (short).** `pyproject.toml`, `src/guiqula` skeleton with
the `_vendor` path shim, `vendor/` wiring (done), `tools/update_vendor.sh`
(done), `git init` + license (done), test harness (`conftest.py` sets offscreen
Qt and plugin path, screenshot fixture, startup-time check), `tools/drive.py`
stub. Install `pytest-qt` and `pyqtgraph` (`platformdirs` 3.10 and `pydantic`
2.8 are already present).

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

**Phase 2 — UI shell and geometry workspace.** Main window with outliner,
viewport, properties, log; plain Qt theme; structure canvas with pan/zoom,
picking, lasso and region creation; lattice picker;
supercell/ribbon/island/remove-atoms ops; autosave, recovery and crash reports.
Acceptance: `tools/drive.py` loads a preset, removes atoms by command, and the
screenshot shows the sculpted geometry; killing the process and restarting
recovers the document.

**Phase 3 — Hamiltonian workspace and results.** Term palette, schema forms
with `f(r)` expressions, invalid-entry flagging with pyqula's messages, job
panel with cancel, result tabs with interactive matplotlib, stale marking on
upstream edits, mean-field block. Acceptance: change the geometry after
setting terms and the bands re-run on the new geometry with the same terms;
cancelling a running job leaves the UI usable.

**Phase 4 — breadth and freedom.** Python nodes with the trust prompt,
embedded console, the rest of the geometry ops and terms, first-wave
calculations, structure-scalar and vector plots, classical spin, lattice-gas
and Ising systems with their palettes, Brillouin-zone canvas, sliders and
sweeps, result overlays, presets gallery from quantum-lattice's modes, project
save/load with results cache, script export for everything.

**Phase 5 — polish.** Undo everywhere, keyboard shortcuts, theming (light and
dark), tooltips and formulas (reuse quantum-lattice's), user guide, example
projects, performance passes (pyqtgraph canvas for large islands).

**Phase 6 — distribution and add-on.** PyPI release, conda file, installers for
Mac/Windows, plugin entry points and a plugin template, JSON-RPC server + MCP
wrapper (the Claude add-on).

### Where the section 13 items land

| Phase | Items |
|---|---|
| 0 | 13.4 vendored layout and path shim; 13.15 startup measured from the first test |
| 1 | 13.1 systems list in the schema; 13.3 headless runner (it is the test driver); regions in the schema (13.2); 14.2 thin UI; 14.3 skip semantics; seeds and `h.copy()` in the engine (3.3) |
| 2 | 13.2 selection tools on the canvas; 13.6 plain Qt theme; 13.14 crash reports |
| 3 | 13.12 cost guard; 13.8 Hamiltonian view (first version: bonds and onsite); Fields: constant, expression, piecewise (section 3.8) |
| 4 | 13.5 classical systems; 13.7 trust prompt (arrives with Python nodes); 14.1 remote console; 13.9 Brillouin-zone canvas; 13.10 sliders and sweeps; 13.11 overlays; Fields: profile, interpolated, painted, from_result (section 3.8) |
| 5 | 13.16 teaching presets and exports; 13.13 in-app help if adopted |

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
ideas (tooltips with physics, formula images, the "pyqula code" view, the
atom picker, the presets) and drops what limited it: one form per mode, `.ui`
files, plotting through `.OUT` files and subprocesses, cwd-based state, a
hand-maintained applicability table. Per decision 5, guiqula does not need to
supersede quantum-lattice; both can coexist.

## 10. Repository conventions (to be kept in CLAUDE.md)

- Upstream pyqula is read-only; only `tools/update_vendor.sh` touches `vendor/`.
- No Qt imports outside `src/guiqula/ui/` and `remote/`. No pyqula imports in
  `core/`, `commands/`, `io/` (they only see the Document).
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
- 13.13, in-app help rendered from the vendored user guide: not decided.
- How a classical texture is handed to a quantum system's exchange term
  (result reference in the Document, or a copied array), and how staleness
  propagates across that link.
- Raised in the 2026-09-26 review (section 14) and not yet decided, with the
  recommendation made there:
  - (review 7) a dedicated *interactive* worker for builds and canvas
    previews, separate from the batch job workers, so a running calculation
    never blocks a geometry edit or a Field preview; recommended, from
    phase 1.
  - (review 8) the build cache lives in worker memory and a cancel kills the
    worker, so every cancel discards it; accept the loss (builds are cheap),
    or keep the cache in the interactive worker and only kill batch workers.
  - (review 9) `run_calculation` is listed as an undoable Command, but running
    is not sensibly undoable; recommended to split *mutations* (undo stack)
    from *actions* (journal only) in the dispatcher from phase 1.
  - (review 10) evaluate expressions with an AST-whitelisted numpy evaluator
    so they are data and only Python nodes need the 13.7 trust prompt;
    recommended (shared presets then open without a prompt, and Field
    evaluation is vectorised).
  - (review 13) `from_result` Fields make the Document a DAG across systems
    and calculations; recommended to make the engine's hashing DAG-aware in
    phase 1 rather than retrofitting it.
  - (review 14) pyqula's `parallel.set_cores` pool forks inside the calling
    process; a daemonic guiqula worker could not start it. Verify in phase 1
    that the worker is non-daemonic and cleans up explicitly on exit.

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
v1" to "classical models included, with their own features", and item 13 left
undecided. Items 1 to 7 touch the Document schema or the package layout; items 8
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

13. **In-app help from the vendored user guide** (undecided). Each registry entry names its
   user-guide anchor; a help panel renders that section. quantum-lattice's
   `TERM_TOOLTIPS` seed the short descriptions.

14. **Crash reports.** On an unexpected error, write a bundle with log,
   traceback, Document snapshot and versions to the user data directory and
   offer to open its folder. A student's bug report then reproduces.

15. **Startup budget.** jax imports in about 0.5 s warm and much more cold,
   numba similar. Keep jax and pyqula out of the UI process entirely (they live
   in the worker), start the worker while the window appears, and measure
   startup in the test suite.

16. **Teaching use.** A preset gallery, one-click export of figure plus data plus
   script, and presets with locked parameters, for use in courses.

## 14. Plan review (2026-09-26)

A read-through of this document against the vendored pyqula before phase 0.
Items keep the numbers of that review so they can be referred to. The
maintainer's answers are recorded here; the verified facts were folded into
sections 3.1, 3.3, 3.8, 6, 7 and 8; the items without an answer yet are at
the end of section 11.

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
