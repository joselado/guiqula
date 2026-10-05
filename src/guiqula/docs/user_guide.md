# guiqula user guide

guiqula is a graphical workbench for pyqula: one window in which a geometry, the terms of
a Hamiltonian and the calculations on it are put together, changed in any order, and
computed by pyqula. This guide describes the program. The physics, and what each pyqula
function does, is in pyqula's own user guide (Help > pyqula user guide), which the help
of every entry quotes (F1).

## Getting started

Install it with `pip install guiqula` (or `pipx install guiqula`) and start the program
with `guiqula` (from a source checkout, `PYTHONPATH=src python -m guiqula`), optionally
followed by a project file or the name of a preset. `guiqula desktop` adds it to the
desktop's application menu, with its icon, and lets `.guiqula` files open with it
(`guiqula desktop --remove` undoes it).

The program opens on the start page, which stands in the place of the drawings as long as
the document has no system. It has three bands: the lattices (by dimension, the classical
systems last) and the examples (the shipped presets, the two teaching ones first) as cards
with pictures, and the recent files, with Open a project... for the others; a filter box
at the top, with the focus when the page first shows, narrows the three at once to what
matches every word typed. The lattices and the examples show their first row, and the
recent files their first three, until the band's Show all is pressed or the filter holds
text. A lattice card makes a new system on that lattice, a classical card makes classical
spins, a lattice gas or an Ising model, and an example card opens that document; a line
at the foot of the page says what comes next and links to this guide. Tab walks the
filter, each band's Show all and its cards in their order, Open a project... and the
recent files, and Enter or Space presses the card that has the focus. File > New brings
the page back, and File > Presets gallery shows the same examples in a dialog, with the
whole description of the one selected.

A document holds one or more systems (a geometry and its Hamiltonian, or a classical
model) and the calculations on them. The simplest way in is an example: open one, select
a calculation in the outliner and press Run (F5), then change anything in it and run
again. From scratch, the way we do this is by choosing a lattice on the start page, then
adding geometry ops (a supercell, a ribbon, an island) with the "+" of the system's
Geometry row in the outliner, terms with the "+" of its Hamiltonian row, a calculation
with the "+" of the Calculations row, and pressing Run, which names the calculation it
computes. F1 explains whatever is selected.

## The window

The window is one document seen through four places: the outliner on the left, the
drawings in the centre, the form of the selected entry on the right with its help below
it, and the status bar at the bottom. Above them, the first toolbar row holds the
workspace tabs (Geometry, Hamiltonian, Calculate; the middle one reads Model for a
classical system), New system, Add and the run controls. New system, Add and Run show
their names beside their icons; Cancel, a filled square, and Follow, two arrows in a loop,
show the icon alone, and their tooltips name them, as for every control that shows only an
icon. The icons are drawn in the text colour of the theme, so they change with it, and
greyed with the control when it is disabled. The workspaces follow the
selection, meaning that selecting a system, its lattice, an op or a region shows Geometry,
a term, the mean field or a model shows Hamiltonian, and a calculation shows Calculate,
and since adding an entry selects it, an add shows its workspace too. A workspace changes
what Add lists and how the Structure tab draws the system (the sites and bonds, or the
Hamiltonian), never the document; Ctrl+1 to Ctrl+3 choose one by hand.

Every change goes through a command, so it can be undone (Edit > Undo), it is saved with
the project, and it can be driven from the console or a script.

### Adding entries

