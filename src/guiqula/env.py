"""Process environment fixes applied before Qt or numba start.

No Qt import happens here (PLAN.md section 3): PySide6 is located with
importlib.util.find_spec, which finds a package without importing it.
"""
import importlib.util
import os
from pathlib import Path

import platformdirs

APP_NAME = "guiqula"


def user_cache_dir():
    return Path(platformdirs.user_cache_dir(APP_NAME, appauthor=False))


def user_data_dir():
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def configure_numba_cache():
    """Keep numba's on-disk cache in the user cache directory.

    Without this numba writes ``.nbi``/``.nbc`` files next to pyqula's
    sources: inside an installed package, which may be read-only, or inside
    an upstream checkout, which guiqula must never write to. An existing
    NUMBA_CACHE_DIR is respected. Must run before numba is imported.
    """
    os.environ.setdefault("NUMBA_CACHE_DIR", str(user_cache_dir() / "numba"))


def qt_platform_plugin_dir():
    """PySide6's own ``platforms`` plugin directory, or None."""
    spec = importlib.util.find_spec("PySide6")
    if spec is None or not spec.submodule_search_locations:
        return None
    root = Path(next(iter(spec.submodule_search_locations)))
    for candidate in (root / "Qt" / "plugins" / "platforms",   # Linux, macOS
                      root / "plugins" / "platforms"):         # Windows
        if candidate.is_dir():
            return candidate
    return None


def configure_qt(offscreen=False):
    """Set the Qt environment; call before the QApplication is created.

    Under conda, Qt does not find PySide6's platform plugins unless
    QT_QPA_PLATFORM_PLUGIN_PATH points at them (CLAUDE.md, "Headless Qt").
    An explicit setting by the user is kept.
    """
    if offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if "QT_QPA_PLATFORM_PLUGIN_PATH" not in os.environ:
        plugins = qt_platform_plugin_dir()
        if plugins is not None:
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins)
