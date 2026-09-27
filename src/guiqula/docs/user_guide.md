# guiqula user guide

guiqula is a graphical workbench for pyqula: one window in which a geometry, the terms of
a Hamiltonian and the calculations on it are put together, changed in any order, and
computed by pyqula. This guide describes the program. The physics, and what each pyqula
function does, is in pyqula's own user guide (Help > pyqula user guide), which the help
of every entry quotes (F1).

## Getting started

Install it with `pip install guiqula` (or `pipx install guiqula`) and start the program
with `guiqula` (from a source checkout,
`PYTHONPATH=src python -m guiqula`), optionally followed by a project file or the name of a
preset. `guiqula desktop` adds it to the desktop's application menu, with its icon, and
lets `.guiqula` files open with it (`guiqula desktop --remove` undoes it). File > Presets
gallery opens a ready-made document: pick one, press Open, then Run (F5) to compute its
selected calculation. Everything in a preset can be changed.

A document holds one or more systems (a geometry and its Hamiltonian, or a classical
model) and the calculations on them. Build one from scratch with New system on the
Geometry toolbar: choose a lattice, add geometry ops (a supercell, a ribbon, an island),
switch to the Hamiltonian workspace to add terms, and to the Calculate workspace to add a
calculation and run it.

## The window

- The workspace tabs (Geometry, Hamiltonian, Calculate) change the toolbar and the canvas
  view, not the document.
- The outliner (left) is the whole document as a tree: for each system its lattice and
  geometry ops, its regions, its terms with the Hilbert space after each (spinless,
  spinful, Nambu) and its mean field; then the calculations with their status (none,
  queued, running, done, stale, failed). A check box enables or disables an entry, a
  drag reorders it, the context menu duplicates, deletes, locks or runs it.
- The viewport (centre) has the Structure tab (the geometry, or the Hamiltonian, or a
  Field, drawn on the atoms), the k-space tab (the Brillouin zone and the k-path), and a
  tab per calculation's result.
- Properties (right) is the form of the selected entry; Help, next to it, its help.
- Jobs and Sliders (right), Log and Console (bottom).
- The status bar shows the selected system (dimension, sites, Hilbert space) and the
  estimated duration of the selected calculation.

Every change goes through a command, so it can be undone (Edit > Undo), it is saved with
the project, and it can be driven from the console or a script.

## Systems and geometry

New system makes a quantum system on a lattice; New classical system makes classical
spins, a lattice gas or an Ising model. A document may hold several systems (a texture
computed on one can drive another, see Fields). The geometry is the lattice followed by
its ops, applied in order: changing an op, or the lattice, rebuilds everything after it
and keeps the terms. Ops that act on positions (keep or remove sites where a condition
holds, remove atoms) store positions or expressions, not indices, so they survive a
change of the supercell. A geometry that is not flat is drawn in 3D; the 3D box on the
canvas toolbar switches to the xy projection, where the selection tools work.

## Selections and regions

On the Structure tab the pick, box and lasso tools select sites (shift adds, ctrl
toggles); the Select menu selects all, a sublattice, the edge sites (fewer neighbours
than the rest) or the inverse. The pan and zoom buttons of the canvas toolbar take the
clicks while they are on (Pick, Box and Lasso then show unchecked): click one of those three
to select again; the mouse wheel zooms at any time. With sites selected:

- Remove selected adds (or extends) a Remove atoms op that deletes them by position;
- Region from selection makes a named region of their positions.

A region can also be an expression of x, y, z and r (Add region). A term restricted to a
region (the region box of its form) acts only there; a Field can take one value per
region (piecewise). A region is kept by position, so it follows the geometry as long as
its sites are still there. A term between sites (Rashba, Haldane, Kane-Mele, Kekule, a
pairing, the hopping modulation) restricted to a region made of selected sites acts on
the bonds whose two ends are in it; an expression region holds the bonds whose midpoint
it holds.

## Terms and the Hamiltonian

