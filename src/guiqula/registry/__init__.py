"""Declarative catalogue of lattices, geometry ops, terms, calculations and
operators: parameter schema, applicability, build function, docs (PLAN.md 3.2).

The UI imports the registry to build its forms, so pyqula may be imported
only inside functions here, never at module level; the UI process must stay
free of pyqula (PLAN.md 13.15, tests/test_layering.py).

Use ``registry.get(family, kind)``, ``registry.kinds(family)`` and
``registry.entries()``; families are "lattice", "geometry_op", "term" and
"calculation".
"""
from guiqula.registry.base import (Call, EntrySpec, G, H, RegistryError, entries,  # noqa: F401
                                   entry, get, kinds, register)
from guiqula.registry.params import ParamError  # noqa: F401
