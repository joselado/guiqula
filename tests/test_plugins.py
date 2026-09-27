"""Plugins (registry/plugins.py; PLAN.md phase 6, part 2): distributions
that declare a "guiqula.plugins" entry point add registry entries, in the
window's process and in the workers; a broken one is left out whole. Each
check runs in a fresh interpreter (the registry loads once per process),
with fake installed distributions on a temporary path; the test suite
itself runs with $GUIQULA_NO_PLUGINS set."""
import json
import os
import shutil
import textwrap

import pytest

TEMPLATE = "plugin_template"


def install(site, name, module, source=None, copy_from=None, value=None):
    """A distribution as pip leaves it: the package and its .dist-info."""
    package = site / module
    if copy_from is not None:
        shutil.copytree(copy_from, package)
    else:
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(textwrap.dedent(source))
    info = site / f"{name.replace('-', '_')}-0.1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1\n")
    (info / "entry_points.txt").write_text(f"[guiqula.plugins]\n{module} = {value or module}\n")


@pytest.fixture
def site(tmp_path, repo):
    site = tmp_path / "site"
    site.mkdir()
    install(site, "guiqula-example-plugin", "guiqula_example_plugin",
            copy_from=repo / TEMPLATE / "src" / "guiqula_example_plugin")
    return site


@pytest.fixture
def with_plugins(run_python, site):
    def run(code, timeout=300, env=None):
        result = run_python(textwrap.dedent(code), env_update=dict({
            "GUIQULA_NO_PLUGINS": "", "PYTHONPATH": f"{site}{os.pathsep}{run_python.src}"},
            **(env or {})),
            timeout=timeout)
        assert result.returncode == 0, result.stderr[-3000:]
        return json.loads(result.stdout.strip().splitlines()[-1])
    return run


def test_a_plugin_entry_is_registered_and_runs_in_the_workers(with_plugins):
    out = with_plugins("""
        import json, sys
        from guiqula import registry
        from guiqula.registry import plugins
        from guiqula.session import Session
        spec = registry.get("term", "chiral_kekule")
        from guiqula.docs import entries
        help = entries.entry_help(spec)
        with Session(warm=False, interactive=False) as session:
            s = session.do("add_system", lattice="honeycomb_lattice")
            session.do("set_construction", system=s, has_spin=False)
            session.do("add_geometry_op", system=s, kind="supercell", params={"n": [3, 3, 1]})
            t = session.do("add_term", system=s, kind="chiral_kekule", params={"t1": 0.2})
            c = session.do("add_calculation", system=s, kind="bands", params={"nk": 10})
            job = session.run_calculation(c, wait=True, timeout=300)
            data = session.document.model_dump(mode="json")
            system = data["systems"][0]
            print(json.dumps({"plugin": spec.plugin, "described": spec.describe()["plugin"],
                              "recorded": session.document.find(t)[-1].plugin,
                              "saved": system["hamiltonian"]["terms"][0].get("plugin"),
                              "own": ["plugin" in system["geometry"]["base"],
                                      "plugin" in system["geometry"]["ops"][0],
                                      "plugin" in data["calculations"][0]],
                              "used": session.document.plugins(),
                              "page": entries.plugins_page(session.document),
                              "loaded": plugins.describe()["loaded"], "status": job.status,
                              "error": job.error, "pyqula": "pyqula" in sys.modules,
                              "help": help,
                              "shape": list(session.result(c).arrays["energies"].shape)}))
    """)
    assert out["plugin"] == out["described"] == "guiqula-example-plugin"
    # the document records the plugin and its version (phase-6 answer 37), and only there
    assert out["recorded"] == out["saved"] == "guiqula-example-plugin==0.1"
    assert out["own"] == [False, False, False] and out["used"] == ["guiqula-example-plugin==0.1"]
    assert "## Used by the open document\n\n- guiqula-example-plugin==0.1: installed" in out["page"]
    assert out["loaded"][0]["entries"] == [["term", "chiral_kekule"]]
    assert out["loaded"][0]["version"] == "0.1"
    assert out["status"] == "done", out["error"]
    assert out["shape"] == [10, 18] and out["pyqula"] is False     # the UI side stays light
    assert "period-tripling" in out["help"]                         # its guide= anchor
    assert "From the plugin guiqula-example-plugin" in out["help"]