An entry is added from the place where it will appear. Each section row of the outliner
(a system's Geometry, Regions, Hamiltonian or Model, and Calculations) has a "+" at its
right, which opens the menu of that family for that system: a search line at the top,
then the entries by group, each with its formula and its one-line description in the
tooltip. Typing narrows the list to the entries that match and draws the best match in
bold, Enter adds it, and the arrow keys reach the others. The menu of the Hamiltonian
ends with Mean field (interactions), which turns the system's mean-field block on and
selects it, and the menu of the Regions row offers a region by expression and a region
from the sites selected on the canvas. Add, on the toolbar, is the same menu for the
workspace shown and the current system (Ctrl+F opens it with the search line ready, or
New system while the document has no system), and New system lists the lattices by
dimension with the classical systems in its last section. With several systems, the "+"
of a system's section adds to that system, while Add and the "+" of Calculations add to
the system of the selected entry (the first one when nothing is selected).

### Running a calculation

Run reads "Run c1 · bands": it acts on the calculation selected in the outliner, else the
one whose result tab is shown, else the first. Showing the tab of a result while another
calculation is selected selects the result's calculation, so the outliner, the tab and Run
never name two different ones, while a term or an op that is selected keeps its form on
screen as results are looked at, and Run then follows the tab. The arrow beside Run lists
the other calculations and Run every stale result; Cancel (the filled square) stops the
job of the calculation Run names, and Follow (the two arrows) is Run > Re-run cheap results
automatically (see Calculations and results). A selected calculation also has its own run
row at the foot of Properties, below the form, so that it stays in sight however long the
form is: its estimated duration and a button that reads Run, Run again when the result is
stale, or Cancel while its job is queued or running, the line beside it saying "running
in a worker" until the job reports its progress. A calculation can thus be computed from
its own form too, and the form's result line says the same state as the tab and the
outliner.

### The outliner

The outliner is the whole document as a tree, and each row says what it is and in what
state. An icon before the label gives the kind of row: a system (the same icon for a
quantum and a classical one), its lattice, an op, a region, a term (a sum sign), the mean
field, a calculation, Python code. A system's row gives its name in bold and a summary of
what was built ("2D · 8 sites · spinful", or "0D · 40 sites · classical spins" for a
classical one). The label of an entry carries its id, its kind and its name, then an op's
parameters, a region's selection or the region a term acts in, and the Status column
carries its state only, the marks drawn as icons:

- the Hilbert space after a term (spinless, spinful, Nambu), which is how one sees where
  a Zeeman field made the Hamiltonian spinful;
- the number of sites of a region;
- the mean field's interactions ("U = 3, runs with the calculations"; its total energy
  after a run, "U = 3, E = -1.68"; "off" when it is off);
- a calculation's result: a check mark when it is current, a circular arrow, dimmed, when
  it is stale, an hourglass and the percentage while its job runs, a cross in the error
  colour when its last run failed and no earlier result is kept (a run that fails over an
  earlier result reads as that result does, and its error is in the Jobs panel), the word
  queued or cancelled, nothing when it was never run, and the value of a single number
  after its mark (a gap, a Chern number);
- a warning triangle in the error colour for an entry that pyqula or the planner refuses,
  a crossed-out circle for a disabled one (the row dimmed), the sign ⚠ for one that is
  valid but worth a look (it reads a stale result), and a padlock on a locked entry (m and
  a padlock when one of its parameters is).

The full label and the messages (why an entry is refused, why a run failed, how to lift a
lock) are in the row's tooltip. A check box enables or disables an op or a term, a drag
reorders the entries, and the context menu enables, runs, renames, locks, duplicates,
moves or deletes.

### The drawings

The centre holds the Structure tab (the geometry, the Hamiltonian or a Field, drawn on the
atoms), the k-space tab (the Brillouin zone and the k-path, there only while the selected
system has a periodic direction) and one tab per calculation's result, which can be
closed (Ctrl+W) or detached into a window of its own. Each drawing has a bar above it
with what that drawing needs, and on a narrow window the bar wraps onto further lines
rather than hiding a control:

- every drawing: Fit, Pan and Zoom first and Save image last;
- the Structure tab: Pick, Box, Lasso and the Select menu, Region from selection,
  Calculate on selection and Remove selected (enabled while sites are selected), Show (the
  sites and bonds, the Hamiltonian, a Field) and the 3D box, and the brush while a Field is
  shown;
- a result: Pick, Box and Lasso (see Picking from a plot), Overlay, Export, Save data and
  Detach;
- the k-space tab: the calculation whose path is drawn, Add points, Remove last and
  Default path;
- the 3D scene drawn with pyvista: Reset view and the View menu in place of Fit, Pan and
  Zoom.

