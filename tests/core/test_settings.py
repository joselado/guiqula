"""The settings file (PLAN.md phase 5, design item 8): defaults for what
is missing or broken, checked values, the recent files."""
import json

import pytest

from guiqula.io import settings


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("GUIQULA_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"


def test_defaults_and_round_trip(config):
    assert settings.path() == config / "settings.json"
    assert settings.load() == settings.DEFAULTS
    settings.put("theme", "dark")
    settings.put("always_trust", True)
    assert settings.load()["theme"] == "dark" and settings.get("always_trust") is True
    with pytest.raises(settings.SettingsError):
        settings.put("theme", "purple")
    with pytest.raises(settings.SettingsError):
        settings.put("nope", 1)
    with pytest.raises(settings.SettingsError):
        settings.put("always_trust", "yes")
    # the file holds what was set, not the defaults: a default can change later
    assert json.loads(settings.path().read_text()) == {"theme": "dark", "always_trust": True}
    assert settings.chosen("theme") and not settings.chosen("renderer_3d")


def test_a_broken_file_gives_the_defaults_and_unknown_keys_stay(config):
    config.mkdir()
    (config / "settings.json").write_text("{not json")
    assert settings.load() == settings.DEFAULTS
    (config / "settings.json").write_text(json.dumps(
        {"theme": "purple", "always_trust": "yes", "recent": [1, "a.guiqula"], "later": 3}))
    values = settings.load()
    assert values["theme"] == "system" and values["always_trust"] is False
    assert values["recent"] == ["a.guiqula"] and values["later"] == 3
    settings.put("theme", "light")
    assert json.loads((config / "settings.json").read_text())["later"] == 3


def test_recent_files(config):
    for i in range(12):
        settings.add_recent(f"/p/{i}.guiqula")
    settings.add_recent("/p/3.guiqula")
    recent = settings.get("recent")
    assert recent[0] == "/p/3.guiqula" and len(recent) == settings.RECENT_LIMIT
    assert recent.count("/p/3.guiqula") == 1 and "/p/0.guiqula" not in recent
