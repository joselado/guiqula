# guiqula

A graphical workbench for tight-binding models in condensed matter physics, built on
[pyqula](https://github.com/joselado/pyqula). Build a lattice, stack up the terms of a
Hamiltonian (spin-orbit coupling, magnetism, superconductivity, interactions, disorder,
fields), and compute band structures, densities of states, topological invariants and
self-consistent mean-field states, in one window and without writing code. Every result can
be turned into the plain pyqula script that reproduces it.

![A zigzag Kane-Mele ribbon: the helical edge states cross the gap, coloured by the edge they live on](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/hero.png)

The model is a pipeline you can edit in any order: change the lattice or the width of a
ribbon after adding the terms, and everything downstream is rebuilt. Any parameter of any
term can depend on position, and results that no longer match the model are marked stale.

## Install

guiqula needs Python 3.12 or 3.13. It is developed and tested on Linux; all its
dependencies have wheels for macOS and Windows too, where it is expected to work but has not
been tried yet (reports are welcome):

```
pip install guiqula
```

(or `pipx install guiqula`, or `uv tool install guiqula`, to keep it in an environment of its
own). Then:

```
guiqula                      # the window
guiqula haldane_chern        # the window, with one of the example documents
guiqula desktop              # optional: a menu entry, an icon and the .guiqula file type
```

With conda, `conda env create -f environment.yml` (from this repository) makes an
environment called `guiqula`, with the scientific stack from conda-forge and guiqula from
PyPI. To try the latest version from this repository:
`pip install git+https://github.com/joselado/guiqula`.

pyqula comes inside guiqula, so there is nothing else to install. The first calculation of
a session takes a few seconds longer: pyqula's numerical kernels are compiled once and then
cached.

## What it does

**Geometry**
- 33 lattices from 0D to 3D: chains and ladders; square, honeycomb (flat and buckled),
  triangular, kagome and Lieb lattices; cubic, diamond, pyrochlore and hyperhoneycomb
  lattices; multilayer graphene and twisted bilayer graphene; ready-made ribbons.
- Supercells, ribbons, films, finite islands (flakes of any number of edges), strain,
  rotations.
- Sculpting on the canvas: select sites with a box or a lasso and remove them, or keep the
  sites where a condition holds; saved selections become regions.

**Hamiltonian**
- Onsite energies, sublattice imbalance, crystal fields, electric fields.
- Zeeman and exchange fields, antiferromagnetic order, spin spirals.
- Rashba and Kane-Mele spin-orbit coupling; Haldane and modified Haldane couplings.
- Superconducting pairing: s-wave, and any symmetry pyqula knows (extended s, p, d, f,
  chiral, triplet with a d-vector), in Nambu form.
- Orbital magnetic fields (Peierls phases, out of plane or in plane), Kekulé and other
  hopping modulations, valley exchange.
- Anderson and hopping-phase disorder, with explicit seeds so that every result is
  reproducible.
- Interactions (Hubbard U, and density-density and exchange couplings up to third
  neighbours) solved self-consistently in the mean field, from several initial guesses.
- **Every parameter can vary in space**: a constant, a formula of x, y, z, a value per
  region, a profile, values painted on the atoms with a brush, or the result of another
  calculation (for example a classical spin texture used as an exchange field).

**Calculations**
- Band structures, coloured by any observable (spin, position, sublattice, valley...);
  density of states; spectral functions of the bulk and of surfaces; Fermi surfaces; gaps;
  total energies.
- Local density of states, electron density and magnetization, drawn on the atoms.
- Topology: Chern and spin Chern numbers, Z2 invariants, Berry curvature maps and along a
  path, local Chern markers.
- Optical conductivity.
- Sweeps over one or two parameters of any term: curves and phase diagrams.
- Classical models on the same lattices: Heisenberg spins with isotropic or tensor
  exchange in a field (energy minimization), Ising models and lattice gases (annealing).

**Working with it**
- Every plot is interactive; sliders change a parameter while cheap results re-run on
  their own; overlays compare results; the k-path is edited on the Brillouin zone.
- Every result exports its figure, its data and the pyqula script that reproduces it. A
  Python console sees the live Hamiltonian.
- Projects keep their results; autosave, crash recovery, and undo for everything.
- Every entry's help is pyqula's own documentation, with its formula and the pyqula code
  it runs.
- Runs without a window too (`guiqula run`), and can be driven by other programs, including
  Claude (see below).
- Teaching: documents with locked parameters, so that students change only what the
  exercise is about.

## Examples

Each example is a document that comes with guiqula: open it with `guiqula <name>` or from
File > Presets gallery, press Run (F5) on a calculation, then change the model and run
again.

### Dirac points and flat bands: the kagome lattice

`guiqula kagome_flat_band`. Nearest-neighbour hopping on the kagome lattice gives two
dispersive bands touching at Dirac points, and a band that does not disperse at all:
destructive interference traps the electrons on the hexagons, and the density of states
shows it as a sharp peak.

<img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/kagome_bands.png" width="49%" alt="kagome bands"> <img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/kagome_dos.png" width="49%" alt="kagome density of states">

Try: add a Zeeman field, or a Haldane-like coupling, and see what happens to the flat
band.

### Chern insulator: the Haldane model

`guiqula haldane_chern`. Spinless electrons on the honeycomb lattice with the Haldane
coupling, which breaks time-reversal symmetry, and a sublattice imbalance. The Berry
curvature concentrates at the K and K' points, and the Chern number is ±1 as long as the
mass stays below about 5 times the Haldane coupling (3√3 times, in the continuum). The
phase diagram sweeps the Chern number over both parameters.

<img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/haldane_berry.png" width="49%" alt="Berry curvature of the Haldane model"> <img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/haldane_phase.png" width="49%" alt="Chern number phase diagram of the Haldane model">

### Quantum spin Hall effect: the Kane-Mele model

`guiqula kane_mele_ribbon`. A zigzag graphene ribbon with intrinsic spin-orbit coupling: the
bulk is gapped, and a helical pair of edge states crosses the gap on each edge. The bands
are coloured by the position across the ribbon (the `yposition` operator; any other, such
as `sz`, is chosen in the calculation's form), so the states of the two edges come out red
and blue; the second calculation shows the local density of states inside the gap sitting
on the edges.

![bands of a Kane-Mele ribbon coloured by the position across it](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/kane_mele_bands.png)

Try: add an exchange field, which breaks time-reversal symmetry, and watch the edge states
gap out; Rashba coupling alone leaves them gapless.

### Quantum Hall effect: Landau levels on a lattice

`guiqula hofstadter_ribbon`. A square-lattice ribbon in an out-of-plane magnetic field
(Peierls phases): flat Landau levels in the bulk, and chiral edge states between them.

![Landau levels and chiral edge states of a Hofstadter ribbon](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/hofstadter.png)

### Interaction-driven magnetism: zigzag graphene edges

`guiqula zigzag_ribbon_magnetism`. A graphene zigzag ribbon with a Hubbard interaction
solved in the mean field: the flat edge band polarizes, each edge becomes ferromagnetic
with the two edges opposite, and a gap opens.

<img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/zigzag_magnetization.png" width="60%" alt="edge magnetization of a zigzag graphene ribbon">

Try: change U in the mean-field block, the width of the ribbon, or the initial guess. The
same mean field on the bulk honeycomb lattice gives an antiferromagnet
(`guiqula honeycomb_hubbard`).

### Topological superconductivity: a Majorana wire

`guiqula majorana_wire`. A finite wire with Rashba spin-orbit coupling, an exchange field
and s-wave pairing, in the topological phase: a Majorana zero mode at each end, seen in the
zero-energy local density of states and as a zero-energy peak in the density of states.

<img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/majorana_ldos.png" width="49%" alt="zero-energy local density of states of a Majorana wire"> <img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/majorana_dos.png" width="49%" alt="density of states of a Majorana wire">

Try: lower the exchange field below the pairing, and the end states disappear.

### Quasiperiodicity and localization: the Aubry-André model

`guiqula aubry_andre`. A chain with an onsite energy λ cos(2πβx) of irrational β. Above
λ = 2 every state is localized: the density of states is a fractal set of bands, and the
local density of states concentrates on a few sites. The onsite energy is written as a
formula of x, so λ and β are edited directly in it.

<img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/aubry_andre_dos.png" width="49%" alt="density of states of the Aubry-André model"> <img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/aubry_andre_ldos.png" width="49%" alt="local density of states of the Aubry-André model">

### Nanostructures: a graphene flake, and a gate on it

`guiqula graphene_island`. A hexagonal graphene flake cut from the lattice: its discrete
spectrum, and the zero-energy states living on the zigzag parts of its edges. On the right,
an onsite energy written as a Gaussian of the position, a gate on the centre of the flake,
drawn on the atoms before anything is computed.

<img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/island_ldos.png" width="49%" alt="zero-energy local density of states of a graphene flake"> <img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/field_gate.png" width="49%" alt="a Gaussian gate potential on a graphene flake">

Try: remove atoms by hand on the Structure tab, change the number of edges of the island,
or restrict a term to a region you draw.

### Frustrated magnetism: classical spins on the triangular lattice

`guiqula triangular_spins`. Classical Heisenberg spins with antiferromagnetic coupling on
the triangular lattice cannot all be antiparallel; minimizing the energy gives the
120-degree order.

<img src="https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/triangular.png" width="60%" alt="120-degree order of classical spins on the triangular lattice">

Ising models and lattice gases are there too (`guiqula ising_ferromagnet`,
`guiqula lattice_gas`).

### Classical textures seen by electrons

`guiqula texture_exchange`. Two systems in one document: classical spins on a ladder,
minimized in a field that turns along it into a domain wall; and electrons on the same
ladder whose exchange field reads that texture site by site, for their density of states
and local density of states. Run the classical calculation first; when it changes, the
electronic results are marked stale.

![a classical domain wall on a ladder: the in-plane spin turns through the out-of-plane direction](https://raw.githubusercontent.com/joselado/guiqula/master/docs/images/texture_spins.png)

Also in the gallery: graphene with an exchange field and Rashba coupling
(`honeycomb_zeeman_rashba`), and two teaching documents with locked parameters: graphene's
Dirac cones and the gap a sublattice imbalance opens (`graphene_basics`), and the end states
of the SSH chain (`ssh_chain`).

## Without the window

```
guiqula run haldane_chern --calc c2 --out results --script   # compute, save data and script
guiqula script haldane_chern --calc c1                       # print the pyqula script
guiqula serve my_project.guiqula                             # a session other programs drive
```

The scripts are plain pyqula: they run without guiqula, so a model set up in the window can
continue its life in a notebook or on a cluster.

## Claude and other programs

File > Allow remote control (or `guiqula --remote`) lets programs on the same computer drive
the window through a local port protected by a token. `guiqula mcp` is an MCP server over
that interface; register it with Claude Code:

```
claude mcp add guiqula -- guiqula mcp
```

Claude can then read the document, add terms, run calculations, look at the results, the
plots and the window, and explain pyqula's documentation of every entry. Without a running
window, the MCP server runs a session of its own.

## Plugins

A plugin package adds lattices, operations, terms or calculations of your own, which then
appear in the palettes and forms like the built-in ones: see `plugin_template/`. A single
Python file in the user's plugins folder works too (Help > Plugins).

## Development

Nothing needs installing in a source checkout: `PYTHONPATH=src python -m guiqula` starts the
window, and `python -m pytest` runs the tests (offscreen Qt, worker processes). `PLAN.md` is
the design document and `CLAUDE.md` the development guide.

## License

GPL-3.0-or-later (see `LICENSE`), like pyqula.