The buttons of the bars show icons, whose tooltips name them and their keys, where they
have one: Show is an eye before the choice of view, and 3D a cube beside its check box.
The k-space tab's path tools and the brush's value and radius keep their words. A result
that is not simply current says so in a row above its plot, with the icon of its state:
stale, with Run again; queued or running, with its progress and Cancel; failed, with the
first line of the error (the whole message in the tooltip) and Run again. A run that fails
while an earlier result is kept reads as that result does, stale (done when it still
matches the document), meaning that the earlier result stays drawn, under the row with Run
again when it is stale, and the error is read in the Jobs panel, in its status column and,
with the whole traceback, in its tooltip. The three read one state, so the result's tab
carries the same mark as a sign after its title (↻ stale, ✗ failed, the percentage while
it runs) and its row in the outliner as an icon, and a result never computed says what
comes next in its caption instead, drawn in the colours of the theme.

### The panels

The right column is Properties, the form of the selected entry, over Help, Sliders and
Jobs, tabbed, so that the help of an entry (F1, or the ? of its form) sits below the form
it explains rather than in its place. A new job brings Jobs to the front, unless Help is
showing an entry's help or Sliders is in front, so a slider being dragged stays in sight.
The Log and the Console share the bottom area, hidden until the Log button at the right
of the status bar shows it. The status bar shows the selected system (its dimension,
sites and Hilbert space), the estimated duration of the calculation Run names, and the
last message, in the error colour for an error.

The panels can be moved and closed but do not float, since a floating panel cannot be
moved on a Wayland desktop. View > Panels shows or hides each one, View > Reset layout puts
them back where they started, and the program keeps their arrangement and the window's
size for the next start. View > Interface text makes the text of the menus, the panels
and the forms larger, the formulas and the fixed-width text of the console and of a Python
node with it, for a projector or a small screen, as View > Plot text does for the
drawings.

### The forms

A form speaks the physics, and the engine's names (the pyqula call, has_spin, the
parameter's name) are in the tooltips and the help. Its head is the entry's title with
its enabled switch and the ? of its help, then the group and a line of what the entry
does, and its formula. A term of a system without regions reads "acts everywhere ·
restrict to a region", whose link opens the menu of the system's Regions row, and once the
system has a region the form has a region box in its place. Every number of a term is a
Field, and the button beside it says which kind it is: f(r) for a plain number, else
expression, piecewise, profile, interpolated, painted or from result; its menu chooses
the kind (see Fields: parameters that depend on the position).

A right click on a parameter's name opens its menu: Lock this parameter (or Unlock), where
a lock can name it; Attach a slider, over a range from zero to twice the value (from -1
to 1 for a zero, within the bounds the parameter takes); Sweep this parameter, which adds
a sweep of eleven values over the same range and selects it (see Sweeps and sliders);
and for a Field, Preview on the canvas. The system's form says spin (spinless or
spinful), superconducting (Nambu), hopping range (neighbours) and sparse matrices (large
systems). The spin and Nambu choices ask for what a term otherwise decides by itself (a
Zeeman field makes the Hamiltonian spinful, a pairing makes it Nambu), so spinless there
does not stop a Zeeman field from making it spinful, as the line under the form says.
The mean-field form folds the interactions beyond first neighbours under further
neighbours, ticked whenever one of them is not zero.

## Systems and geometry

New system (on the toolbar, or a card of the start page) makes a quantum system on a
lattice, and from its last section classical spins, a lattice gas or an Ising model. A
document may hold several systems (a texture computed on one can drive another, see
Fields). The geometry is the lattice followed by its ops, applied in order: changing an
op, or the lattice, rebuilds everything after it and keeps the terms. Ops that act on
positions (keep or remove sites where a condition holds, remove atoms) store positions or
expressions, not indices, so they survive a change of the supercell. A geometry that is
not flat is drawn in 3D; the 3D box of the Structure tab's bar switches to the xy
projection, where the selection tools work (see Drawing in 3D).

## Selections and regions

On the Structure tab the Pick, Box and Lasso tools of its bar select sites (shift adds,
ctrl toggles); its Select menu selects all, a sublattice, the edge sites (fewer neighbours
than the rest) or the inverse. The Pan and Zoom buttons of the bar take the clicks while
they are on (Pick, Box and Lasso then show unchecked): click one of those three to select
again; the drawing moves as described under Moving in space. With sites selected:

- Remove selected adds (or extends) a Remove atoms op that deletes them by position;
- Region from selection, on the bar or in the menu of the "+" of the system's Regions row,
  makes a named region of their positions;
- Calculate on selection offers what takes the selected sites (see Picking from a plot).

