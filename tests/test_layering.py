"""Import rules between the layers (PLAN.md section 3, CLAUDE.md "Layering").

- Qt (PySide6, shiboken6, pyqtgraph, matplotlib's Qt backends) only in ui/
  and remote/.
- pyqula only in engine/ and worker/, and inside function bodies in
  registry/: the UI imports the registry to build its forms, and the UI
  process must stay free of pyqula (PLAN.md 13.15). Never in core/,
  commands/, io/, ui/, remote/ or the top-level modules.
- guiqula.engine only from engine/ and the worker process side of worker/;
  worker/client.py and worker/protocol.py run in the UI process and import
  neither pyqula nor the engine.
"""
import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "guiqula"

QT_ROOTS = {"PySide6", "shiboken6", "pyqtgraph", "PyQt5", "PyQt6", "qtpy"}
QT_ALLOWED = {"ui", "remote"}
PYQULA_ALLOWED = {"engine", "worker"}
PYQULA_LAZY_ONLY = {"registry"}
# modules of the UI process: never pyqula, never the engine (13.15)
UI_PROCESS = {"worker/client.py", "worker/protocol.py"}
ENGINE_FORBIDDEN = {"ui", "remote", "core", "commands", "io", "registry"}


def imports(tree):
    """Yield (module name, lineno, at module level) for every import."""
    def walk(node, top):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import):
                for alias in child.names:
                    yield alias.name, child.lineno, top
            elif isinstance(child, ast.ImportFrom) and child.level == 0 and child.module:
                yield child.module, child.lineno, top
            nested = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            yield from walk(child, top and not nested)
    yield from walk(tree, True)


def is_qt(name):
    return (name.split(".")[0] in QT_ROOTS
            or name.startswith("matplotlib.backends.backend_qt"))


def violations(source, layer, module=""):
    """Rule violations in one module; layer is its subpackage ('' for top
    level), module its path relative to the package."""
    found = []
    for name, line, top in imports(ast.parse(source)):
        engine = name == "guiqula.engine" or name.startswith("guiqula.engine.")
        if engine and (layer in ENGINE_FORBIDDEN or module in UI_PROCESS or layer == ""):
            found.append(f"line {line}: {name!r} imported outside engine/ and the worker process")
        if module in UI_PROCESS and name.split(".")[0] == "pyqula":
            found.append(f"line {line}: pyqula import {name!r} in {module}, which runs in the UI process")
            continue
        if is_qt(name) and layer not in QT_ALLOWED:
            found.append(f"line {line}: Qt import {name!r} outside ui/ and remote/")
        if name.split(".")[0] == "pyqula" and layer not in PYQULA_ALLOWED:
            if layer in PYQULA_LAZY_ONLY and not top:
                continue
            where = "at module level in registry/" if layer in PYQULA_LAZY_ONLY \
                else f"in {layer or 'the top-level package'}/"
            found.append(f"line {line}: pyqula import {name!r} {where}")
    return found


def modules():
    files = sorted(PACKAGE.rglob("*.py"))
    files = [f for f in files if "_vendor" not in f.relative_to(PACKAGE).parts]
    return files


def test_package_is_scanned():
    names = {f.relative_to(PACKAGE).as_posix() for f in modules()}
    assert {"__init__.py", "ui/app.py", "core/__init__.py"} <= names


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.relative_to(PACKAGE).as_posix())
def test_layering(path):
    parts = path.relative_to(PACKAGE).parts
    layer = parts[0] if len(parts) > 1 else ""
    module = path.relative_to(PACKAGE).as_posix()
    assert violations(path.read_text(), layer, module) == []


@pytest.mark.parametrize("source, layer, bad", [
    ("from PySide6.QtWidgets import QLabel", "core", True),
    ("import shiboken6", "", True),
    ("from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg", "engine", True),
    ("from PySide6.QtWidgets import QLabel", "ui", False),
    ("import matplotlib.pyplot", "core", False),
    ("from pyqula import geometry", "commands", True),
    ("def f():\n    import pyqula.geometry", "ui", True),
    ("from pyqula import geometry", "registry", True),
    ("def build(h):\n    from pyqula import geometry", "registry", False),
    ("from pyqula import geometry", "engine", False),
])
def test_checker_catches(source, layer, bad):
    assert bool(violations(source, layer)) == bad


@pytest.mark.parametrize("source, layer, module, bad", [
    ("from guiqula.engine.build import build_system", "ui", "ui/x.py", True),
    ("def f():\n    from guiqula.engine import calculations", "", "session.py", True),
    ("def f():\n    from pyqula import geometry", "worker", "worker/client.py", True),
    ("from guiqula.engine.calculations import run_calculation", "worker", "worker/process.py", False),
    ("from guiqula.engine import build", "worker", "worker/client.py", True),
])
def test_checker_catches_process_rules(source, layer, module, bad):
    assert bool(violations(source, layer, module)) == bad
