# A guiqula plugin

A template for adding lattices, geometry operations, Hamiltonian terms, mean fields,
classical models or calculations to [guiqula](../README.md) without changing it. This
one adds pyqula's chiral Kekule hopping as a term.

1. Copy this directory, and rename the package (`src/guiqula_example_plugin`) and the
   distribution (`name` in `pyproject.toml`).
2. Declare your entries in the package's `__init__.py` with `guiqula.registry.entry(...)`,
   as guiqula's own `src/guiqula/registry/*.py` do. Import pyqula inside functions only:
   the window imports your module and must never load pyqula. Every numeric parameter of a
   term is a Field (`FieldParam`).
3. Keep the entry point: `[project.entry-points."guiqula.plugins"]` names your module.
4. Install it into guiqula's environment: `pip install -e .`. guiqula lists it in
   Help > Plugins, with the entries it added and any error; a plugin that fails to load is
   left out and guiqula starts without it. `GUIQULA_NO_PLUGINS=1 guiqula` starts without
   any plugin.
5. Test every entry against a direct pyqula call and run its exported script, as
   `tests/test_example_plugin.py` does: `python -m pytest`.

A document that uses a plugin's entry opens where the plugin is missing too: the entry is
skipped and flagged in the outliner, and everything else builds.