A region can also be an expression of x, y, z and r (Region by expression, in the same
menu). A term restricted to a region (the region box of its form, which its link "restrict
to a region" leads to while the system has none) acts only there; a Field can take one
value per region (piecewise). A region is kept by position, so it follows the geometry as
long as its sites are still there. A term between sites (Rashba, Haldane, Kane-Mele,
Kekule, a pairing, the hopping modulation) restricted to a region made of selected sites
acts on the bonds whose two ends are in it; an expression region holds the bonds whose
midpoint it holds.

## Terms and the Hamiltonian

The "+" of a system's Hamiltonian row (or Add, in the Hamiltonian workspace) offers the
terms by group (onsite, magnetism, spin-orbit, topology, superconductivity, fields,
disorder, and the mean field last); typing in its search line finds one by name or by what
it does. Terms are applied in order to the Hamiltonian that the construction (the system's
form) starts: first-neighbour hopping, or the hoppings to further neighbours its hopping
range gives. Before building, guiqula fixes the Hilbert space from the whole stack (a
Zeeman field needs spin, a pairing needs Nambu), so no term upgrades it halfway.

A term pyqula refuses is skipped and flagged with a cross in the error colour, with
pyqula's message in the tooltip of its row; the rest of the stack still builds, and a
result computed without it says so. The Hamiltonian view of the canvas (the Hamiltonian
workspace, or Show: Hamiltonian) draws what the terms did: the atoms coloured by their
onsite energy and outlined in grey, so that an onsite energy of zero, the pale middle of
the scale, stays in sight on either background, every hopping with a width following its
amplitude and a colour following its phase, exchange fields as arrows.

## Fields: parameters that depend on the position

Every number of a term is a Field. The button next to it reads f(r) for a plain number
and the kind of the Field otherwise, and its menu chooses the kind, which opens the editor
of that kind under the number:

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

The expression line says in one line what it takes (x, y, z, r; sin, exp, tanh; a
comparison is 1 or 0), with the whole list in its tooltip. While a Field is being edited
(a click into one of its boxes) the canvas previews it on the atoms, and Preview on the
canvas, in the menu of the parameter's name, shows it without editing. A parameter that
pyqula takes as a number only is marked constant: it accepts no function of position.
pyqula evaluates the Field of a term between sites at the middle of each bond: a painted
or from-result Field gives a bond the mean of the values at its two ends.

## The mean field

The mean-field block closes a system's Hamiltonian: the interactions (a Hubbard U, which
can depend on the position, and neighbour interactions V1 to V3 and exchange J1 to J3)
solved self-consistently from an initial guess, at a filling or a chemical potential.
Mean field (interactions), at the end of the menu of the Hamiltonian's "+", turns it on,
and its row in the outliner says which interactions it holds and, after a run, the total
energy it found. Its form shows U, V1 and J1 and folds the further neighbours. It runs
with the calculations, not while editing, and a calculation whose mean field does not
converge fails rather than silently using the non-interacting Hamiltonian. The engine
(numpy or jax), the solver, the mixing and the temperature are in its form; empty means
the engine's own default.

## Classical systems

A classical system (the last section of New system, or the last cards of the start
page's lattices) has a Model in place of a Hamiltonian: classical spins, a lattice gas
at a filling, or an Ising model, set up on the system's geometry, with its own terms
(exchange shells, fields, chemical potentials, exchange tensors) and calculations
(minimizing the spins, annealing the gas or the Ising model). Their results are drawn on
the atoms, and a from-result Field hands them to another system.

## Calculations and results

The "+" of the Calculations row (or Add, in the Calculate workspace) offers the
calculations by group. Run (F5) sends the calculation it names to a worker process, so the
window stays responsive; the row above its plot shows the progress, with Cancel, and the
Jobs panel lists every job. Each result has its own tab: the plot, with the bar of Fit,
Pan, Zoom, the pick tools, Overlay, Export, Save data, Detach (a window of its own) and
Save image, and a readout of the point under the mouse. A result becomes stale when
anything it depends on changes: its tab, its row in the outliner and the row above its
plot say so, and Run again in that row, Run, or Run every stale result in the menu of
Run's arrow computes it again. Run > Re-run cheap results automatically (Follow, the two
arrows on the toolbar) does that by itself for results estimated under three seconds.
Before a run estimated above a minute, a bar asks, and the estimate beside the
calculation's own Run, at the foot of Properties, says beforehand that it will. Run > Run
calculations at once, a setting kept like the theme and on by default, runs a calculation
as soon as it is added or one of its parameters is set, from its form, a pick on a plot or
a command, through the same bar; off, a calculation waits for Run.

