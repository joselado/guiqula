# guiqula

A graphical workbench for [pyqula](https://github.com/joselado/pyqula), the Python
tight-binding library: one window in which a geometry, the terms of a Hamiltonian and the
calculations on it are put together, changed in any order and computed by pyqula.
Geometry, Hamiltonian and calculations are a non-destructive pipeline, as in Blender or
Inkscape: change the lattice after adding the terms, and everything downstream follows.

- Lattices (chains, square, honeycomb, triangular, kagome, Lieb, ribbons, multilayers,
  twisted bilayers), geometry operations (supercells, ribbons, islands, removing atoms,
  selections and regions drawn on the canvas).
- Hamiltonian terms (onsite energies, exchange, spin-orbit couplings, Haldane and
  Kane-Mele, pairing, disorder, orbital fields, strain...) whose every parameter can depend
  on the position: an expression, a value per region, a profile, values painted on the
  atoms, or another calculation's result. Mean-field interactions.
- Calculations (bands, density of states, local density of states, Chern and spin Chern
  numbers, Z2 invariants, Berry curvature, Fermi surfaces, surface spectral functions,
  optical conductivity, sweeps and phase diagrams...), each with an interactive plot;
  classical spin, Ising and lattice-gas models too.
- Every result exports the standalone pyqula script that reproduces it. Projects keep
  their results; autosave and crash recovery; undo for everything; the help of every
  entry is pyqula's own documentation.
- Runs headless (`guiqula run`), and can be driven by other programs and by Claude
  (`guiqula mcp`, an MCP server).

pyqula ships inside guiqula (a copy of its source, `vendor/`), so a `pip install` brings
the version guiqula was tested with.

## Install

Python 3.12 or 3.13, on Linux, macOS or Windows:

```
pip install guiqula            # or: pipx install guiqula, uv tool install guiqula
guiqula                        # the window
guiqula desktop                # a menu entry and an icon (optional)
```

With conda, `conda env create -f environment.yml` makes an environment `guiqula` with
the dependencies from conda-forge and guiqula from PyPI.

The first calculation of a session takes some seconds more: numba compiles pyqula's
kernels once, and keeps them in the user cache directory.

## Use

- `guiqula [project.guiqula | preset]` opens the window; File > Presets gallery has ready
  documents. The user guide is in the program (Help > guiqula user guide, and F1 on any
  entry for its help).
- `guiqula run project.guiqula --calc c1 --out results --script` computes without a window.
- `guiqula script project.guiqula --calc c1` prints the pyqula script of a calculation.
- `guiqula serve project.guiqula` runs a session without a window that other programs drive.

## Claude and other programs

File > Allow remote control (or `guiqula --remote`) lets programs on the same computer drive
the window through a local port protected by a token. `guiqula mcp` is an MCP server over
that API; register it with Claude Code:

```
claude mcp add guiqula -- guiqula mcp
```

Claude can then read the document, add terms, run calculations, look at the results, the
plots and the window, and explain pyqula's documentation of every entry. Without a running
window, the MCP server runs a session of its own.

## Plugins

A plugin package adds lattices, operations, terms or calculations: see `plugin_template/`.
A single Python file in the user's plugins folder works too (Help > Plugins).

## Development

Nothing needs installing in a source checkout: `PYTHONPATH=src python -m guiqula`, and
`python -m pytest` runs the tests (offscreen Qt, worker processes). `PLAN.md` is the
design document, `CLAUDE.md` the maintainer's guide.

## License

GPL-3.0-or-later (see `LICENSE`), like pyqula.
