---
paths:
  - "src/guiqula/engine/**"
  - "src/guiqula/worker/**"
  - "src/guiqula/registry/**"
  - "src/guiqula/docs/**"
  - "src/guiqula/vendoring.py"
  - "tests/engine/**"
  - "tests/worker/**"
  - "tests/test_help.py"
  - "tests/test_plugins.py"
  - "vendor/**"
  - "tools/update_vendor.sh"
  - "plugin_template/**"
---

# The registry, the engine, the worker and pyqula

What CLAUDE.md leaves to this file, loaded when a file of the registry, the engine, the
worker, the help or the vendored copy is read or edited: how an entry is declared, tested
and exported, what the plan and the build do, and what the refresh of `vendor/` does.

## Adding an entry

- One `entry(...)` call in the family's module (`lattices.py`, `geometry_ops.py`,
  `terms.py`, `meanfield.py`, `calculations.py`, `classical.py` for the classical models,
  terms and calculations) plus its case in `tests/engine/test_entries.py`; a completeness
  test fails otherwise, and the case is also exported and run by
  `tests/engine/test_script_export.py`. A plugin's entries are tested the same way
  (`plugin_template/tests/`).
- A declarative `Call("h.add_zeeman", "m")` drives both the engine and the script export; a
  custom entry gives `apply` and `script`, names the pyqula modules its script uses
  (`modules=`) and, for the help, its pyqula calls (`pyqula=`).
- An entry's `systems` names the system kinds it applies to; `guide=` names its guide
  sections ("guiqula: X" for guiqula's own guide), and `tests/test_help.py` checks every
  anchor. A renamed upstream guide section breaks these anchors, which is the one fix that
  may join a vendor refresh (decision 13.13).
- A calculation's `plot` is a dict or a callable of the parameters (and the arrays); the
  plot kinds are listed in `ui/plots.py`. A plot spec's `picks` names what its axes carry
  (`core/picks.py`: `AXES` and `fixed`); the targets of a picked value (`registry/picks.py`)
  are computed from the parameters' `quantity`, never listed by pairs. A result on the atoms
  yields sites; a bands or spectral-function result carries `kpoints`, reduced, (0, 3) in 0D.
- A parameter declared `FieldParam(bond=True)` is evaluated at the bond midpoints
  (`core/bonds.py`: the mean of the two ends for a site Field, a region holding a bond when
  it holds both).
- `sweeps.py` holds the calculation that runs another one over parameter values (exported
  as a loop) and `command`, the mutation that sets one number of the Document (sliders,
  picks). `kpaths.py` holds the points of a k-path, pyqula's default one included (walked
  with the Γ it leaves out put first, decision 89), and the names of the points along one.
- An entry that `runs_code` (`python_nodes.py`) is invalid unless planned with
  `trusted=True`, the Session's flag, never the Document's; the UI plans only through
  `Session.plan_system`, `plan_calculation` and `calculation_key`.

## The plan, the build and the worker

- `pipeline.py` plans a system without pyqula: the Hilbert-space pre-scan marks the first
  entry that needs Nambu (`turn_nambu`) so that the mode is set from the whole term stack,
  invalid entries are skipped and flagged, region references are resolved to selections,
  and the stage and calculation keys give staleness; the mean field is the last stage.
- `build.py` executes a plan: a per-stage cache handing out copies, bounded by memory too,
  skip on error, each stochastic entry's `seed` applied by `build.seed` right before it, the
  Hamiltonian turned where the pre-scan said; the interactive
  builds defer the mean field (`meanfield=False`) and go sparse above pyqula's dense limit
  (`sparse_above`).
- `context.py` is what an entry sees while it is applied: its parameters compiled to what
  pyqula takes (a Field becomes a number or a callable of the position), the script text
  of each value (`ctx.code`), and the name lists pyqula itself provides (`source_names`),
  which the worker hands to the UI process for its forms, since that process cannot import
  pyqula.
- `structure.py` gives the canvas its arrays: positions, lattice, sublattice, pyqula's
  first-neighbour bonds, and the Hamiltonian view (onsite, exchange, pairing, every
  hopping's amplitude and phase).
- `worker/process.py` imports the engine inside `main()` only; its `Console` is the Python
  console's interpreter. `client.py`'s `JobManager` runs the interactive and batch workers
  and the console worker, started at its first command, with cancel, respawn, timeouts and
  `request_handler`, which answers a job's REQUEST. `tests/test_layering.py` keeps
  `client.py` and `protocol.py` free of pyqula and the engine, since they run in the UI
  process.
- `plugins.py` loads the plugins right after the built-in entries, in the window and the
  workers alike: the entry points of the group `guiqula.plugins` and the `*.py` of the
  user's plugins folder; `none_declared` reads the `entry_points.txt` files on the path
  first (about 5 ms) and only a file naming the group, or a doubt, costs
  `importlib.metadata`'s 30 ms of the start; a failing plugin is left out whole and listed
  (Help > Plugins); `EntrySpec.plugin` names it; the test suite sets `$GUIQULA_NO_PLUGINS`.
- `cost.py` estimates durations: the cost guard of the window and of `drive.py --run`.

## The help (decision 13.13)

- `docs/guide.py`: pyqula's user guide, `vendor/pyqula_user_guide.md`, in sections; an
  anchor is a heading's text, "Parent > Heading" when repeated; equations become mathtext
  images.
- `docs/docstrings.py`: pyqula's docstrings read from its source with `ast`, following
  imports and `@get_docstring`; `tests/engine/test_help_docstrings.py` checks every one an
  entry needs.
- `docs/entries.py`: an item's help: formula, parameters, the pyqula code with its values,
  docstrings, the guide sections it names and the reference section of each call. Nothing
  in `docs/` imports pyqula.
- `docs/search.py` (decision 159): BM25 over the registry entries and the sections of both
  guides, a word the index lacks read as its close or longer words; the index is built at
  the first search (about 0.6 s) and kept per registry and guide. `tests/test_help.py`
  holds questions with the entry or section each must return first; a change of the
  weights is checked against them.

## The vendored copy

`tools/update_vendor.sh` refreshes the whole of `vendor/pyqula/` from an upstream checkout
(`$PYQULA_SRC`, or the path given) and rewrites `vendor/VENDOR.md` (upstream URL and commit,
uncommitted upstream files that were included, upstream's runtime dependencies to mirror
in `pyproject.toml`), then runs the help tests. A refresh is committed on its own; the one
exception is the fix of registry `guide=` anchors that a renamed upstream guide section
forces, which may join it.