An undo, or a value set back, makes the earlier result that matches the document current
again, without a re-run.

## Drawing in 3D

A geometry that is not flat (a 3D lattice, buckled or stacked layers) is drawn in 3D on the
canvas, and so is a result on its atoms: a magnetization, a local density of states, a
density. The 3D box of the Structure tab's bar decides for both: when it is checked, a flat
geometry is drawn in 3D too, which is the way to see the magnetization of graphene as
arrows in space rather than as in-plane arrows and dots, and when it is not, everything is
drawn in the xy projection, where the selection tools, the readout and the picks work.

View > 3D drawing chooses what draws in 3D. pyvista, the default when it is installed, draws
with VTK and moves as Blender's viewport does (see Moving in space). matplotlib draws with
mplot3d, which turns with a drag, and is what remains when pyvista is missing. In the
pyvista scene the bar has Reset view, which goes back to the first, oblique view with
everything in sight, and the View menu, in place of Fit, Pan and Zoom; Home shows
everything from the current angle, and Save image writes the view as it is drawn. The camera
stays where it was left when the same system is drawn again, after an edit, a new result or a
change of theme. The choice is kept with the settings. pyvista is an optional dependency
(`pip install "guiqula[3d]"`), and without it the entry is greyed out; if pyvista cannot draw
at all (no OpenGL), the drawing is left to matplotlib and the caption says why. Note that
Export writes matplotlib's figure in both cases, in the same projection.

## Moving in space

The drawings move as the two programs this workbench borrows its look from do, so that the
hands already know how: Inkscape's canvas for a geometry drawn flat (the Structure tab, and a
result drawn on the atoms), and Blender's viewport for a geometry drawn in 3D with pyvista.
The bands, the densities of states and the other plots keep matplotlib's own pan and
zoom, through the Fit, Pan and Zoom of their bar.

On a flat drawing, as in Inkscape:

- the wheel scrolls up and down, shift and the wheel scrolls sideways, and ctrl and the wheel
  zooms about the pointer, by a factor of the square root of two a notch;
- the middle button drags the drawing, and a click of it zooms in (shift and a click zooms out);
- holding Space turns the left button into the same drag, the hand, which is how a touchpad
  pans; the box and lasso tools step aside while it is held;
- ctrl and the arrow keys scroll, + and - zoom, 3 zooms to the selected sites (to everything
  when none is selected), 4 or Home shows the whole drawing, and the backtick goes back to the
  previous zoom and its shifted key forward to the next one;
- the Pan and Zoom buttons of the bar are there too, and while one is on the mouse
  belongs to it; Fit shows the whole drawing.

In the 3D scene, as in Blender:

- the middle button orbits, as a turntable, meaning that z stays up (past a pole the view is
  upside down and a horizontal drag turns the other way, as in Blender); shift and the middle
  button pans, and ctrl and the middle button zooms (dragging up zooms in);
- alt and the left button stand for the middle button (Blender's emulation of a three button
  mouse), so a mouse without one works; a Linux desktop that takes alt and a drag to move
  windows has to be told not to, or the middle button used;
- the wheel zooms, and ctrl and the wheel, or shift and the wheel, move the view sideways or up
  and down; the plain left button does nothing, since Blender keeps it for selecting and the
  scene has no selection yet;
- on the numpad, 1, 3 and 7 give the front, right and top views (ctrl: the opposite side, back,
  left and bottom), 4, 6, 8 and 2 orbit by 15 degrees (ctrl: pan), 5 switches between the
  perspective and the orthographic projection, 9 goes half way round, + and - zoom, and .
  puts the selected sites in sight; Home shows everything;
- an axis view is orthographic, and turning away from it returns to the perspective, as
  Blender's auto perspective does, unless the projection was chosen with 5;
- the View menu of the bar has the same views, the projection and the framing for a
  keyboard without a numpad, and names the view as Blender does (User Perspective, Top
  Orthographic).