def test_broken_and_colliding_plugins_are_left_out(site, with_plugins):
    install(site, "broken-plugin", "broken_plugin", """
        from guiqula.registry import Call, entry
        from guiqula.registry.params import FieldParam
        entry("term", "half_registered", "Half", FieldParam("x", 0.1),
              call=Call("h.add_onsite", "x"))
        raise RuntimeError("something is missing")
    """)
    install(site, "colliding-plugin", "colliding_plugin", """
        from guiqula.registry import Call, entry
        from guiqula.registry.params import FieldParam
        entry("term", "first_ok", "First", FieldParam("x", 0.1), call=Call("h.add_onsite", "x"))
        entry("term", "onsite", "Mine", FieldParam("x", 0.1), call=Call("h.add_onsite", "x"))
    """)
    install(site, "heavy-plugin", "heavy_plugin", """
        import pyqula.geometry
        from guiqula.registry import Call, entry
        from guiqula.registry.params import FieldParam
        entry("term", "heavy_term", "Heavy", FieldParam("x", 0.1), call=Call("h.add_onsite", "x"))
    """)
    out = with_plugins("""
        import json
        from guiqula import registry
        from guiqula.registry import plugins
        kinds = registry.kinds("term")
        print(json.dumps({"kinds": kinds, "onsite": registry.get("term", "onsite").plugin,
                          "state": plugins.describe()}))
    """)
    assert "half_registered" not in out["kinds"] and "first_ok" not in out["kinds"]
    assert "onsite" in out["kinds"] and out["onsite"] == ""        # guiqula's own is kept
    assert {"chiral_kekule", "heavy_term"} <= set(out["kinds"])     # the others still load
    problems = {p["distribution"]: p for p in out["state"]["problems"]}
    assert problems["broken-plugin"]["error"] == "RuntimeError: something is missing"
    assert "registered twice" in problems["colliding-plugin"]["error"]
    assert "imports pyqula" in problems["heavy-plugin"]["warning"]
    assert sorted(p["distribution"] for p in out["state"]["loaded"]) == \
        ["guiqula-example-plugin", "heavy-plugin"]


def test_a_document_with_a_missing_plugin_entry_opens(site, with_plugins):
    out = with_plugins("""
        import json, os
        os.environ["GUIQULA_NO_PLUGINS"] = "1"
        from guiqula.commands import Dispatcher
        from guiqula.core.document import Document
        from guiqula.registry import pipeline
        d = Dispatcher()
        s = d.do("add_system", lattice="honeycomb_lattice")
        data = d.document.model_dump(mode="json")
        data["systems"][0]["hamiltonian"]["terms"] += [
            {"id": "t1", "kind": "chiral_kekule", "params": {"t1": 0.2}},
            {"id": "t2", "kind": "chiral_kekule", "params": {"t1": 0.2},
             "plugin": "guiqula-example-plugin==0.1"}]
        document = Document.from_data(data)
        plan = pipeline.plan_system(document, s)
        stages = {st.id: st for st in plan.stages}
        print(json.dumps({"problem": stages["t1"].problem, "applied": stages["t1"].applied,
                          "named": stages["t2"].problem, "stages": len(plan.stages),
                          "saved": json.loads(document.to_json())["systems"][0]["hamiltonian"]
                                             ["terms"][1]["plugin"]}))
    """)
    assert out["problem"].startswith("unknown term 'chiral_kekule': neither guiqula nor an "
                                     "installed plugin provides it")
    assert "plugins are off" in out["problem"] and out["applied"] is False
    assert out["named"] == ("unknown term 'chiral_kekule': it needs the plugin "
                            "guiqula-example-plugin==0.1 (plugins are off: $GUIQULA_NO_PLUGINS)")
    assert out["saved"] == "guiqula-example-plugin==0.1"      # kept on a round trip


