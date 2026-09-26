"""tools/drive.py, the headless driver (PLAN.md 3.6)."""
import json
import subprocess
import sys

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def drive(repo, cwd, *args):
    return subprocess.run([sys.executable, str(repo / "tools" / "drive.py"), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=120)


def test_window_screenshot(repo, tmp_path):
    result = drive(repo, tmp_path, "--size", "800x600", "--shot", "win.png")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["window"] == [800, 600]
    assert report["widget"] == "MainWindow"
    assert (tmp_path / "win.png").read_bytes().startswith(PNG_MAGIC)


def test_widget_screenshot_and_snippet(repo, tmp_path):
    result = drive(repo, tmp_path, "--python", "window.setWindowTitle('changed')",
                   "--python", "print('title', window.windowTitle())",
                   "--widget", "placeholder", "--shot", "label.png")
    assert result.returncode == 0, result.stderr
    assert "title changed" in result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["widget"] == "placeholder"
    assert (tmp_path / "label.png").read_bytes().startswith(PNG_MAGIC)


def test_list_widgets(repo, tmp_path):
    result = drive(repo, tmp_path, "--list-widgets")
    assert result.returncode == 0, result.stderr
    assert "MainWindow (MainWindow)" in result.stdout
    assert "  placeholder (QLabel)" in result.stdout


def test_unknown_widget(repo, tmp_path):
    result = drive(repo, tmp_path, "--widget", "nope", "--shot", "x.png")
    assert result.returncode == 1
    assert "no widget named 'nope'" in result.stderr
    assert not (tmp_path / "x.png").exists()


def test_document_needs_phase_1(repo, tmp_path):
    for args in (["preset.guiqula"], ["--run", "bands"]):
        result = drive(repo, tmp_path, *args)
        assert result.returncode == 2
        assert "phase 1" in result.stderr
