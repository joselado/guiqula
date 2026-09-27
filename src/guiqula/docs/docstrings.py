"""pyqula's docstrings, read from its source without importing it (decision
13.13, open point 1: the UI process never loads pyqula, 13.15).

A target names a pyqula callable as the registry does: ``h.add_zeeman`` (a
Hamiltonian method), ``g.get_supercell`` (a Geometry method),
``disorder.anderson`` or ``classicalspin.SpinModel.add_heisenberg`` (a
module, then attributes). The source of the pyqula copy in use (the one
vendoring finds, so an override's help matches its code) is parsed once
per module; a name is followed through ``from . import x`` and ``from .x
import y`` and through module-level aliases, and ``@get_docstring(f)``
(pyqula's helptk, which copies f's docstring at import time) is followed
to f. The docstring is cleaned as inspect.getdoc cleans it; a test checks
every registry target against inspect.getdoc of the imported pyqula.
"""
import ast
from functools import lru_cache
from pathlib import Path

from guiqula import vendoring

OBJECTS = {"h": "hamiltonians.Hamiltonian", "g": "geometry.Geometry"}


def package_dir():
    """The pyqula package directory in use (not imported)."""
    return vendoring.find_pyqula_dir()[1] / "pyqula"


@lru_cache(maxsize=None)
def _module(root, dotted):
    """(tree, path) of a module of the package, or None."""
    base = Path(root).joinpath(*dotted.split(".")) if dotted else Path(root)
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file():
            return ast.parse(path.read_text(encoding="utf-8"), str(path)), path
    return None


def _relative(module, level, name, is_package):
    """The dotted module a relative import names from module."""
    parts = module.split(".") if module else []
    if not is_package:
        parts = parts[:-1]
    parts = parts[:len(parts) - (level - 1)] if level > 1 else parts
    return ".".join(parts + ([name] if name else []))


def _bindings(root, module):
    """{name: node or ("module", dotted) or ("from", dotted, attribute) or
    ("alias", expression)} of a module's top level."""
    found = _module(root, module)
    if found is None:
        return None
    tree, path = found
    is_package = path.name == "__init__.py"
    names = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names[node.name] = node
        elif isinstance(node, ast.ImportFrom) and node.names[0].name == "*" and (
                node.level > 0 or (node.module or "").startswith("pyqula")):
            source = _relative(module, node.level, node.module, is_package) if node.level \
                else node.module[len("pyqula"):].lstrip(".")
            names.setdefault("*", []).append(source)      # searched after the names
        elif isinstance(node, ast.ImportFrom) and node.level > 0:
            source = _relative(module, node.level, node.module, is_package)
            for alias in node.names:
                if _module(root, f"{source}.{alias.name}" if source else alias.name) is not None:
                    names[alias.asname or alias.name] = ("module", f"{source}.{alias.name}"
                                                         if source else alias.name)
                else:
                    names[alias.asname or alias.name] = ("from", source, alias.name)
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pyqula"):
            source = node.module[len("pyqula"):].lstrip(".")
            for alias in node.names:
                full = f"{source}.{alias.name}" if source else alias.name
                names[alias.asname or alias.name] = ("module", full) \
                    if _module(root, full) is not None else ("from", source, alias.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            names[node.targets[0].id] = ("alias", node.value)
    return names


def _lookup(root, module, name, depth=0):
    """The definition node a name of a module stands for, with its module."""
    if depth > 12:
        return None
    names = _bindings(root, module)
    if names is None:
        return None
    if name not in names:
        for source in reversed(names.get("*", [])):       # from .x import *: the last wins
            found = _lookup(root, source, name, depth + 1)
            if found is not None:
                return found
        return None
    value = names[name]
    if isinstance(value, ast.AST):
        return value, module
    if value[0] == "module":
        return ("module", value[1]), value[1]
    if value[0] == "from":
        return _lookup(root, value[1], value[2], depth + 1)
    return _expression(root, module, value[1], depth + 1)


def _expression(root, module, node, depth=0):
    """The definition a Name or an Attribute chain names."""
    if isinstance(node, ast.Name):
        return _lookup(root, module, node.id, depth)
    if isinstance(node, ast.Attribute):
        base = _expression(root, module, node.value, depth)
        if base is None:
            return None
        return _member(root, base, node.attr, depth)
    return None


def _member(root, found, attribute, depth=0):
    """An attribute of a module or a class definition."""
    definition, module = found
    if isinstance(definition, tuple) and definition[0] == "module":
        return _lookup(root, definition[1], attribute, depth)
    if isinstance(definition, ast.ClassDef):
        for node in definition.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and node.name == attribute:
                return node, module
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == attribute for t in node.targets):
                return _expression(root, module, node.value, depth + 1)
    return None


def _doc(root, found, depth=0):
    """The docstring of a definition, following @get_docstring(f)."""
    definition, module = found
    if isinstance(definition, tuple):             # a module
        tree = _module(root, definition[1])
        return ast.get_docstring(tree[0]) if tree else None
    for decorator in getattr(definition, "decorator_list", []):
        if isinstance(decorator, ast.Call) and getattr(decorator.func, "id", None) == \
                "get_docstring" and decorator.args and depth < 12:
            source = _expression(root, module, decorator.args[0])
            return _doc(root, source, depth + 1) if source is not None else None
    return ast.get_docstring(definition)


def resolve(target, root=None):
    """(definition, module) of a target, or None."""
    root = str(root or package_dir())
    head, _, rest = target.partition(".")
    dotted = f"{OBJECTS[head]}.{rest}" if head in OBJECTS else target
    parts = dotted.split(".")
    for split in range(len(parts) - 1, 0, -1):          # the longest module prefix
        module = ".".join(parts[:split])
        if _module(root, module) is None:
            continue
        found = _lookup(root, module, parts[split])
        for attribute in parts[split + 1:]:
            found = _member(root, found, attribute) if found is not None else None
        return found
    return None


def docstring(target, root=None):
    """The cleaned docstring of a pyqula target, or None (none, or not found)."""
    found = resolve(target, root)
    if found is None:
        return None
    return _doc(str(root or package_dir()), found)
