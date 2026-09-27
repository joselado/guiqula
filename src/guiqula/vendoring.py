"""Put the pyqula copy guiqula uses on sys.path, without importing it.

pyqula imports itself absolutely (``from pyqula import ...``), so the copy
guiqula ships must be importable as top-level ``pyqula`` (PLAN.md section 6,
decision 3). The directory that holds the ``pyqula`` package is looked up in
this order and inserted at the front of sys.path:

1. ``$GUIQULA_PYQULA_PATH``: a development override, pointing either at the
   directory that contains ``pyqula/`` (for example an upstream ``src``) or
   at the ``pyqula`` package directory itself. If it is set it must be valid;
   there is no silent fallback.
2. the application folder of a frozen guiqula (PyInstaller,
   packaging/pyinstaller), which holds pyqula's sources as files;
3. ``guiqula/_vendor``: the copy shipped inside an installed guiqula.
4. ``<checkout>/vendor``: the copy in a source checkout.

When the override is used the interpreter stops writing bytecode, so an
upstream checkout (read-only from guiqula) gets no ``__pycache__``; numba's
cache is redirected by guiqula.env.configure_numba_cache.
"""
import os
import sys
from pathlib import Path

ENV_VAR = "GUIQULA_PYQULA_PATH"

_HERE = Path(__file__).resolve().parent

#: Message of the last failed lookup (None when pyqula was found).
problem = None
#: (origin, directory) of the pyqula copy in use, once found.
location = None


class VendoringError(RuntimeError):
    """No usable pyqula copy, or a different pyqula was imported first."""


def _override_dir(value):
    path = Path(value).expanduser().resolve()
    if (path / "pyqula" / "__init__.py").is_file():
        return path
    if path.name == "pyqula" and (path / "__init__.py").is_file():
        return path.parent
    raise VendoringError(
        f"{ENV_VAR}={value!r} contains no pyqula package: expected "
        f"{path}/pyqula/__init__.py or {path}/__init__.py")


def find_pyqula_dir():
    """Return (origin, directory containing the pyqula package).

    origin is "override", "bundled", "vendored" or "checkout".
    """
    value = os.environ.get(ENV_VAR)
    if value:
        return "override", _override_dir(value)
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen and (Path(frozen) / "pyqula" / "__init__.py").is_file():
        return "bundled", Path(frozen)
    shipped = _HERE / "_vendor"
    if (shipped / "pyqula" / "__init__.py").is_file():
        return "vendored", shipped
    root = _HERE.parents[1]
    checkout = root / "vendor"
    if (_HERE.parent.name == "src" and (checkout / "VENDOR.md").is_file()
            and (checkout / "pyqula" / "__init__.py").is_file()):
        return "checkout", checkout
    raise VendoringError(
        f"no pyqula found: not in {shipped}, not in a source checkout, and "
        f"{ENV_VAR} is not set")


def find_guide():
    """(origin, path) of pyqula's user guide that goes with the pyqula copy
    in use, or None. An override's own guide is used when its tree has one
    (``documentation/user_guide.md`` above the package), so the help matches
    the running code; else the shipped or checkout copy (origin says which)."""
    try:
        origin, directory = find_pyqula_dir()
    except VendoringError:
        return None
    if origin == "override":
        for base in (directory, directory.parent, directory.parent.parent):
            candidate = base / "documentation" / "user_guide.md"
            if candidate.is_file():
                return "override", candidate
    for origin, candidate in (("vendored", _HERE / "_vendor" / "pyqula_user_guide.md"),
                              ("checkout", _HERE.parents[1] / "vendor" /
                               "pyqula_user_guide.md")):
        if candidate.is_file():
            return origin, candidate
    return None


def _check_already_imported(directory):
    module = sys.modules.get("pyqula")
    if module is None:
        return
    files = [getattr(module, "__file__", None)] + list(getattr(module, "__path__", []))
    expected = (directory / "pyqula").resolve()
    for f in files:
        if f and expected in (Path(f).resolve(), *Path(f).resolve().parents):
            return
    raise VendoringError(
        f"a different pyqula was imported before guiqula: {files[0] or files}; "
        f"guiqula uses {expected}")


def ensure_pyqula_on_path(strict=True):
    """Put the pyqula copy at the front of sys.path and return its directory.

    With strict=False a failure is recorded in ``problem`` and None is
    returned instead of raising VendoringError.
    """
    global problem, location
    try:
        origin, directory = find_pyqula_dir()
        _check_already_imported(directory)
    except VendoringError as error:
        problem = str(error)
        location = None
        if strict:
            raise
        return None
    entry = str(directory)
    sys.path[:] = [p for p in sys.path if p != entry]
    sys.path.insert(0, entry)
    if origin == "override":
        sys.dont_write_bytecode = True
    problem = None
    location = (origin, directory)
    return directory


def describe():
    """One line for the status bar and for result provenance."""
    if location is None:
        return f"pyqula: not found ({problem})"
    origin, directory = location
    return f"pyqula: {origin} copy at {directory}"
