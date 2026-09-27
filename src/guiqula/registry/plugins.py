"""Plugins (PLAN.md 3.2; phase 6, part 2): installed packages that add
registry entries (lattices, geometry ops, terms, mean fields, models,
calculations) without changing guiqula.

A plugin is a distribution that declares an entry point in the group
``guiqula.plugins``:

    [project.entry-points."guiqula.plugins"]
    example = "guiqula_example_plugin"

The value names a module whose import registers entries with
``guiqula.registry.entry(...)``, as guiqula's own registry modules do (or
``module:function``, a function that does it when called). A Python file
in the user's plugins folder (``plugins`` in the user configuration
directory, $GUIQULA_CONFIG_DIR/plugins when set) is one too, without any
packaging: each ``*.py`` there is imported the same way. The registry
loads the plugins right after its own entries, in every process that asks
for an entry: the window, which builds its palettes and forms from them,
and the workers, which run them. So a plugin module follows the registry's
rule: pyqula is imported inside functions only, since the window must never
load pyqula (13.15); a plugin that loads it anyway is loaded, with a
warning.

A plugin that fails to load (an exception on import, a kind that is taken)
is left out whole, what it registered before failing removed, and recorded
in PROBLEMS; nothing else changes. The entries of a plugin carry its
distribution's name (``EntrySpec.plugin``). A document that uses an entry
no installed plugin provides still opens: the entry is skipped and flagged
(14.3), like any invalid entry.

$GUIQULA_NO_PLUGINS (any value but "" and "0") loads none: the test suite
sets it, so that a plugin installed on the machine cannot change its
results, and it helps to start without a plugin that breaks something.
Pure Python, no pyqula, no Qt.
"""
import importlib.metadata
import importlib.util
import os
import sys
import time
import traceback

GROUP = "guiqula.plugins"
HEAVY = ("pyqula", "jax", "numba")      # what the window must not load (13.15)
LOADED = []      # [{"name", "distribution", "version", "entries": [[family, kind]], "seconds"}]
PROBLEMS = []    # [{"name", "distribution", "error" or "warning", "traceback"}]


def disabled():
    return os.environ.get("GUIQULA_NO_PLUGINS", "") not in ("", "0")


def directory():
    """The user's plugins folder."""
    from guiqula import env
    return env.user_config_dir() / "plugins"


def discover():
    """The entry points of the group, by name (none when disabled)."""
    if disabled():
        return []
    try:
        points = importlib.metadata.entry_points(group=GROUP)
    except Exception as error:          # a broken distribution's metadata
        PROBLEMS.append({"name": GROUP, "distribution": "", "error": f"could not list the "
                                                                     f"plugins: {error}"})
        return []
    unique = {}
    for point in points:                # the same distribution twice on sys.path: once
        unique.setdefault((point.name, point.value), point)
    return sorted(unique.values(), key=lambda p: p.name)


def load(catalogue, tagging):
    """Load every plugin into catalogue ({family: {kind: spec}});
    tagging(name) makes the registry tag what is registered meanwhile with
    that distribution name (None: stop)."""
    for point in discover():
        _load_one(point.name, point.dist.name if point.dist is not None else "",
                  point.dist.version if point.dist is not None else "", point.load,
                  catalogue, tagging)
    folder = directory()
    if disabled() or not folder.is_dir():
        return
    for path in sorted(folder.glob("*.py")):
        _load_one(path.stem, f"{folder.name}/{path.name}", "", lambda p=path: _import_file(p),
                  catalogue, tagging)


def _import_file(path):
    """Import a file of the plugins folder as the module guiqula_plugins.<name>."""
    name = f"guiqula_plugins.{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def _load_one(name, distribution, version, load, catalogue, tagging):
    before = {family: dict(table) for family, table in catalogue.items()}
    heavy = {m for m in HEAVY if m in sys.modules}
    start = time.perf_counter()
    tagging(distribution or name)
    try:
        loaded = load()
        if callable(loaded):
            loaded()
    except Exception as error:
        for family, table in catalogue.items():         # left out whole
            table.clear()
            table.update(before[family])
        PROBLEMS.append({"name": name, "distribution": distribution,
                         "error": f"{type(error).__name__}: {error}",
                         "traceback": traceback.format_exc()})
        return
    finally:
        tagging(None)
    added = [[family, kind] for family, table in catalogue.items()
             for kind in table if kind not in before[family]]
    LOADED.append({"name": name, "distribution": distribution, "version": version,
                   "entries": added, "seconds": time.perf_counter() - start})
    pulled = [m for m in HEAVY if m in sys.modules and m not in heavy]
    if pulled:
        PROBLEMS.append({"name": name, "distribution": distribution,
                         "warning": f"imports {', '.join(pulled)} when it is loaded: import "
                                    f"pyqula inside the functions of its entries, so that the "
                                    f"window starts without it"})


def describe():
    """What was loaded and what went wrong, for the help and the remote API."""
    return {"disabled": disabled(), "loaded": [dict(p) for p in LOADED],
            "problems": [{k: v for k, v in p.items() if k != "traceback"} for p in PROBLEMS]}


def missing(family, kind):
    """Why a document's entry has no registry entry: the problem text."""
    text = f"unknown {family} {kind!r}: neither guiqula nor an installed plugin provides it"
    failed = [p for p in PROBLEMS if "error" in p]
    if failed:
        text += " (" + "; ".join(f"plugin {p['distribution'] or p['name']} failed to load: "
                                 f"{p['error']}" for p in failed) + ")"
    elif disabled():
        text += " (plugins are off: $GUIQULA_NO_PLUGINS)"
    return text
