"""tools/drive.py, the headless driver (PLAN.md 3.6)."""
import json
import subprocess
import sys

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def drive(repo, cwd, *args, timeout=600):
    return subprocess.run([sys.executable, str(repo / "tools" / "drive.py"), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=timeout)


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
    for name in ("MainWindow (MainWindow)", "documentTree (DocumentTree)", "runButton (QPushButton)",
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