Blender's roll, its navigation gizmo, zooming towards the pointer and the fly mode are not
there. The keys of both are in the table under Keyboard shortcuts, and the window action
`view_3d` moves the scene for a driver (`front`, `top`, `orthographic`, `all` and the rest).

## Picking from a plot

A point of a plot stands for a few physical values, and a calculation can be started or
moved there. A right click on a result, in any mode of its bar, or a click with its
Pick toggle on, opens a menu whose first line says what the point is: the energy and the
k-point of a point of the bands or of a spectral function, the energy on a density of
states, the k-point of a cell of a Fermi surface together with the energy the surface was
computed at, the value of the swept parameter on a sweep, a site of a result drawn on the
atoms. The point is the one the readout names, the drawn point nearest the cursor, or the
cursor itself when none is close, and the readout says what a pick would take as the mouse
moves, so you know it before clicking.

The menu then lists what takes those values. The calculations of the system with a
parameter of that kind come first, moved to the picked value with their other parameters
kept; then a new calculation of every kind that takes it, with its defaults otherwise and
named after where it came from, `at E = 0.3 from c1`: the LDOS at the picked energy over
the whole k-mesh, and the LDOS at the picked energy and k-point alone (an LDOS left over
the mesh stays so when it is moved), the eigenstate nearest that energy at that k-point,
drawn as its weight on the atoms, the Fermi surface and the quasiparticle interference
pattern at the energy, the density of states on picked sites. On a sweep the menu sets
the document at that point of the phase diagram and runs the swept calculation there; a
picked k-point can become a new vertex of the k-path of the bands; picked sites can be
selected on the Structure tab or made a region. On a result drawn flat on the atoms, the
Box and Lasso toggles of its bar pick every atom inside a drag, as the canvas tools
select them.

Two places that are not plots pick too. A click in the zone of the k-space tab, with Add
points off, or a right click there in any mode, picks the k-point under it, snapped onto
a high-symmetry point nearby as a vertex would be (a click on a vertex picks the vertex),
and offers the LDOS and the eigenstate at that k. On the Structure tab, Calculate on
selection offers what takes the selected sites, the density of states on them first, next
to Region from selection.

A picked energy can also become the Fermi level: an onsite term named `Fermi level` whose
mu shifts the spectrum so that the picked energy sits at zero, updated by the next pick of
this kind, so that every calculation counting the states below zero energy (the Chern
number, the gap, the density, the magnetization) is computed at that energy, while a mean
field at a fixed filling finds the Fermi energy of its filling whatever the shift. It is
offered without pairing only, since in Bogoliubov-de Gennes form an onsite energy enters
the electron and hole blocks with opposite signs, which changes the pairing problem
instead of shifting the spectrum, whose zero is the Fermi level already.

What a pick set stays on the plot it was picked on as a marker: a dashed line at the
energy across the bands or the density of states, at the swept value of a sweep, a line at
the picked point of a k-path, a circle at the k-point of a map, rings around the picked
atoms. A marker is bound to the parameter it set, as a slider is, so dragging it sets the
parameter, one undo step per drag, and with Run > Re-run cheap results automatically the
LDOS follows the line as it is dragged across the bands; a form, a slider or an undo
moves the marker in turn, since it always shows the value the parameter holds. The Sliders
panel lists the markers with the sliders (a marker of a k-point or of sites has no range
there, only its value), and removing the row removes the marker.

A pick is a set of ordinary commands, meaning that the document holds plain numbers, an
undo takes a pick back as one step, and a locked parameter refuses it with a message in
the log; whether what it added or moved runs at once is the choice of Run > Run
calculations at once. A result saved before picks existed carries no k-points, and a pick
on it gives the energy alone until it is computed again. The window's actions `pick` and
`pick_to` do the same for `tools/drive.py` and for remote control.

## Sweeps and sliders

A Sweep is a calculation that runs another one at every value of a parameter (or on a grid
of two) and draws the numbers it gives: the gap against a field, a Chern number against
two couplings. Name the calculation, the entry holding the parameter (a term, an op, a
calculation, `<system>/meanfield`, `<system>/model`, or the system for its lattice), the
parameter and its range. A range the parameter cannot take (a filling above 1) is refused,
and a sweep fails at a value pyqula rejects: no point is computed without its entry.