def test_files_in_the_plugins_folder(tmp_path, with_plugins):
    folder = tmp_path / "config" / "plugins"
    folder.mkdir(parents=True)
    (folder / "gate.py").write_text(textwrap.dedent("""
        from guiqula.registry import Call, entry
        from guiqula.registry.params import FieldParam
        entry("term", "gate_onsite", "Gate", FieldParam("v", 0.3, "v"),
              call=Call("h.add_onsite", "v"))
    """))
    (folder / "broken.py").write_text("raise ImportError('not today')\n")
    # a script, not a plugin: it parses the command line, which exits (loaded before gate.py)
    (folder / "exits.py").write_text("import argparse\n"
                                     "argparse.ArgumentParser().parse_args(['--nope'])\n")
    out = with_plugins("""
        import json
        from guiqula import registry
        from guiqula.registry import plugins
        from guiqula.session import Session
        with Session(warm=False, interactive=False) as session:
            s = session.do("add_system", lattice="chain")
            session.do("add_term", system=s, kind="gate_onsite", params={"v": 0.25})
            c = session.do("add_calculation", system=s, kind="bands", params={"nk": 5})
            job = session.run_calculation(c, wait=True, timeout=300)
            print(json.dumps({"plugin": registry.get("term", "gate_onsite").plugin,
                              "status": job.status, "error": job.error,
                              "energies": session.result(c).arrays["energies"].ravel().tolist(),
                              "state": plugins.describe()}))
    """, env={"GUIQULA_CONFIG_DIR": str(tmp_path / "config")})
    assert out["plugin"] == "plugins/gate.py"
    assert out["status"] == "done", out["error"]      # the workers load the folder too
    assert all(abs(e - 0.25) < 2.0 + 1e-9 for e in out["energies"])
    problems = {p["distribution"]: p for p in out["state"]["problems"]}
    assert problems["plugins/broken.py"]["error"] == "ImportError: not today"
    assert problems["plugins/exits.py"]["error"].startswith("SystemExit")


def test_the_template_tests_pass(site, run_python, repo, tmp_path):
    result = run_python(
        f"import sys, pytest; sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', "
        f"'--rootdir', {str(repo / TEMPLATE)!r}, {str(repo / TEMPLATE / 'tests')!r}]))",
        env_update={"GUIQULA_NO_PLUGINS": "",
                    "PYTHONPATH": f"{site}{os.pathsep}{run_python.src}"},
        timeout=600)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert "3 passed" in result.stdout


def test_the_plugins_page_and_the_missing_entry_text(monkeypatch):
    from guiqula.docs import entries
    from guiqula.registry import plugins
    monkeypatch.setenv("GUIQULA_NO_PLUGINS", "")
    monkeypatch.setattr(plugins, "LOADED", [{"name": "x", "distribution": "guiqula-x",
                                             "version": "1.0", "entries": [["term", "haldane"]],
                                             "seconds": 0.01}])
    monkeypatch.setattr(plugins, "PROBLEMS", [{"name": "y", "distribution": "guiqula-y",
                                               "error": "ImportError: no"}])
    page = entries.plugins_page()
    assert "## guiqula-x 1.0" in page and "term `haldane`: Haldane coupling" in page
    assert "**guiqula-y**: failed to load, left out: ImportError: no" in page
    assert plugins.missing("term", "z").endswith("(plugin guiqula-y failed to load: "
                                                 "ImportError: no)")
    # the plugin a document records for the entry (phase-6 answer 37)
    assert plugins.missing("term", "z", "guiqula-q==3.1") == \
        "unknown term 'z': it needs the plugin guiqula-q==3.1, which is not installed"
    assert plugins.missing("term", "z", "guiqula-y==0.5") == \
        "unknown term 'z': it needs the plugin guiqula-y==0.5, which failed to load: ImportError: no"
    assert plugins.missing("term", "z", "guiqula-x==0.9") == \
        ("unknown term 'z': the plugin guiqula-x 1.0 is installed but does not provide it "
         "(the document was made with guiqula-x==0.9)")
    from guiqula.core.document import Document
    document = Document.from_data({"systems": [{"id": "s1", "geometry": {
        "base": {"kind": "honeycomb_lattice", "plugin": "guiqula-q==3.1"},
        "ops": [{"id": "o1", "kind": "z", "plugin": "guiqula-x==1.0"}]}}]})
    page = entries.plugins_page(document)
    assert ("## Used by the open document\n\n- guiqula-q==3.1: **not installed**\n"
            "- guiqula-x==1.0: installed") in page
