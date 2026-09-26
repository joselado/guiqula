"""tools/drive.py, the headless driver (PLAN.md 3.6), and the phase-2
acceptance tests that go through it: sculpt a preset by command and see it
on the canvas; kill the program and recover the document on restart."""
import json
import os
import subprocess
import sys
import time

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def drive(repo, cwd, *args, timeout=600, env=None):
    return subprocess.run([sys.executable, str(repo / "tools" / "drive.py"), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)


def report_of(result):
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_window_screenshot_without_session(repo, tmp_path):
    result = drive(repo, tmp_path, "--no-session", "--size", "800x600", "--shot", "win.png")
    assert result.returncode == 0, result.stderr
    assert report_of(result)["window"] == [800, 600]
    assert (tmp_path / "win.png").read_bytes().startswith(PNG_MAGIC)


def test_list_widgets(repo, tmp_path):
    result = drive(repo, tmp_path, "--no-session", "--list-widgets")
    assert result.returncode == 0, result.stderr
    for name in ("MainWindow (MainWindow)", "outliner (Outliner)", "properties (PropertiesPanel)", "runButton (QPushButton)",
                 "jobPanel (JobPanel)", "plotView (PlotView)"):
        assert name in result.stdout, name


def test_unknown_widget(repo, tmp_path):
    result = drive(repo, tmp_path, "--no-session", "--widget", "nope", "--shot", "x.png")
    assert result.returncode == 1 and "no widget named 'nope'" in result.stderr
    assert not (tmp_path / "x.png").exists()


def test_document_commands_run_and_shot(repo, tmp_path):
    result = drive(repo, tmp_path, "honeycomb_zeeman_rashba", "--no-warm",
                   "--do", json.dumps({"do": "set_param", "entry": "c2", "name": "ne", "value": 50}),
                   "--do", json.dumps({"do": "add_term", "system": "s1", "kind": "onsite"}),
                   "--run", "c2", "--widget", "plotView", "--shot", "dos.png",
                   "--python", "print('terms', len(session.document.systems[0].hamiltonian.terms))")
    assert result.returncode == 0, result.stderr
    report = report_of(result)
    assert report["commands"][1] == {"do": "add_term", "result": "t3"}
    assert report["results"]["c2"]["arrays"]["dos"] == [50]
    assert report["jobs"][0]["status"] == "done" and report["widget"] == "plotView"
    assert "terms 3" in result.stdout
    assert (tmp_path / "dos.png").read_bytes().startswith(PNG_MAGIC)


def test_bad_command_fails_cleanly(repo, tmp_path):
    result = drive(repo, tmp_path, "honeycomb_zeeman_rashba", "--no-warm",
                   "--do", json.dumps({"do": "set_param", "entry": "t9", "name": "c", "value": 1}))
    assert result.returncode != 0 and "no entry 't9'" in result.stderr


def test_sculpt_by_command_and_see_it(repo, tmp_path):
    """Phase 2 acceptance, first half: load a preset, remove atoms by
    command, and the screenshot shows the sculpted geometry."""
    result = drive(repo, tmp_path, "honeycomb_zeeman_rashba", "--no-warm",
                   "--do", json.dumps({"do": "select_sites", "box": [0.9, -2.0, 2.1, 2.0]}),
                   "--do", json.dumps({"do": "remove_selected"}),
                   "--do", json.dumps({"do": "add_geometry_op", "system": "s1",
                                       "kind": "remove_atoms",
                                       "params": {"positions": [[-2.0, 0.0, 0.0]]}}),
                   "--widget", "structureView", "--shot", "sculpted.png")
    assert result.returncode == 0, result.stderr
    report = report_of(result)
    assert [c["result"] for c in report["commands"]] == [2, "op2", "op3"]
    assert report["document"][0]["ops"] == ["op1:supercell", "op2:remove_atoms", "op3:remove_atoms"]
    assert report["builds"]["s1"]["sites"] == 5 and report["build_errors"] == {}
    assert report["selected"] == "op2" and report["modified"]      # remove_selected selects its op
    assert (tmp_path / "sculpted.png").read_bytes().startswith(PNG_MAGIC)


def test_kill_and_recover(repo, tmp_path):
    """Phase 2 acceptance, second half: a session killed without closing
    leaves its autosave; the next start recovers the document."""
    env = dict(os.environ, GUIQULA_DATA_DIR=str(tmp_path / "data"))
    autosaves = tmp_path / "data" / "autosave"
    victim = subprocess.Popen(
        [sys.executable, str(repo / "tools" / "drive.py"), "honeycomb_zeeman_rashba", "--no-warm",
         "--do", json.dumps({"do": "select", "entry": "t2"}),
         "--do", json.dumps({"do": "workspace", "name": "hamiltonian"}),
         "--do", json.dumps({"do": "rename", "entry": "s1", "name": "before the crash"}),
         "--do", json.dumps({"do": "add_geometry_op", "system": "s1", "kind": "remove_atoms",
                             "params": {"positions": [[1.0, 0.0, 0.0]]}}),
         "--hold", "300"], cwd=tmp_path, env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)

    def saved():
        for path in autosaves.glob("*.json"):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if data["document"]["systems"][0]["name"] == "before the crash" and \
                    len(data["document"]["systems"][0]["geometry"]["ops"]) == 2:
                return path
        return None
    try:
        deadline = time.monotonic() + 240
        while saved() is None:
            assert victim.poll() is None, "the driver ended before autosaving"
            assert time.monotonic() < deadline, "no autosave appeared"
            time.sleep(0.2)
    finally:
        victim.kill()                              # SIGKILL: no clean close, no atexit
        victim.wait(30)
    left = saved()
    assert left is not None and json.loads(left.read_text())["modified"]

    result = drive(repo, tmp_path, "--recover", "--no-warm", "--widget", "structureView",
                   "--shot", "recovered.png", env=env)
    assert result.returncode == 0, result.stderr
    report = report_of(result)
    assert report["recovered"]["path"] == str(left)
    assert report["document"][0]["name"] == "before the crash"
    assert report["document"][0]["ops"] == ["op1:supercell", "op2:remove_atoms"]
    assert report["builds"]["s1"]["sites"] == 7 and report["modified"]
    assert report["selected"] == "t2" and report["workspace"] == "hamiltonian"   # the view too
    assert (tmp_path / "recovered.png").read_bytes().startswith(PNG_MAGIC)
    assert list(autosaves.glob("*.json")) == []    # the recovering session closed cleanly
