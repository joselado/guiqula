"""Declarative catalogue of lattices, geometry ops, terms, calculations and
operators: parameter schema, applicability, build function, docs (PLAN.md 3.2).

The UI imports the registry to build its forms, so pyqula may be imported
only inside functions here, never at module level; the UI process must stay
free of pyqula (PLAN.md 13.15, tests/test_layering.py). Phase 1.
"""