The quickest sweep is Sweep this parameter, in the menu of a parameter's name in its form
(a right click): eleven values from zero to twice the value (from -1 to 1 for a zero,
within the bounds the parameter takes), running the calculation itself for a parameter of
a calculation, else the first calculation of the system known to give numbers (a gap, a
Chern number), else the first one, which its tooltip then says has given no number so
far. The sweep is added and selected, so its form is there to change the range or the
calculation.

A slider is attached to a number from the same menu (Attach a slider, over the same
range), or named in the Sliders panel with its entry, parameter and range: dragging it
changes the parameter (one undo step per drag), and with the automatic re-run on, cheap
results follow. A locked parameter takes no slider. A marker is a slider drawn on a plot
(see Picking from a plot).

## Overlays and exports

The Overlay menu of a result draws another result on the same axes, or the difference of
two curves on the same grid. Export (Ctrl+Shift+E) writes one folder with the figure as PNG
and PDF (on white, whatever the theme), the arrays (.npz, and .csv for curves), the pyqula
script that computes them and the document; File > Export pyqula script (Ctrl+E) writes
the script alone. The scripts use pyqula only, not guiqula.

## The k-space tab

The k-space tab, there while the selected system has a periodic direction, draws the
Brillouin zone of that system with the high-symmetry points pyqula knows for it, pyqula's
default path (dashed) and the k-path of the calculation its bar names (path of). Add
points appends vertices (they snap onto the high-symmetry points); with it on, a click on
a vertex of the path adds that point again, so a path can pass twice through a point (Γ K
M Γ). A vertex can be dragged, Remove last removes one, and Default path goes back to
pyqula's. The k-path of a calculation's form takes the same path as text (`G K M G`). The
latest Fermi surface of the system is drawn underneath, and a click in the zone with Add
points off picks its k-point (see Picking from a plot). A three-dimensional lattice is
drawn by the k3 = 0 cut of its zone (the plane of b1 and b2) with the high-symmetry points
in that plane; a path that leaves the plane (pyqula's default one, or `Z` typed in the
form) is drawn projected onto it.

When the k-path of the bands or of the spectral function is left empty they walk pyqula's
default path, and the k axis names the high-symmetry points that path goes through, as it
does for a path typed in the form: Γ K' M K Γ on the honeycomb, triangular and kagome
lattices, Γ M Γ on a square one, Γ X Γ in one dimension and Γ X M Γ R in three. Γ, K and K'
are the points pyqula's labels give (the ones the k-space tab draws), which means that the
first corner of the default path is K' and not the K that pyqula's own guide writes; M, X and
Y name a point by its kind, so the three M points of a hexagonal zone are all M, and `M` typed
in a k-path is the point (1/2, 0), which is not always the M that the default path crosses. In
two dimensions pyqula's path leaves out its opening Γ (it stores each point after the step),
so guiqula walks the same points with Γ put first: the bands of an empty k-path have one point
more than a direct call of pyqula, and the exported script writes the path. A finite system
has no k, and its axis keeps the index of the point.

## Python nodes, trust and the console

A Python op, term or calculation runs its code in the worker with `g` (the geometry), `h`
(the Hamiltonian), `np` and `pyqula`: whatever pyqula can do and the Add menus do not offer.
An error flags the node with the line of its code and the rest carries on. A calculation
sets `arrays`, numbers and arrays of numbers (what a project file keeps), and may set
`plot`; a plot that does not fit its arrays is refused when the code runs.

A document built in the program, or a shipped preset, is trusted. A file opened with
Python nodes is not: its nodes are skipped until you trust it (the bar at the top, or
File > Trust the Python code), since opening a file must not run code someone else wrote.
File > Always trust Python code in files turns that off for your files.

The Console, a panel of the bottom area beside the Log (the Log button of the status bar
shows them), runs Python in its own worker, with `doc`, `g` and `h` of the selected
system, `do(command, ...)` for commands (undoable, like any edit), `np` and `pyqula`.
Interrupt stops it and starts afresh.

## Projects, presets and locks

