# PyInstaller spec of the guiqula application folder (PLAN.md section 6, phase 6).
#
#   pip install pyinstaller   (in an environment with guiqula's dependencies)
#   pyinstaller packaging/pyinstaller/guiqula.spec --noconfirm
#
# gives dist/guiqula/ with two executables sharing one _internal folder:
# "guiqula" (the window; no console on Windows and macOS) and "guiqula-cli"
# (a console program: guiqula-cli run ..., serve, mcp, script). On macOS it
# also gives dist/guiqula.app. Run it from the repository's root.
#
# pyqula is collected as source files (module_collection_mode "py") at the top
# of _internal/: guiqula's vendoring shim finds it there ("bundled"), numba's
# cache needs the sources of the functions it compiles, and the in-app help
# reads pyqula's docstrings from them. guiqula's data (presets, guides,
# icons) and pyqula's user guide go where the package looks for them.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
VENDOR = ROOT / "vendor"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(VENDOR))

pyqula_modules = sorted(
    "pyqula." + ".".join(p.relative_to(VENDOR / "pyqula").with_suffix("").parts)
    for p in (VENDOR / "pyqula").rglob("*.py")
    if "__pycache__" not in p.parts and p.parent.joinpath("__init__.py").is_file()
)
pyqula_modules = ["pyqula"] + [m.removesuffix(".__init__") for m in pyqula_modules
                               if m != "pyqula.__init__"]

datas = collect_data_files("guiqula", excludes=["**/__pycache__"])
datas += collect_data_files("pyqula", includes=["datasets/*"])
datas += [(str(VENDOR / "pyqula_user_guide.md"), "guiqula/_vendor")]

hiddenimports = (collect_submodules("guiqula") + pyqula_modules
                 + ["multiprocess", "dill", "threadpoolctl"])

ICONS = ROOT / "src" / "guiqula" / "resources"
windowed = sys.platform in ("win32", "darwin")

a = Analysis(
    [str(ROOT / "packaging" / "pyinstaller" / "launcher.py")],
    pathex=[str(ROOT / "src"), str(VENDOR)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PyQt5", "PyQt6", "tkinter", "IPython", "pytest"],
    module_collection_mode={"pyqula": "py"},
    noarchive=False,
)
pyz = PYZ(a.pure)

gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="guiqula",
          console=not windowed, icon=str(ICONS / ("guiqula.icns" if sys.platform == "darwin"
                                                  else "guiqula.ico")))
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="guiqula-cli", console=True,
          icon=str(ICONS / "guiqula.ico"))
coll = COLLECT(gui, cli, a.binaries, a.datas, name="guiqula")

if sys.platform == "darwin":
    import guiqula
    app = BUNDLE(coll, name="guiqula.app", icon=str(ICONS / "guiqula.icns"),
                 bundle_identifier="org.pyqula.guiqula",
                 info_plist={"CFBundleShortVersionString": guiqula.__version__,
                             "NSHighResolutionCapable": True,
                             "CFBundleDocumentTypes": [{
                                 "CFBundleTypeName": "guiqula project",
                                 "CFBundleTypeExtensions": ["guiqula"],
                                 "CFBundleTypeRole": "Editor"}]})
