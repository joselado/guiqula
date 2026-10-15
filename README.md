# guiqula

guiqula is a graphical program to study tight-binding models in condensed matter physics,
and it uses [pyqula](https://github.com/joselado/pyqula) to do the calculations. You choose a
lattice, you add terms to the Hamiltonian (spin-orbit coupling, magnetism,
superconductivity, interactions, disorder, external fields), and then you compute band
structures, density of states, topological invariants and self-consistent mean-field
solutions. All of this is done in one window, and you do not need to write code. For every
result, guiqula can also give you the pyqula script that computes the same thing.

![A zigzag Kane-Mele ribbon: the helical edge states cross the gap, coloured by the edge they live on](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/hero.png)

The model is built as a chain of steps, and you can edit any step at any time. For example,
you can change the lattice or the width of a ribbon after you added the terms, and guiqula
builds again everything that comes after it. Any parameter of any term can depend on the
position. When a result does not match the model anymore, guiqula marks it as stale.

## Install

guiqula needs Python 3.12 or 3.13. We develop and test it on Linux. All its dependencies
also have wheels for macOS and Windows, so it should work there too, but we have not tried it
yet (reports are welcome):

```
pip install guiqula
```

You can also use `pipx install guiqula` or `uv tool install guiqula`, which put guiqula in
its own environment. `pip install "guiqula[3d]"` also installs pyvista, for 3D drawings that
you move with the mouse as in the viewport of Blender. Then:

```
guiqula                      # the window
guiqula haldane_chern        # the window, with one of the example documents
guiqula desktop              # optional: a menu entry, an icon and the .guiqula file type
```

With conda, run `conda env create -f environment.yml` from this repository. This creates an
environment called `guiqula`, with the scientific packages from conda-forge and guiqula from
PyPI. To try the latest version of this repository:
`pip install git+https://github.com/joselado/guiqula`.

pyqula is included inside guiqula, so you do not need to install anything else. The first
calculation of a session takes a few seconds more, because pyqula compiles its numerical
kernels the first time and then keeps them in a cache.

## What it does

**Geometry**
- 33 lattices from 0D to 3D: chains and ladders; square, honeycomb (flat and buckled),
  triangular, kagome and Lieb lattices; cubic, diamond, pyrochlore and hyperhoneycomb
  lattices; multilayer graphene and twisted bilayer graphene; ribbons ready to use.
- Supercells, ribbons, films, finite islands (flakes with any number of edges), strain,
  rotations.
- Editing the structure on the canvas: you select sites with a box or a lasso and remove
  them, or you keep only the sites where a condition is true. A selection that you save
  becomes a region.

**Hamiltonian**
- Onsite energies, sublattice imbalance, crystal fields, electric fields.
- Zeeman and exchange fields, antiferromagnetic order, spin spirals.
- Rashba and Kane-Mele spin-orbit coupling; Haldane and modified Haldane couplings.
- Superconducting pairing: s-wave, and every symmetry that pyqula has (extended s, p, d, f,
  chiral, triplet with a d-vector), in Nambu form.
- Orbital magnetic fields (Peierls phases, out of plane or in plane), Kekulé and other
  modulations of the hopping, valley exchange.
- Anderson disorder and hopping-phase disorder, with an explicit seed, so that every result
  can be reproduced.
- Interactions (Hubbard U, and density-density and exchange couplings up to third
  neighbours), solved self-consistently at the mean-field level, starting from different
  initial guesses.
- **Every parameter can change in space**: it can be a constant, a formula of x, y, z, one
  value per region, a profile, values painted on the atoms with a brush, or the result of
  another calculation (for example, a classical spin texture used as an exchange field).

**Calculations**
- Band structures, coloured by any observable (spin, position, sublattice, valley...);
  density of states; spectral functions of the bulk and of surfaces; Fermi surfaces; gaps;
  total energies.
- Local density of states, electron density and magnetization, drawn on the atoms. With
  pyvista (optional) they can also be drawn in 3D, and you rotate, move and zoom them with
  the mouse.
- Topology: Chern and spin Chern numbers, Z2 invariants, Berry curvature as a map and along
  a path, local Chern markers.
- Optical conductivity.
- The dI/dV that an STM tip measures on one site. The tip is a system of its own, so it
  can be a metal, a superconductor or a magnet.
- Sweeps of one or two parameters of any term, which give curves and phase diagrams.
- Classical models on the same lattices: Heisenberg spins with isotropic or tensor exchange
  in a magnetic field (solved by minimizing the energy), and Ising models and lattice gases
  (solved by annealing).

**Working with it**
- Everything is in one window, similar to Blender and Inkscape. When it opens, it shows a
  page with the lattices and the examples as pictures.
- To add an operation, a term or a calculation, you click the "+" of its section in the
  outliner and choose it from a menu with a search line. The workspace shows what you
  selected.
- The Run button says which calculation it will compute. When a result does not match the
  model anymore, a message above its plot says so, with a Run again button next to it.
- Every plot is interactive. From the menu of a parameter's name you can attach a slider or
  a sweep to it, and with the automatic re-run on (Follow), cheap results are computed again
  while you move the slider.
- Overlays compare results. A Style button sets the widths, sizes, colours and colour maps
  that make sense for each kind of plot. A grid shows several results next to each other,
  and you put each result in its cell by dragging its tab. You edit the k-path directly on
  the Brillouin zone.
- Every result can export its figure, its data and the pyqula script that reproduces it. A
  structure, a local density of states or a magnetization can also be exported to
  Blender, as a .blend file, to render it. A Python console has access to the live
  Hamiltonian.
- Projects save their results too. There is autosave, crash recovery, and undo for every
  action.
- The help of every entry is the documentation of pyqula itself, with its formula and the
  pyqula code that it runs.
- It also runs without a window (`guiqula run`), and other programs can control it,
  including Claude (see below).
- Teaching: documents with locked parameters, so that students can only change what the
  exercise is about.

## Examples

Each example is a document that comes with guiqula. You can open it with `guiqula <name>`,
from the start page, or from File > Presets gallery. Then you select a calculation in the
outliner and press Run (F5), which shows the name of the calculation it will compute. After
that, change the model and run again.

### Dirac points and flat bands: the kagome lattice

`guiqula kagome_flat_band`. With nearest-neighbour hopping, the kagome lattice has two
dispersive bands that touch at Dirac points, and one band that is completely flat. The flat
band comes from destructive interference, which traps the electrons on the hexagons, and
the density of states shows it as a sharp peak. Here the two results are next to each
other, in a grid with one row and two columns (View > New grid of results), and each result
was dragged there by its tab.

![guiqula with the kagome bands and density of states side by side in a grid: two dispersive bands with Dirac points, a flat band and its peak](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/kagome.png)

Try: add a Zeeman field, or a Haldane-like coupling, and look at what happens to the flat
band.

### Chern insulator: the Haldane model

`guiqula haldane_chern`. Spinless electrons on the honeycomb lattice, with the Haldane
coupling, which breaks time-reversal symmetry, and a sublattice imbalance. The Berry
curvature is concentrated at the K and K' points. The Chern number is ±1 while the mass is
smaller than about 5 times the Haldane coupling (3√3 times in the continuum). The phase
diagram, shown here together with its form, computes the Chern number as a function of both
parameters.

![guiqula with the Chern number phase diagram of the Haldane model](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/haldane.png)

### Quantum spin Hall effect: the Kane-Mele model

`guiqula kane_mele_ribbon`. A zigzag graphene ribbon with intrinsic spin-orbit coupling.
The bulk has a gap, and on each edge a helical pair of edge states crosses this gap. The
picture at the top of this page shows its bands coloured by the position across the ribbon
(the `yposition` operator; you can choose another one, such as `sz`, in the form of the
calculation), so the states of one edge are red and the states of the other edge are blue.
In the picture below, the local density of states inside the gap is located on the two
edges of the cell of the ribbon.

![guiqula with the in-gap local density of states of a Kane-Mele ribbon](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/kane_mele.png)

Try: add an exchange field, which breaks time-reversal symmetry, and you will see a gap open
in the edge states. With Rashba coupling alone, they stay gapless.

### Quantum Hall effect: Landau levels on a lattice

`guiqula hofstadter_ribbon`. A ribbon of the square lattice in an out-of-plane magnetic
field (Peierls phases). The bulk has flat Landau levels, and between them there are chiral
edge states.

![guiqula with the Landau levels and chiral edge states of a Hofstadter ribbon](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/hofstadter.png)

### Interaction-driven magnetism: zigzag graphene edges

`guiqula zigzag_ribbon_magnetism`. A graphene zigzag ribbon with a Hubbard interaction,
solved at the mean-field level. The flat band at the edges becomes polarized: each edge
becomes ferromagnetic, the two edges point in opposite directions, and a gap opens.

![guiqula with the mean-field block and the edge magnetization of a zigzag ribbon](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/zigzag.png)

Try: change U in the mean-field block, the width of the ribbon, or the initial guess. The
same mean field on the bulk honeycomb lattice gives an antiferromagnet
(`guiqula honeycomb_hubbard`).

### Topological superconductivity: a Majorana wire

`guiqula majorana_wire`. A finite wire with Rashba spin-orbit coupling, an exchange field
and s-wave pairing, in the topological phase. There is a Majorana zero mode at each end. You
can see it in the local density of states at zero energy, and as a peak at zero energy in
the density of states.

![guiqula with the zero-energy local density of states of a Majorana wire](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/majorana.png)

Try: make the exchange field smaller than the pairing, and the end states disappear.

### Quasiperiodicity and localization: the Aubry-André model

`guiqula aubry_andre`. A chain with an onsite energy λ cos(2πβx), with β irrational. For λ
above 2 all the states are localized: the density of states is a fractal set of bands, and
the local density of states is concentrated on a few sites. The onsite energy is written as
a formula of x, so you edit λ and β directly in the formula.

![guiqula with the onsite energy written as a formula and the density of states of the Aubry-André model](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/aubry_andre.png)

### Nanostructures: a graphene flake, and a gate on it

`guiqula graphene_island`. A hexagonal graphene flake cut from the lattice. Its spectrum is
discrete, and the states at zero energy live on the zigzag parts of its edges.

![guiqula with the island operation and the zero-energy local density of states of a graphene flake](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/island.png)

Any parameter can depend on the position. Here an onsite energy is written as a Gaussian of
the position, which works as a gate on the centre of the flake, and guiqula draws it on the
atoms before computing anything:

![guiqula with an onsite energy written as a Gaussian of the position, drawn on the flake](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/island_gate.png)

Try: remove atoms by hand on the Structure tab, change the number of edges of the island,
or apply a term only in a region that you draw.

### Frustrated magnetism: classical spins on the triangular lattice

`guiqula triangular_spins`. Classical Heisenberg spins with antiferromagnetic coupling on
the triangular lattice. They cannot all be antiparallel to each other, and minimizing the
energy gives the 120-degree order.

![guiqula with the 120-degree order of classical spins on the triangular lattice](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/triangular.png)

Ising models and lattice gases are also included (`guiqula ising_ferromagnet`,
`guiqula lattice_gas`).

### Classical textures seen by electrons

`guiqula texture_exchange`. One document with two systems. The first one is classical spins
on a ladder, minimized in a magnetic field that rotates along the ladder, which gives a
domain wall. The second one is electrons on the same ladder, whose exchange field takes
this texture site by site, and for them we compute the density of states and the local
density of states. Run the classical calculation first. When it changes, the results of the
electrons are marked as stale.

![guiqula with the two systems of the document and the classical domain wall](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/texture.png)

Also in the gallery: graphene with an exchange field and Rashba coupling
(`honeycomb_zeeman_rashba`), and two documents for teaching, with locked parameters. One
shows the Dirac cones of graphene and the gap opened by a sublattice imbalance
(`graphene_basics`), and the other one the end states of the SSH chain (`ssh_chain`).

## Without the window

```
guiqula run haldane_chern --calc c2 --out results --script   # compute, save data and script
guiqula script haldane_chern --calc c1                       # print the pyqula script
guiqula serve my_project.guiqula                             # a session other programs drive
```

The scripts are plain pyqula, and they run without guiqula. So you can set up a model in the
window, and then continue with it in a notebook or on a cluster.

## Claude and other programs

With File > Allow remote control (or `guiqula --remote`), other programs on the same
computer can control the window. They connect through a local port, protected by a token.
`guiqula mcp` is an MCP server that uses this connection, and you register it in Claude
Code with:

```
claude mcp add guiqula -- guiqula mcp
```

Then Claude can read the document, add terms, run calculations, look at the results, the
plots and the window, and explain the pyqula documentation of every entry. If no window is
open, the MCP server starts its own session.

## Plugins

With a plugin package you can add your own lattices, operations, terms or calculations.
They then appear in the Add menus, on the start page and in the forms, in the same way as
the built-in ones. There is an example in `plugin_template/`. A single Python file in your
plugins folder also works (Help > Plugins).

## Development

In a source checkout you do not need to install anything. `./guiqula` starts the window,
and it takes the same arguments and subcommands as the installed `guiqula`. It is the same
as `PYTHONPATH=src python -m guiqula`, and you can link it from a directory in your `PATH`.
`python -m pytest` runs the tests (offscreen Qt, worker processes). `PLAN.md` is the design
document, and `CLAUDE.md` is the development guide.

## License

GPL-3.0-or-later (see `LICENSE`), the same as pyqula.
