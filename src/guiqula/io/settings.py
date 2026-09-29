"""User preferences (PLAN.md phase 5, design item 8): a JSON file in the
user config directory ($GUIQULA_CONFIG_DIR overrides it), read and written
whole. Only the window reads it: headless runs (guiqula run, the tests,
tools/drive.py unless asked) never depend on what a user chose.

- ``theme``: "system" (follow the desktop), "light" or "dark";
- ``always_trust``: open files with Python nodes trusted (13.7's global
  switch; off unless the user turns it on);
- ``recent``: the project files opened or saved last, newest first;
- ``remote``: let other programs drive the window through a localhost
  socket (remote control, the Claude add-on, PLAN.md 3.7; off unless the
  user turns it on).
- ``run_at_once``: a calculation runs as soon as it is added or one of its
  parameters is set (from its form, a pick on a plot, a command), through
  the cost guard; off, only when asked (Run, F5). On unless the user turns
  it off (PLAN.md phase 7, answer 48).
- ``renderer_3d``: what draws in 3D, the canvas and the results on the
  atoms: "matplotlib" (mplot3d) or "pyvista" (moved in space as Blender's
  viewport is; the optional [3d] extra). pyvista unless the user chooses
  matplotlib, and matplotlib whenever pyvista is not installed and the user
  never chose it (`chosen`).
- ``plot_text``: the size of the text of every drawing (the labels, the
  ticks, the titles of the plots, the canvas and the k-space tab, and of
  the exported figures): "small", "normal" or "large" (ui/theme.py's
  sizes). normal unless the user chooses another.

A missing, unreadable or malformed file gives the defaults (a broken
settings file must not stop the program); unknown keys are kept, so an
older version does not erase what a newer one wrote. The file holds only
the settings that were set, never the defaults filled in, so that a default
can change (renderer_3d did) without a file written earlier keeping the old
one.
"""
import json
import os

from guiqula import env

FILE = "settings.json"
RECENT_LIMIT = 10
DEFAULTS = {"theme": "system", "always_trust": False, "recent": [], "remote": False,
            "run_at_once": True, "renderer_3d": "pyvista", "plot_text": "normal"}
SWITCHES = ("always_trust", "remote", "run_at_once")       # true or false
CHOICES = {"theme": ("system", "light", "dark"), "renderer_3d": ("matplotlib", "pyvista"),
           "plot_text": ("small", "normal", "large")}


class SettingsError(ValueError):
    pass


def path():
    return env.user_config_dir() / FILE


def _stored():
    """What the file holds, as it is (a broken file holds nothing)."""
    try:
        stored = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


def load():
    """The settings, defaults filled in for what is missing or invalid."""
    stored = _stored()
    values = dict(DEFAULTS, **stored)
    for name, choices in CHOICES.items():
        if values[name] not in choices:
            values[name] = DEFAULTS[name]
    for name in SWITCHES:
        if not isinstance(values[name], bool):
            values[name] = DEFAULTS[name]
    recent = values["recent"] if isinstance(values["recent"], list) else []
    values["recent"] = [p for p in recent if isinstance(p, str)][:RECENT_LIMIT]
    return values


def save(values):
    """Write the settings (atomically: a crash leaves the old file)."""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)


def get(name):
    return load()[name]


def chosen(name):
    """Whether the file holds a value for this setting: the user (or a
    command) set it, and it is not the default filled in."""
    return name in _stored()


def put(name, value):
    """Change one setting; returns the settings."""
    if name not in DEFAULTS:
        raise SettingsError(f"unknown setting {name!r}; known: {sorted(DEFAULTS)}")
    if name in CHOICES and value not in CHOICES[name]:
        raise SettingsError(f"{name} must be one of {CHOICES[name]}, not {value!r}")
    if name in SWITCHES and not isinstance(value, bool):
        raise SettingsError(f"{name} must be true or false")
    stored = _stored()              # only what was set is written, so that `chosen` can tell
    stored[name] = value
    save(stored)
    return load()


def add_recent(file_path):
    """Put a project file first in the recent list; returns the list."""
    name = str(file_path)
    recent = [name] + [p for p in load()["recent"] if p != name]
    return put("recent", recent[:RECENT_LIMIT])["recent"]
