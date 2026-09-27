"""The in-app help reads pyqula's docstrings from its source, without
importing it (decision 13.13, open point 1): for every pyqula call behind a
registry entry, the text equals inspect.getdoc of the imported pyqula."""
import importlib
import inspect

import pytest

from guiqula.docs import docstrings
from guiqula.docs.entries import pyqula_targets
from guiqula.registry import base as registry

TARGETS = sorted({t for spec in registry.entries() for t in pyqula_targets(spec)})


def imported(target):
    head, _, rest = target.partition(".")
    dotted = f"{docstrings.OBJECTS[head]}.{rest}" if head in docstrings.OBJECTS else target
    parts = dotted.split(".")
    for split in range(len(parts) - 1, 0, -1):
        try:
            obj = importlib.import_module("pyqula." + ".".join(parts[:split]))
        except ImportError:
            continue
        for attribute in parts[split:]:
            obj = getattr(obj, attribute)
        return obj
    raise LookupError(target)


def test_there_are_targets():
    assert len(TARGETS) > 60


@pytest.mark.parametrize("target", TARGETS)
def test_docstring_as_pyqula_gives_it(pyqula, target):
    assert docstrings.resolve(target) is not None, f"{target} is not found in the source"
    assert docstrings.docstring(target) == inspect.getdoc(imported(target))
