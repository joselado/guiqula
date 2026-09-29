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
  atoms: "matplotlib" (mplot3d) or "pyvista" (turned and zoomed with the
  mouse as in a pyvista window; the optional [3d] extra). matplotlib unless
  the user chooses pyvista.

A missing, unreadable or malformed file gives the defaults (a broken
settings file must not stop the program); unknown keys are kept, so an
older version does not erase what a newer one wrote.
"""
import json
import os

from guiqula import env

FILE = "settings.json"
RECENT_LIMIT = 10
DEFAULTS = {"theme": "system", "always_trust": False, "recent": [], "remote": False,
            "run_at_once": True, "renderer_3d": "matplotlib"}
SWITCHES = ("always_trust", "remote", "run_at_once")       # true or false
CHOICES = {"theme": ("system", "light", "dark"), "renderer_3d": ("matplotlib", "pyvista")}


class SettingsError(ValueError):
    pass


def path():
    return env.user_config_dir() / FILE


def load():
    """The settings, defaults filled in for what is missing or invalid."""
    try:
        stored = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
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


def put(name, value):
    """Change one setting; returns the settings."""
    if name not in DEFAULTS:
        raise SettingsError(f"unknown setting {name!r}; known: {sorted(DEFAULTS)}")
    if name in CHOICES and value not in CHOICES[name]:
        raise SettingsError(f"{name} must be one of {CHOICES[name]}, not {value!r}")
    if name in SWITCHES and not isinstance(value, bool):
        raise SettingsError(f"{name} must be true or false")
    values = load()
    values[name] = value
    save(values)
    return values


def add_recent(file_path):
    """Put a project file first in the recent list; returns the list."""
    name = str(file_path)
    recent = [name] + [p for p in load()["recent"] if p != name]
    return put("recent", recent[:RECENT_LIMIT])["recent"]
