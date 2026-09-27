"""Desktop integration (PLAN.md section 6): ``guiqula desktop`` puts guiqula
in the desktop's application menu with its icon, for the interpreter it
runs with (a venv, pipx or conda environment); ``--remove`` takes it out.

- Linux (freedesktop): a .desktop entry in $XDG_DATA_HOME/applications, the
  icon in the hicolor theme, and the MIME type of .guiqula files, so that a
  project opens with a double click;
- Windows: a Start menu shortcut (written by PowerShell's WScript.Shell),
  and .guiqula files associated with it (in the user's registry hive);
- macOS: ~/Applications/guiqula.app, a small bundle that starts the
  interpreter (files are opened from the program: a script bundle does not
  receive the Finder's open-document events).

Everything is written for the current user only; nothing needs
administrator rights. From a source checkout (nothing installed), the
entry also says where guiqula's sources are (PYTHONPATH on Linux and
macOS, the working directory on Windows). Qt-free.
"""
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import guiqula
from guiqula import env

RESOURCES = Path(__file__).resolve().parent / "resources"
NAME = "guiqula"
COMMENT = "Graphical workbench for the pyqula tight-binding library"
MIME = "application/x-guiqula"
PROG_ID = "guiqula.project"


def checkout_src():
    """The src/ directory guiqula runs from when it is not installed, else None."""
    package = Path(guiqula.__file__).resolve().parent
    if package.parent.name == "src" and (package.parents[1] / "pyproject.toml").is_file():
        return package.parent
    return None


def platform():
    return {"linux": "linux", "win32": "windows", "darwin": "macos"}.get(
        sys.platform, "linux" if os.name == "posix" else sys.platform)


# ---- Linux
def data_home():
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _exec_quote(argument):
    """An argument of a .desktop Exec key (the freedesktop quoting rules)."""
    if not any(c in argument for c in ' \t\n"\'\\><~|&;$*?#()`'):
        return argument
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in argument)
    return f'"{escaped}"'


def _command(python):
    """The interpreter and its arguments that start the window."""
    return [python, "-m", "guiqula"] if python else env.launcher()


def linux_files(python=None, home=None):
    """{path: text or bytes} of the Linux integration."""
    home = Path(home) if home is not None else data_home()
    src = checkout_src()
    command = " ".join(_exec_quote(str(a)) for a in _command(python)) + " %f"
    if src is not None:
        command = f"env {_exec_quote('PYTHONPATH=' + str(src))} {command}"
    entry = "\n".join([
        "[Desktop Entry]", "Type=Application", f"Name={NAME}",
        "GenericName=Tight-binding workbench", f"Comment={COMMENT}",
        f"Exec={command}", f"Icon={NAME}", "Terminal=false",
        "Categories=Science;Physics;Education;", f"MimeType={MIME};",
        f"StartupWMClass={NAME}", f"X-guiqula-Version={guiqula.__version__}", ""])
    mime = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">',
        f'  <mime-type type="{MIME}">', "    <comment>guiqula project</comment>",
        '    <glob pattern="*.guiqula"/>', f'    <icon name="{NAME}"/>', "  </mime-type>",
        "</mime-info>", ""])
    return {home / "applications" / f"{NAME}.desktop": entry,
            home / "icons" / "hicolor" / "scalable" / "apps" / f"{NAME}.svg":
                (RESOURCES / "guiqula.svg").read_bytes(),
            home / "icons" / "hicolor" / "256x256" / "apps" / f"{NAME}.png":
                (RESOURCES / "guiqula.png").read_bytes(),
            home / "mime" / "packages" / f"{NAME}.xml": mime}


def _refresh_linux(home):
    """Let the desktop see the changes (the tools may be missing: fine)."""
    for command in (["update-mime-database", str(home / "mime")],
                    ["update-desktop-database", str(home / "applications")],
                    ["gtk-update-icon-cache", "-q", "-t", str(home / "icons" / "hicolor")]):
        if shutil.which(command[0]):
            subprocess.run(command, capture_output=True, timeout=60)


# ---- Windows
def windows_python(python=None):
    """pythonw.exe next to the interpreter (no console window), if there is one."""
    python = Path(python or sys.executable)
    windowed = python.with_name("pythonw.exe")
    return windowed if windowed.name != python.name and windowed.exists() else python


def start_menu():
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / \
        "Microsoft" / "Windows" / "Start Menu" / "Programs"