The Hamiltonian workspace offers the terms by group (onsite, magnetism, spin-orbit,
topology, superconductivity, fields, disorder); the search box (Ctrl+F) finds one by
name. Terms are applied in order to the Hamiltonian that the construction (the system's
form) starts: first-neighbour hopping, or the hoppings to further neighbours given there.
Before building, guiqula fixes the Hilbert space from the whole stack (a Zeeman field
needs spin, a pairing needs Nambu), so no term upgrades it halfway.

A term pyqula refuses is flagged in red with pyqula's message and skipped; the rest of the
stack still builds, and a result computed without it says so. The Hamiltonian view of the
canvas (Show: Hamiltonian) draws what the terms did: the atoms coloured by their onsite
energy, every hopping with a width following its amplitude and a colour following its
phase, exchange fields as arrows.

## Fields: parameters that depend on the position

Every number of a term is a Field. The f(r) button next to it opens the Field editor:

- a number, or an expression of x, y, z and r (numpy functions such as sin, exp, tanh,
  sqrt, abs, and pi); a comparison is 1 where it holds and 0 elsewhere, so
  `0.2*((x > 0) - (x < 0))` is a step, and `&`, `|` and `~` combine comparisons
  (and, or, not);
- piecewise: one value per region and a default elsewhere;
- a profile (gaussian, step, disk, plane wave, Aubry-Andre, domain wall) with its numbers;
- interpolated between control points;
- painted: the Paint tool of the canvas paints a value on the sites under the brush;
- from a result: an array of another system's result, site by site (a classical spin
  texture as the exchange field of an electronic system).

While a Field is being edited the canvas previews it on the atoms. A parameter that
pyqula takes as a number only is marked constant: it accepts no function of position.
pyqula evaluates the Field of a term between sites at the middle of each bond: a painted
or from-result Field gives a bond the mean of the values at its two ends.

## The mean field

The mean-field block closes a system's Hamiltonian: the interactions (a Hubbard U, which
can depend on the position, and neighbour interactions V1 to V3 and exchange J1 to J3)
solved self-consistently from an initial guess, at a filling or a chemical potential. It
runs with the calculations, not while editing, and a calculation whose mean field does not
converge fails rather than silently using the non-interacting Hamiltonian. The engine
(numpy or jax), the solver, the mixing and the temperature are in its form; empty means
the engine's own default.

## Classical systems

A classical system has a Model in place of a Hamiltonian: classical spins, a lattice gas
at a filling, or an Ising model, set up on the system's geometry, with its own terms
(exchange shells, fields, chemical potentials, exchange tensors) and calculations
(minimizing the spins, annealing the gas or the Ising model). Their results are drawn on
the atoms, and a from-result Field hands them to another system.

## Calculations and results

The Calculate workspace offers the calculations by group. Run (F5) sends the selected one
to a worker process, so the window stays responsive; the Jobs dock shows its progress and
Cancel stops it. Each result has its own tab: the plot (zoom and pan with its toolbar), a
readout of the point under the mouse, Save data, Export, Detach (a window of its own) and
Overlay. A result becomes stale (its tab and the outliner say so) when anything it depends
on changes; Run computes it again. Run > Re-run cheap results automatically does that for
results estimated under three seconds. Before a run estimated above a minute, a bar asks.

An undo, or a value set back, makes the earlier result that matches the document current
again, without a re-run.

## Sweeps and sliders

A Sweep is a calculation that runs another one at every value of a parameter (or on a grid
of two) and draws the numbers it gives: the gap against a field, a Chern number against
two couplings. Name the calculation, the entry holding the parameter (a term, an op, a
calculation, `<system>/meanfield`, `<system>/model`, or the system for its lattice), the
parameter and its range. A range the parameter cannot take (a filling above 1) is refused,
and a sweep fails at a value pyqula rejects: no point is computed without its entry.

The Sliders dock attaches a slider to any number of the document: dragging it changes the
parameter (one undo step per drag), and with the automatic re-run on, cheap results follow.

## Overlays and exports

The Overlay menu of a result draws another result on the same axes, or the difference of
two curves on the same grid. Export (Ctrl+Shift+E) writes one folder with the figure as PNG
and PDF (on white, whatever the theme), the arrays (.npz, and .csv for curves), the pyqula
script that computes them and the document; File > Export pyqula script (Ctrl+E) writes
the script alone. The scripts use pyqula only, not guiqula.

