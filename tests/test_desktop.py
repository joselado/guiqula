"""guiqula desktop (desktop.py): the Linux entry written and removed in a
scratch $XDG_DATA_HOME, valid by the freedesktop tools when they are
installed; what Windows and macOS get, as written (not applied here)."""
import shutil
import subprocess
import sys

import pytest

from guiqula import desktop
from guiqula.__main__ import main


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setattr(desktop, "platform", lambda: "linux")
    return tmp_path / "share"


def test_linux_entry_icon_and_file_type(xdg, capsys):
    assert main(["desktop"]) == 0
    entry = (xdg / "applications" / "guiqula.desktop").read_text()
    assert "MimeType=application/x-guiqula;" in entry and "Icon=guiqula" in entry
    exec_line = next(line for line in entry.splitlines() if line.startswith("Exec="))
    assert exec_line.endswith(f"{desktop._exec_quote(sys.executable)} -m guiqula %f")
    src = desktop.checkout_src()
    assert src is not None                                           # tests run from a checkout
    assert desktop._exec_quote(f"PYTHONPATH={src}") in exec_line
    assert (xdg / "icons" / "hicolor" / "256x256" / "apps" / "guiqula.png").read_bytes()[:4] \
        == b"\x89PNG"
    assert "*.guiqula" in (xdg / "mime" / "packages" / "guiqula.xml").read_text()
    if shutil.which("desktop-file-validate"):
        check = subprocess.run(["desktop-file-validate", str(xdg / "applications" /
                                                             "guiqula.desktop")],
                               capture_output=True, text=True)
        assert check.returncode == 0 and "error" not in check.stdout, check.stdout
    assert "wrote" in capsys.readouterr().out
    assert main(["desktop", "--remove"]) == 0
    assert not (xdg / "applications" / "guiqula.desktop").exists()
    assert main(["desktop", "--remove"]) == 0
    assert "nothing to remove" in capsys.readouterr().out


def test_exec_quoting():
    assert desktop._exec_quote("/usr/bin/python3") == "/usr/bin/python3"
    assert desktop._exec_quote("/opt/my env/bin/python") == '"/opt/my env/bin/python"'
    assert desktop._exec_quote('/a "b"/$x') == '"/a \\"b\\"/\\$x"'


def test_windows_shortcut_and_file_association():
    script = desktop.windows_shortcut_script(r"C:\Python312\pythonw.exe",
                                             r"C:\Users\me\Start Menu\guiqula.lnk",
                                             r"C:\it's\guiqula.ico", r"C:\src")
    assert "CreateShortcut('C:\\Users\\me\\Start Menu\\guiqula.lnk')" in script
    assert "$s.IconLocation = 'C:\\it''s\\guiqula.ico'" in script      # PowerShell quoting
    assert "$s.WorkingDirectory = 'C:\\src'" in script and script.endswith("$s.Save()")
    keys = desktop.windows_registry(r"C:\Python312\pythonw.exe", r"C:\guiqula.ico")
    assert keys[r"Software\Classes\.guiqula"] == {"": "guiqula.project"}
    assert keys[r"Software\Classes\guiqula.project\shell\open\command"][""] == \
        '"C:\\Python312\\pythonw.exe" -m guiqula "%1"'


def test_mac_bundle(tmp_path):
    files = desktop.mac_bundle_files("/opt/py/bin/python3", tmp_path)
    contents = tmp_path / "guiqula.app" / "Contents"
    plist = files[contents / "Info.plist"]
    assert "<key>CFBundleExecutable</key><string>guiqula</string>" in plist
    launcher = files[contents / "MacOS" / "guiqula"]
    assert launcher.startswith("#!/bin/sh\n") and "exec /opt/py/bin/python3 -m guiqula" in launcher
    assert files[contents / "Resources" / "guiqula.icns"][:4] == b"icns"
