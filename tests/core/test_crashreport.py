"""Crash reports (PLAN.md 13.14)."""
import json

from guiqula.io import crashreport


def test_write_and_prune(tmp_path, monkeypatch):
    monkeypatch.setenv("GUIQULA_DATA_DIR", str(tmp_path))
    folder = crashreport.write("Traceback: boom", '{"version": 1}', "log line",
                               extra={"where": "test"})
    assert folder.parent == tmp_path / "crash-reports"
    assert (folder / "traceback.txt").read_text() == "Traceback: boom"
    assert (folder / "document.json").read_text() == '{"version": 1}'
    info = json.loads((folder / "report.json").read_text())
    assert info["where"] == "test" and info["versions"]["pyqula"].startswith("pyqula: ")
    assert "PySide6-Essentials" in info["versions"] or "PySide6" in info["versions"]
    for _ in range(crashreport.KEEP + 3):
        crashreport.write("again")
    assert len(list((tmp_path / "crash-reports").iterdir())) == crashreport.KEEP