## The k-space tab

The k-space tab draws the Brillouin zone of the selected system with the high-symmetry
points pyqula knows for it, pyqula's default path (dashed) and the k-path of the chosen
calculation. Add points appends vertices (they snap onto the high-symmetry points); with
it on, a click on a vertex of the path adds that point again, so a path can pass twice
through a point (Γ K M Γ). A vertex can be dragged, Remove last removes one, and Default
path goes back to pyqula's. The k-path of a calculation's form takes the same path as text
(`G K M G`). The latest Fermi surface of the system is drawn underneath. A
three-dimensional lattice is drawn by the k3 = 0 cut of its zone (the plane of b1 and b2)
with the high-symmetry points in that plane; a path that leaves the plane (pyqula's
default one, or `Z` typed in the form) is drawn projected onto it.

## Python nodes, trust and the console

A Python op, term or calculation runs its code in the worker with `g` (the geometry), `h`
(the Hamiltonian), `np` and `pyqula`: whatever pyqula can do and the palettes do not offer.
An error flags the node with the line of its code and the rest carries on. A calculation
sets `arrays`, numbers and arrays of numbers (what a project file keeps), and may set
`plot`; a plot that does not fit its arrays is refused when the code runs.

A document built in the program, or a shipped preset, is trusted. A file opened with
Python nodes is not: its nodes are skipped until you trust it (the bar at the top, or
File > Trust the Python code), since opening a file must not run code someone else wrote.
File > Always trust Python code in files turns that off for your files.

The Console dock runs Python in its own worker, with `doc`, `g` and `h` of the selected
system, `do(command, ...)` for commands (undoable, like any edit), `np` and `pyqula`.
Interrupt stops it and starts afresh.

## Projects, presets and locks

File > Save writes a `.guiqula` project (the document and its results; a `.json` file
holds the document alone). New, Open, the gallery's Open and Recover replace the document:
with unsaved changes they first ask, as Quit does, whether to save them. The program
autosaves; after a crash, the next start offers to recover the unsaved work. The presets
gallery (File > Presets gallery) lists the shipped documents: teaching presets, with some
parameters locked, and examples.

A lock keeps an entry, one parameter of it, or a system's geometry from changing: its
fields are greyed out and commands that would change it are refused. Right-click a
parameter's label to lock or unlock it; the outliner's context menu locks an entry or a
geometry; Edit > Unlock everything lifts them all. Locks guide an exercise, they are not a
protection.

## Undo, themes and settings

Edit > Undo and Redo say which step they take back; Edit > Undo history goes back several
steps at once, and the selection follows. What is shown (the selection, the workspace,
the sliders, the overlays, the theme) is not undone. View > Theme chooses light, dark or
the desktop's scheme. The settings (theme, recent files, always trust, remote control)
are a file in the user configuration directory.

## Headless use

The same engine runs without the window:

```
guiqula run project.guiqula --calc c1 --out results --script
guiqula script honeycomb_zeeman_rashba --calc c1
```

`run` computes a calculation of a project or preset and writes its arrays (and, with
`--script`, the pyqula script); `script` prints the same script. Both read the results a
project file keeps, which a from-result Field reads. A file with Python nodes
needs `--trust`.

## Remote control and the Claude add-on

Other programs on the same computer can drive guiqula, and Claude (Claude Code, or any
MCP client) can drive it through them. File > Allow remote control (or `guiqula --remote`
for one run) makes the window listen on a local port; `guiqula serve project.guiqula`
does the same without a window. The port and a secret token are written to a connection
file in the user data directory that only the user can read, and a client must present
the token first. What a client does goes through the same commands as the window: it is
undoable, it shows in the window at once, and locks refuse it. A client with the token
can do anything the user can, including running Python in the console, so remote control
is off by default.

`guiqula mcp` is the add-on: an MCP server on standard input and output whose tools
(status, catalogue, command, run_calculation, result, plot, screenshot, help, script,
console...) drive the newest running window, or, when none runs, a session of its own
without a window. Register it with Claude Code once:

```
claude mcp add guiqula -- guiqula mcp
```

From a source checkout, give the interpreter and the path instead:
`claude mcp add guiqula -e PYTHONPATH=/path/to/guiqula/src -- python -m guiqula mcp`.
Its `connect` tool lists the running windows, attaches to one, or opens one.

Scripts can use the same port with `guiqula.remote.client`:

```python
from guiqula.remote.client import connect
with connect() as client:
    client.call("do", command="add_term", args={"system": "s1", "kind": "haldane"})
    print(client.call("run", calculation="c1")["result"]["arrays"])
```

## Plugins

A plugin is a Python package that adds lattices, geometry operations, terms, mean fields,
classical models or calculations; once installed in guiqula's environment (`pip install
guiqula-something`), its entries appear in the palettes, forms, help and exported scripts
like guiqula's own, and run in the workers. Help > Plugins lists the plugins found, what
each added, and any that failed to load: such a plugin is left out and guiqula starts
without it (`GUIQULA_NO_PLUGINS=1 guiqula` starts without any). A document records which
plugin, and which version of it, each of its entries came from, and Help > Plugins lists
the plugins the open document uses. A document that uses an entry of a plugin that is not
installed still opens; that entry is skipped and flagged with the plugin's name, which is
what to `pip install`.

The quickest plugin is one Python file in the `plugins` folder of the user configuration
directory (Help > Plugins shows where): each `*.py` there that declares entries with
`guiqula.registry.entry(...)` is loaded at start. To share one, make it a package: copy
`plugin_template/` from guiqula's source, whose module is named in the entry point group
`guiqula.plugins` of its `pyproject.toml`, with a test that compares each entry with a
direct pyqula call; its README says what to change. Either way, import pyqula inside
functions only: the window loads the plugin too, and must start without pyqula.

## Keyboard shortcuts

| where | keys | what |
|---|---|---|
| window | Ctrl+N | new document |
| window | Ctrl+O | open a project |
| window | Ctrl+Shift+O | presets gallery |
| window | Ctrl+S | save |
| window | Ctrl+Shift+S | save as |
| window | Ctrl+E | export the pyqula script of the selected calculation |
| window | Ctrl+Shift+E | export the figure, data and script of the selected calculation's result |
| window | Ctrl+Q | quit |
| window | Ctrl+Z | undo |
| window | Ctrl+Shift+Z, Ctrl+Y | redo |
| window | Ctrl+1 | Geometry workspace |
| window | Ctrl+2 | Hamiltonian (or Model) workspace |
| window | Ctrl+3 | Calculate workspace |
| window | Ctrl+F | search the palette of the workspace (ops, terms or calculations) |
| window | Ctrl+0 | show the Structure tab |
| window | Ctrl+W | close the result tab shown |
| window | F5 | run the selected calculation |
| window | Esc | cancel the selected calculation's job |
| window | Ctrl+/ | this list of shortcuts |
| window | F1 | help on the selected entry |
| outliner | Del | delete the selected entry |
| outliner | F2 | rename the selected entry |
| outliner | Ctrl+D | duplicate the selected entry |
| outliner | Alt+Up | move the selected entry up |
| outliner | Alt+Down | move the selected entry down |
| canvas | P | pick tool (click an atom) |
| canvas | B | box selection tool |
| canvas | L | lasso selection tool |
| canvas | Ctrl+A | select every site |
| canvas | Ctrl+Shift+A | select nothing |
| canvas | Ctrl+I | invert the selection |
| canvas | Del, Backspace | remove the selected atoms (a Remove atoms op) |
| canvas | Home | show the whole geometry |
| console | Return | run the input |
| console | Shift+Return | a new line in the input |
| console | Up, Down | walk the history |
| code editor | Ctrl+Return | apply the code of a Python node |

The canvas and outliner keys work while that widget has the focus (click it first).

## Getting help

F1, or the ? button of a form, shows the help of the selected entry in the Help dock: its
formula and parameters, the pyqula code it runs with the current values, the docstrings of
the pyqula functions behind it, and the sections of pyqula's user guide about it. Help >
pyqula user guide and Help > guiqula user guide open the whole texts.