File > Save writes a `.guiqula` project (the document and its results; a `.json` file
holds the document alone). New, Open, a card of the start page, the gallery's Open and
Recover replace the document: with unsaved changes they first ask, as Quit does, whether
to save them, and New leaves an empty document, on which the start page shows. The program
autosaves; after a crash, the next start offers to recover the unsaved work. The start
page and the presets gallery (File > Presets gallery) list the shipped documents:
teaching presets, with some parameters locked, and examples.

A lock keeps an entry, one parameter of it, or a system's geometry from changing: its
fields are greyed out and commands that would change it are refused. Lock this parameter
and Unlock, in the menu of a parameter's name (a right click), lock or unlock it; the
outliner's context menu locks an entry or a geometry; Edit > Unlock everything lifts them
all. Locks guide an exercise, they are not a
protection.

## Undo, themes and settings

Edit > Undo and Redo say which step they take back; Edit > Undo history goes back several
steps at once, and the selection follows. What is shown (the selection, the workspace,
the sliders, the overlays, the theme) is not undone. View > Theme chooses light, dark or
the desktop's scheme, and the icons, the drawings and an empty result follow it. View >
Plot text chooses the size of the text of every drawing, the labels, the ticks and the
titles of the plots, of the canvas, of the k-space tab and of the exported figures: small,
normal or large, so that a projector or a small screen gets a readable size too; View > Interface text does the same for the text of the menus, the
panels and the forms (normal or large). The settings (theme, plot text, interface text,
recent files, always trust, remote control, run at once, the 3D drawing, and the
arrangement of the panels with the window's size) are a file in the user configuration
directory.

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
guiqula-something`), its entries appear in the Add menus, the start page, the forms, the
help and the exported scripts like guiqula's own, and run in the workers. Help > Plugins
lists the plugins found, what each added, and any that failed to load: such a plugin is
left out and guiqula starts without it (`GUIQULA_NO_PLUGINS=1 guiqula` starts without
any). A document records which plugin, and which version of it, each of its entries came
from, and Help > Plugins lists the plugins the open document uses. A document that uses an
entry of a plugin that is not installed still opens; that entry is skipped and flagged
with the plugin's name, which is what to `pip install`.

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
| window | Ctrl+F | the Add menu of the workspace, with its search line (ops, terms or calculations) |
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
| 2D canvas | +, = | zoom in (in 3D as well) |
| 2D canvas | - | zoom out (in 3D as well) |
| 2D canvas | 3 | zoom to the selected sites, or to everything when none is (in 3D as well) |
| 2D canvas | 4 | show the whole drawing (Home does it too) |
| 2D canvas | ` | the previous zoom |
| 2D canvas | ~, Shift+` | the next zoom |
| 2D canvas | Ctrl+Left | scroll left (pan left in 3D) |
| 2D canvas | Ctrl+Right | scroll right (pan right in 3D) |
| 2D canvas | Ctrl+Up | scroll up (pan up in 3D) |
| 2D canvas | Ctrl+Down | scroll down (pan down in 3D) |
| 3D canvas | Num+1, Num+3, Num+7 | front, right and top view |
| 3D canvas | Ctrl+Num+1, Ctrl+Num+3, Ctrl+Num+7 | back, left and bottom view |
| 3D canvas | Num+4, Num+6, Num+8, Num+2 | orbit left, right, up and down by 15 degrees |
| 3D canvas | Ctrl+Num+4, Ctrl+Num+6, Ctrl+Num+8, Ctrl+Num+2 | pan left, right, up and down |
| 3D canvas | Num+5 | perspective or orthographic |
| 3D canvas | Num+9 | the opposite side of the view |
| 3D canvas | Num++, Num+- | zoom in and out |
| 3D canvas | Num+. | the selected sites in sight |
| console | Return | run the input |
| console | Shift+Return | a new line in the input |
| console | Up, Down | walk the history |
| code editor | Ctrl+Return | apply the code of a Python node |

The canvas and outliner keys work while that widget has the focus (click it first).

## Getting help

F1, or the ? button of a form, shows the help of the selected entry in the Help panel,
below the form: its formula and parameters, the pyqula code it runs with the current
values, the docstrings of the pyqula functions behind it, and the sections of pyqula's
user guide about it. Help > pyqula user guide and Help > guiqula user guide open the whole
texts, and so do the two buttons at the top of the panel; the link at the foot of the
start page opens this guide.
