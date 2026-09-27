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


CODE = """
from guiqula.io import crashreport
from guiqula.session import Session
print(crashreport.write("Traceback: ValueError: gap \\u0394 < 0").name)
with Session(None, warm=False) as s:
    system = s.do("add_system")
    s.do("add_term", system=system, kind="python",
         params={"code": "# \\u0394: a staggered potential\\nh.add_sublattice_imbalance(0.1)\\n"})
    print(s.act("export_script", calculation=s.do("add_calculation", system=system,
                                                  kind="bands"), path="delta.py"))
"""


def test_text_files_are_utf8_whatever_the_locale(tmp_path, run_python):
    """Under a locale that cannot write a Greek letter (Windows' cp1252,
    here the C locale), the crash reporter itself and Export script failed
    with UnicodeEncodeError; they write UTF-8."""
    done = run_python(CODE, {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0",
                             "PYTHONCOERCECLOCALE": "0", "GUIQULA_DATA_DIR": str(tmp_path)})
    assert done.returncode == 0, done.stderr
    folder = tmp_path / "crash-reports" / done.stdout.split()[0]
    assert "Δ < 0" in (folder / "traceback.txt").read_text(encoding="utf-8")
    assert "# Δ: a staggered" in (tmp_path / "delta.py").read_text(encoding="utf-8")
