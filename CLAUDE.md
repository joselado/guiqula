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
documentation, whose open design points phase 5 settled), and section 14's
review decisions of the same day (the console is a remote REPL in the worker,
a thin UI already in phase 1, invalid entries are skipped and flagged). Section 11 records
where each of its former open questions was settled, the expression arithmetic of 3.8
last (a comparison is 1.0 or 0.0, confirmed on 2026-09-28), so no design question is open.
Read it before designing anything; update it when a decision changes.

Status (2026-09-26): phases 0 to 3 are done and the maintainer has answered the phase-3
report (PLAN.md section 7 says what each phase built, what was left for later, and the
answers). Phase 4 is done (2026-09-27, in parts 1 to 4b: the breadth of the registry and the
plot kinds, Python nodes, trust and the console, classical systems and `from_result` Fields,
results in projects, presets gallery, overlays, sweeps, sliders, the Brillouin-zone canvas,
the remaining Fields and the brush); the maintainer asked for phase 5 without commenting
on its report, so its items stand as built. Phase 5 (polish) is done (2026-09-27, in four
parts: settings, themes, shortcuts, undo; teaching exports and locks; performance; the in-app
help); its report, numbered design items 1 to 14 and decisions 15 to 24 (PLAN.md section 7,
end of phase 5; items 1 to 7 are the in-app help's recommendations, kept in section 11), was not
commented on (phase 6 was asked for), so its items stand as built. Phase 6 (distribution
and the add-on) is done (2026-09-27, in three parts: remote control and the MCP add-on;
plugins; distribution: README, PyPI metadata, sdist and wheel, conda file, `guiqula
desktop`, icons), and the maintainer answered its report, decisions 25 to 45 (PLAN.md
section 7): a public GitHub repository without CI, pip as the only installer (no frozen
builds), Python 3.12 and 3.13, 0.0.1 as the first release. Phase 7 (calculations from
picks on the plots: the vocabulary, the targets, the new calculations, the markers) is done
(2026-09-28, in three parts); of its report, decisions 55 to 62 (PLAN.md section 7, end of
phase 7), the maintainer answered 55 to 57 (they stand as built) and the others stand as
built. After phase 7, the 3D drawing with pyvista (View > 3D drawing, 2026-09-29; decisions
63 to 70 at the end of PLAN.md's section 7, for the maintainer to confirm), and the look
(2026-09-29: the plot text size, View > Plot text; the check boxes drawn by a proxy style;
the axes centred in their panels; decisions 71 to 79, same place, for the maintainer to
confirm), and moving in space (2026-09-29: Blender's controls in the 3D scene, Inkscape's on
the flat drawings, pyvista the default in the program when installed; decisions 80 to 87,
same place, for the maintainer to confirm), and a detached plot is a window of its own, since a
floating dock could not be moved on Wayland (decision 88, same place), and the bands and the
spectral function on pyqula's default k-path name its high-symmetry points on the axis and walk
pyqula's two-dimensional path with the Γ that it leaves out put first (2026-09-30: decision 89,
same place, for the maintainer to confirm). Phase 8, the interface (the start page, the
Add menus on the outliner, Run where the result is, the panels, the bars, the forms, the
outliner, icons, the documentation), was planned on 2026-10-03 (packages P1 to P9 and
decisions 90 to 106 at the end of PLAN.md's section 7; the maintainer answered 93, the
workspace tabs stay and follow the selection) and built on 2026-10-03 and 2026-10-04 on
branch phase8 by a workflow, package by package; its report, with decisions 107 to 135 for
the maintainer to confirm, closes PLAN.md's section 7, whose P8 paragraph (the icons) is
completed when that package is merged, and section 4 draws the window as built. Nothing
is uploaded or pushed without the maintainer.

## Code map

The flow is Document -> plan -> engine -> worker -> Result -> plot; everything goes through
a `Session`.

- `core/`: `document.py` (pydantic models; ids unique across the document; a quantum
  system's Hamiltonian = construction, terms, mean-field block; a classical system's
  `model` = the model entry's set-up and its terms; `terms_of(system)`; an op, term or
  calculation may have a `name`, left out of the JSON when empty, never in a key), `fields.py` and
  `locks.py` (what a teaching preset locks: an entry, `t1.m`, `s1/geometry`; the
  dispatcher refuses any mutation that changes a locked thing, comparing before and after),
  `expressions.py` (Fields: constant, expression, piecewise over regions, from_result,
  profile, interpolated, painted; the
  AST-whitelisted expression evaluator), `regions.py`, `nearest.py` (the stored point
  nearest to a position within a tolerance, by a cell hash: regions by positions, painted
  and from_result Fields and the canvas selection must use it, never an N x M scan), `results.py` (the `Result` dataclass
  that crosses the process boundary; a result drawn on the atoms carries its geometry in
  `structure`, a map over the zone its reciprocal frame in `kspace`, and the ResultRefs its
  from_result Fields read in `reads`; `ResultRef`, what a from_result Field reads),
  `picks.py` (phase 7: a point of a plot as the values it stands for, in the closed
  vocabulary `QUANTITIES`; a plot spec's `picks` names what its axes carry, `AXES`: kpath,
  kmesh, energy, parameter, frequency, and `fixed`; a result on the atoms yields sites; a
  bands or spectral-function result carries `kpoints`, reduced, (0, 3) in 0D),
  `bonds.py` (a Field known on the sites only, painted,
  from_result or a region by positions, at the bond midpoints where pyqula evaluates the
  parameters declared `FieldParam(bond=True)`: the mean of the two ends, a region holding
  a bond when it holds both), `hashing.py`.
- `registry/`: one declaration per lattice, op, term, mean field and calculation
  (`lattices.py`, `geometry_ops.py`, `terms.py`, `meanfield.py`, `calculations.py`,
  `classical.py` for the classical models, terms and calculations, `python_nodes.py`,
  `sweeps.py`, a calculation that runs another one over parameter values, and `command`,
  the mutation that sets one number of the Document (sliders, picks); `kpaths.py`, the
  points of a k-path, pyqula's default one included, and the names of the points along one;
  `picks.py`, the targets of picked values, computed from the
  parameters' `quantity` and never listed by pairs); an
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
  `window.py` (the window's hooks: screenshots, widget names, its state, which says
  whether the start page shows, `start_page`, and the calculation Run acts on,
  `selected_calculation`); `api.py`'s `plot` titles a figure as the window does, with the
  mark of a state that is not current (`plot_title`), and replies with the state.
- `io/`: project files (a `.guiqula` zip keeps the results too), presets
  (`src/guiqula/presets/*.json`, loadable by name, described by the Document's `notes`),
  script export (a sweep exports a loop), result files, `autosave.py` (autosave and
  recovery), `crashreport.py`, `bundle.py` (Export figure, data and script: one folder
  per result, the figure drawn by the window in the light theme), `settings.py` (the user's theme, plot text size, interface
  text size (`ui_text`), the arrangement of the panels and the window's size (`layout`),
  recent files, always
  trust, remote control, run at once, 3D drawing (pyvista unless matplotlib was chosen or pyvista is missing); the file holds
  only what was set, `settings.chosen`; `$GUIQULA_CONFIG_DIR`; only the interactive program's window,
  `use_settings=True`, reads or writes it, so tests and drivers run with Run at once off unless they turn it on).
- `desktop.py`: `guiqula desktop` (the menu entry, icon and `.guiqula` file type for the
  current user: freedesktop files on Linux, a Start menu shortcut and registry keys on
  Windows, `~/Applications/guiqula.app` on macOS; from a checkout it carries `src/`);
  `env.launcher()` is the command that starts guiqula again. `resources/`: the icon (SVG;
  PNG, ICO, ICNS made by `tools/make_icons.py`), `thumbnails/` (the pictures of the start
  page and the gallery, `lattices/`, `classical/`, `presets/`, PNG files made by
  `tools/make_thumbnails.py` and shipped as package data; `tests/ui/test_start.py` fails
  for a lattice, a classical system or a preset without one), and `icons/` (phase 8, P8:
  the Tabler Icons of the controls, SVG with `currentColor`, their MIT licence and a
  README of the names).
- `packaging/README.md`: what each distribution is (pip only: sdist and wheel, the conda
  file, `guiqula desktop`), what was verified, the release checklist (built and uploaded by
  hand; there is no CI).
- `ui/`: `mainwindow.py` (the window as PLAN.md section 4 draws it since phase 8: the first
  toolbar row of the workspace tabs, which follow the selection (`workspace_of`), New
  system and Add (`PaletteMenu`s, which the outliner's "+" open too, `open_add_menu`) and
  the run controls (`runButton` names `selected_calculation()`, the outliner's
  calculation, else the tab's, else the first; its `runMenu`, `cancelButton`, Follow);
  `centralStack`, the start page in the viewport's place while the document has no system
  (`show_start`); the panels, `Dock`s without a float button, Properties over Help,
  Sliders and Jobs, the Log and the Console hidden behind the status bar's `logToggle`,
  View > Panels, Reset layout and Interface text, the arrangement kept in the settings
  (`layout`, `LAYOUT_VERSION`); one result view per calculation, whose tab, status row and
  outliner row read one state (`_result_state`, `marks.calculation_state`); the cost
  guard, auto re-run; the window's own
  dispatcher actions `select`, `workspace`, `tool`, `select_sites`, `region_from_selection`,
  `remove_selected`, `canvas_view`, `preview`, `auto_rerun`, `projection`, `overlay`,
  `slider`, `set_slider`, `remove_slider`, `paint`, `theme`, `export_bundle`, `help`,
  `remote`, `pick`, `pick_to`, `run_at_once`, `renderer_3d`, `view_3d`, `plot_text`,
  `ui_text`, `reset_layout`, `log`, `panel`, `add_menu`, `run_stale`, `start`, `run`; a new
  one joins `remote/api.py`'s `WINDOW_ACTIONS` and `tools/drive.py`'s help (tests check
  both); File > Allow remote control starts the server, polled from the window's
  timer; a pick emits ordinary commands, and the pick menu is built by `pick_menu` and
  shown with `popup()`, never `exec()`; `pick` and `pick_to` take a calculation and a
  point, or `system` and `values`: the k-space tab's click, Calculate on selection),
  `start.py` (the start page, `startPage`: the lattices, the examples and the recent files
  as cards with the pictures of `resources/thumbnails/`, read when a card comes into sight,
  a filter, Show all; `preset_card` makes the gallery's cards too), `palette.py`
  (`PaletteMenu`, the Add menu of one family: a search line, the entries by group,
  `search_entries`, Enter adding the best match; `MenuButton`, which opens its menu with
  `popup()`), `canvasbar.py` (`CanvasBar`, the bar of a drawing: Fit, Pan, Zoom, the
  drawing's tools and Save image, in groups that wrap onto further lines, over a hidden
  `NavigationToolbar2QT` kept as `canvas.toolbar`, `HiddenToolbar`, whose mode
  `CanvasNavigation` and the tests read), `marks.py` (the marks of a state, one set for the
  outliner, the result tabs and the status row: `mark`, `calculation_state`; no Qt),
  `icons.py` (phase 8, P8: `icon(name)`, an SVG of `resources/icons/` tinted with the
  theme's colour, cached per theme, `on_theme_change`),
  `help.py` (the Help panel, below Properties: F1, a form's ?, the guides; Markdown in a QTextBrowser, whose
  `loadResource` serves the equations), `shortcuts.py` (the one
  table of keyboard shortcuts: menus, the canvas and outliner keys, the dialog; a test
  refuses ambiguous keys), `outliner.py` (the tree: a "+" on each section row,
  `outlinerAdd_<system>_<section>` and `outlinerAdd_calculations`, `add_requested`; a label
  that says what the row is, a Status column that holds the state only and is as wide as
  its longest text, `status_width`; the system and the mean field as detail rows across
  both columns), `gallery.py`
  (presets, the start page's cards), `sliders.py` (the Sliders panel; `range_from`, the
  range a label's menu gives a slider or a sweep), `kspace.py` (the Brillouin-zone canvas,
  its tab hidden for a system without a periodic direction),
  `properties.py` + `forms.py` (forms from the parameter declarations, in the words of the
  physics: the label's menu `paramMenu_<p>` (Lock, Attach a slider, Sweep this parameter,
  Preview on the canvas), the region link, a calculation's estimate and `formRun`, the
  system form's spin, Nambu, hopping range and sparse; the Field editor, whose button
  shows the kind and opens the kind menu `fieldKindMenu_<p>`), `formulas.py` (mathtext
  images; rich tooltips of the Add menus), `structure.py`
  (canvas, its three views, its bar `structureBar` with the
  selection tools, and the mplot3d drawing of geometries that are not flat), `pyvista_view.py`
  (the 3D drawing with pyvista, View > 3D drawing, the `renderer_3d` action and setting:
  rendered off-screen and painted as an image, moved as Blender's viewport is, the widget
  applying the mouse and the numpad to a `navigation.Turntable` and setting the camera,
  `SceneCanvas.send`/`drag` without a mouse, `SceneView.set_view` and the `view_3d` action;
  pyvista imported at the first drawing, never at startup; the canvas and each `PlotView`
  swap their matplotlib canvas for its `SceneView`, whose Reset view, View and Save image
  go into the drawing's bar, and a result on the atoms follows the
  canvas's projection), `navigation.py` (the arithmetic of moving, without Qt, VTK or
  matplotlib: `Turntable`, the limits of a flat view, `ZoomHistory`), `canvas_navigation.py`
  (Inkscape's controls on a matplotlib canvas, `CanvasNavigation`, on the structure canvas
  and the results drawn flat on the atoms; `bind_keys` makes the QShortcuts of the table's
  "2D canvas" context; the "3D canvas" keys are the scene's own `keyPressEvent`), `plots.py`
  (`PlotView` per calculation, `plot_<id>`, with its bar `plotBar_<id>` and its status row
  `plotStatus_<id>` (stale with Run again, queued or running with the progress and Cancel,
  failed; `ROW_STATES`), and `ResultWindow`, the plain window of a detached one, never a floating dock, which Wayland cannot move; lines, colored_scatter, heatmap,
  structure_scalar, structure_vector, scalar; the right click, the Pick, Box and Lasso
  toggles, `pick_requested`; the markers, sliders with `on` drawn by `set_markers` and
  dragged through `marker_moved`), `jobpanel.py`,
  `console.py` (the console panel), `bars.py` (recovery, error, cost and trust bars;
  `StatusMessage`, the last message in the status bar),
  `errors.py` (exception hook), `theme.py` (light and dark: the colour names are the active
  theme's, rebound by `apply`; every figure is drawn inside `theme.drawing(figure)`, whose
  rc carries the plot text size, `text_size`, View > Plot text; the interface text,
  `UI_POINTS` and `set_ui_text`, View > Interface text; `CheckStyle`, the proxy
  style drawing the check boxes; `centre` and `Centring`, the axes box kept in the middle
  of its figure after every draw). The
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

## Good practices for the interface

What the phase-8 plan (PLAN.md section 7) was made from, kept here so that any change of
`ui/` follows it; the first five are how the interface is designed, the rest how it is
built and checked.

- Put the action where its effect appears: a "+" on the outliner section the entry will
  join, Run on the result it computes, a slider on the parameter it moves. A control a row
  or a dock away from what it acts on is what the user cannot find.
- Let the window follow the selection: the workspace, the viewport tab and the help
  follow what was selected or added, and never ask the user to find the right tab first.
- One place to choose a thing: a calculation is chosen in the outliner or by its tab, not
  in a third widget; a duplicate selector is a place to be out of sync.
- The form speaks the physics and the tooltip speaks the engine: "spinful", "superconducting
  (Nambu)", "hopping range" on the label, "add_zeeman", "requested", "sparse" in the tooltip
  and the help.
- An empty state says what to do next, in one line, where the thing will appear (the start
  page when there is no system, the plot caption when nothing was run).
- Look before designing: drive the window offscreen with `tools/drive.py` at 1200x800 (the
  small laptop) and 1600x1000, on the shipped presets, in both themes, and read the
  screenshots; let the layout settle first (ten rounds of `processEvents` and
  `QTest.qWait(100)`, as `tools/readme_images.py` does), since an unsettled grab draws
  dock tab bars twice.
- A widget's `objectName` is an API: the tests, `drive.py --widget`, the remote
  `screenshot` and `widgets` methods and the examples in this file name them. Keep a name
  when the widget moves; list every rename in the report.
- A behaviour is an action, not a click: anything the window can do is a window action in
  `WINDOW_ACTIONS` (both lists) with a `drive.py` example, so that it can be driven and
  tested without the mouse; a new key goes in `ui/shortcuts.py` and the tooltip names it
  through `shortcuts.text`.
- The Add menus, the start page's lattices, the forms, the tooltips and the help are
  generated from the registry declarations: a control that lists physics entries reads `registry.entries(family)`,
  never a hand-written list, so a plugin's entries appear in it too.
- The UI process stays light: pictures are PNG files made by a tool script and shipped,
  never computed in the window; `tests/ui/test_startup.py` keeps the 2 s budget and the
  module set.
- Replace a look, keep the instance: the matplotlib toolbar stays, hidden, behind guiqula's
  own buttons, since `CanvasNavigation` and the tests read its mode; the Inkscape and
  Blender controls of the drawings are not touched by a change of bars.
- Nothing floats: a detached thing is a plain window, since a floating dock cannot be moved
  on Wayland (decision 88).
- Layout is tested, not eyeballed: a test checks that no toolbar shows its extension
  chevron at 1200 px and no outliner status is elided at the default width, on every
  preset; every control has a tooltip (`test_every_toolbar_control_and_palette_entry_has_a_tooltip`).
- Acceptance is a named screenshot: each change states the `drive.py` command, the preset,
  the size and the theme that show it, so the maintainer can reproduce it and the next
  agent can check it.
- Work is cut by file ownership: `ui/mainwindow.py` is the shared file, so the packages
  that rewrite parts of it go one after another and the file owners (`forms.py`,
  `structure.py`, `outliner.py`, a new module) go in parallel in worktrees, merged in a
  fixed order with the suite run after each merge.
- Decisions go in PLAN.md, numbered, the recommended option first; they stand as built
  unless the maintainer answers. The documentation (`docs/user_guide.md`, README, this
  file's code map and examples) is the last package of any change, in the voice of
  `~/.claude/CLAUDE.md`.

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

The interpreter on `PATH` is anaconda's base Python 3.14.6 with PySide6 6.11.0 (2026-09-28),
which is outside the declared 3.12 and 3.13; the whole suite passes on it. Offscreen
rendering works, but the platform plugin is only found when its path is given explicitly:

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
`tools/drive.py` and `guiqula --offscreen` call it. `pytest-qt` 4.5.0 is installed in it
(without it every test using `qapp` or `qtbot` errors at setup); `pyqtgraph`, the `fast`
extra, is not, and no test needs it. pyvista 0.48.4 with VTK 9.6.2, the `3d` extra, is
installed (`tests/ui/test_pyvista_view.py` skips without it); it renders off-screen through
XWayland here and falls back to EGL by itself without a display, while a VTK widget
embedded in Qt (`QVTKRenderWindowInteractor`) segfaults on the offscreen platform, which
is why `ui/pyvista_view.py` paints an image instead. `tests/ui/test_startup.py`'s 2.0 s budget is tight on
this interpreter: it passes on a quiet machine, but the start took 2.2 to 3.0 s at a load
average of about 5 and 3.6 s at 16 (2026-09-28), so a failure there under load is the
load before it is the code.

## Commands

Nothing is installed: pytest puts `src/` on the path (`pyproject.toml`), and `tools/drive.py`
and the launcher `./guiqula` do it themselves (the launcher also through `PYTHONPATH`, for
what `env.launcher()` starts, and its `__main__` guard is what keeps the spawned workers
from running `main()` again). Keep this section in sync with what exists.

```bash
python -m pytest                       # everything (offscreen Qt, worker processes; about
                                       # 30 min on this machine since phase 8)
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
python tools/drive.py --no-session --widget startPage --shot start.png   # the start page
python tools/drive.py --no-warm --do '{"do": "start", "search": "kagome"}' --shot kagome.png
                                                   # its filter, on an empty document
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "add_menu", "section": "s1/hamiltonian",
    "search": "spin"}' --widget paletteMenu_term --shot terms.png   # the "+" of a section
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "select", "entry": "c2"}' \
    --widget runButton --shot run.png              # Run names what it runs ("Run c2 · dos")
python tools/drive.py honeycomb_zeeman_rashba --run c1 --python "session.do('set_param', \
    entry='t1', name='m', value=[0, 0, 0.3])" --widget plotStatus_c1 --shot stale.png
                                                   # the status row of a stale result
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "log"}' --do '{"do": "ui_text",
    "name": "large"}' --shot large_text.png        # the Log toggle, the interface text
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "canvas_view", "name": "hamiltonian"}' \
    --widget structureView --shot hview.png        # the Hamiltonian view (13.8)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "preview", "entry": "t1", "param": "m"}' \
    --widget structureView --shot field.png        # a Field on the structure
python tools/drive.py honeycomb_hubbard --run c1 --widget plot_c1 --shot hubbard.png   # mean field
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "console", "code": "h.get_gap()"}'
                                                   # the console; its output is in the report
python tools/drive.py project.guiqula --trust ...   # run the Python nodes of a file (13.7)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "theme", "name": "dark"}' --shot dark.png
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "plot_text", "name": "large"}' \
    --run c1 --widget plot_c1 --shot large.png     # the plot text size (small, normal, large)
python tools/drive.py honeycomb_hubbard --do '{"do": "renderer_3d", "name": "pyvista"}' \
    --do '{"do": "projection", "name": "3d"}' --do '{"do": "add_calculation", "system": "s1",
    "kind": "magnetization", "params": {"nk": 4}}' --run c3 --widget plot_c3 --shot m.png
                                                   # the 3D drawing with pyvista
python tools/drive.py preset --do '{"do": "set_param", ...}' --do '{"do": "undo"}'
                                                   # undo, redo (steps), history
python tools/drive.py honeycomb_hubbard --do '{"do": "renderer_3d", "name": "pyvista"}' \
    --do '{"do": "projection", "name": "3d"}' --do '{"do": "view_3d", "name": "top"}' \
    --widget structureScene --shot top.png             # Blender's views: front, right, top, ...
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "select", "entry": "t1"}' \
    --do '{"do": "help"}' --widget helpDock --shot help.png   # an entry's help (13.13)
python tools/drive.py honeycomb_zeeman_rashba --run c1 \
    --python "session.act('export_bundle', calculation='c1', path='out/c1_bands')"
                                                   # figure, data, script in one folder
                                                   # (--do runs before --run, --python after)
python tools/drive.py honeycomb_zeeman_rashba --run c1 --python "session.act('run_at_once'); \
    p = session.act('pick', calculation='c1', x=20, y=0.5); print(p['label'], \
    [t['label'] for t in p['targets']]); session.act('pick_to', calculation='c1', x=20, \
    y=0.5, target=0)"                              # a pick on the bands (phase 7)
PYTHONPATH=src python -m guiqula --remote preset      # the window, remote control on (3.7)
PYTHONPATH=src python -m guiqula serve preset         # a session without a window, remotely driven
PYTHONPATH=src python -m guiqula mcp [--attach|--headless] [--document D]   # the MCP add-on
claude mcp add guiqula -e PYTHONPATH=$PWD/src -- python -m guiqula mcp  # register it (checkout)
<python with the mcp SDK> tools/mcp_check.py --python $(which python)  # the SDK's client vs mcp
PYTHONPATH=src python -m guiqula desktop [--remove]   # menu entry, icon, file type (this user)
python -m build && twine check --strict dist/*   # sdist and wheel (packaging/README.md)
python tools/make_icons.py             # the PNG, ICO and ICNS from resources/guiqula.svg
python tools/make_thumbnails.py [name ...]   # the start page's pictures (resources/thumbnails),
                                             # after a new lattice, classical system or preset
python tools/readme_images.py [name ...]   # the README's screenshots (docs/images), by drive.py
tools/update_vendor.sh /path/to/pyqula  # refresh vendor/ from upstream pyqula ($PYQULA_SRC)
```

`drive.py` prints a JSON report last (document outline, builds, jobs, result summaries,
canvas view, tab shown, open result views, the calculation Run acts on, whether the start
page shows, selection, undo steps, log tail, screenshot path); a `--do`
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