def windows_shortcut_script(python, shortcut, icon, directory=None):
    """The PowerShell that writes the Start menu shortcut (directory: its
    working directory, the user's home by default; src/ from a checkout,
    where python -m guiqula then finds the package)."""
    def quoted(value):
        return "'" + str(value).replace("'", "''") + "'"
    return "; ".join([
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({quoted(shortcut)})",
        f"$s.TargetPath = {quoted(python)}", "$s.Arguments = '-m guiqula'",
        f"$s.IconLocation = {quoted(icon)}", f"$s.Description = {quoted(COMMENT)}",
        f"$s.WorkingDirectory = {quoted(directory or Path.home())}", "$s.Save()"])


def windows_registry(python, icon):
    """{key under HKEY_CURRENT_USER: {value name: data}} of the .guiqula
    file association ("" is a key's default value)."""
    base = r"Software\Classes"
    command = f'"{python}" -m guiqula "%1"'
    return {rf"{base}\.guiqula": {"": PROG_ID},
            rf"{base}\{PROG_ID}": {"": "guiqula project"},
            rf"{base}\{PROG_ID}\DefaultIcon": {"": str(icon)},
            rf"{base}\{PROG_ID}\shell\open\command": {"": command}}


def _install_windows(python):
    import winreg
    python = windows_python(python)
    icon = RESOURCES / "guiqula.ico"
    shortcut = start_menu() / f"{NAME}.lnk"
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                    windows_shortcut_script(python, shortcut, icon, checkout_src())],
                   check=True,
                   capture_output=True, timeout=120)
    for key, values in windows_registry(python, icon).items():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
            for name, data in values.items():
                winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, data)
    return [str(shortcut)] + [f"HKEY_CURRENT_USER\\{key}" for key in windows_registry(python, icon)]


def _remove_windows():
    import winreg
    removed = []
    shortcut = start_menu() / f"{NAME}.lnk"
    if shortcut.exists():
        shortcut.unlink()
        removed.append(str(shortcut))
    for key in sorted(windows_registry("", ""), key=len, reverse=True):   # children first
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
            removed.append(f"HKEY_CURRENT_USER\\{key}")
        except OSError:
            pass
    return removed


# ---- macOS
def mac_bundle_files(python=None, applications=None):
    """{path: text or bytes} of ~/Applications/guiqula.app (the launcher is
    made executable when written)."""
    applications = Path(applications) if applications is not None else \
        Path.home() / "Applications"
    contents = applications / f"{NAME}.app" / "Contents"
    plist = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">', "<dict>",
        "  <key>CFBundleName</key><string>guiqula</string>",
        "  <key>CFBundleDisplayName</key><string>guiqula</string>",
        "  <key>CFBundleIdentifier</key><string>org.pyqula.guiqula</string>",
        f"  <key>CFBundleShortVersionString</key><string>{guiqula.__version__}</string>",
        "  <key>CFBundlePackageType</key><string>APPL</string>",
        "  <key>CFBundleExecutable</key><string>guiqula</string>",
        "  <key>CFBundleIconFile</key><string>guiqula.icns</string>",
        "  <key>NSHighResolutionCapable</key><true/>",
        "</dict>", "</plist>", ""])
    src = checkout_src()
    launcher = "#!/bin/sh\n" + (f"export PYTHONPATH={shlex.quote(str(src))}\n" if src else "") + \
        f"exec {' '.join(shlex.quote(str(a)) for a in _command(python))} \"$@\"\n"
    return {contents / "Info.plist": plist, contents / "MacOS" / NAME: launcher,
            contents / "Resources" / f"{NAME}.icns": (RESOURCES / "guiqula.icns").read_bytes()}


# ---- the command
def _write(files):
    written = []
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return written


def install(python=None):
    """Put guiqula in the desktop's menu; returns what was written."""
    system = platform()
    if system == "windows":
        return _install_windows(python)
    if system == "macos":
        files = mac_bundle_files(python)
        written = _write(files)
        launcher = next(p for p in files if p.parent.name == "MacOS")
        launcher.chmod(0o755)
        return written
    files = linux_files(python)
    written = _write(files)
    _refresh_linux(data_home())
    return written


def remove():
    """Take guiqula out of the desktop's menu; returns what was removed."""
    system = platform()
    if system == "windows":
        return _remove_windows()
    if system == "macos":
        bundle = Path.home() / "Applications" / f"{NAME}.app"
        if bundle.exists():
            shutil.rmtree(bundle)
            return [str(bundle)]
        return []
    removed = []
    for path in linux_files():
        if path.exists():
            path.unlink()
            removed.append(str(path))
    _refresh_linux(data_home())
    return removed
