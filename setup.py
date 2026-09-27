"""Package list for setuptools; everything else is in pyproject.toml.

vendor/pyqula is packaged as guiqula._vendor.pyqula (the mapping is in
pyproject.toml). Its subpackages are listed here rather than by hand so a
refresh of vendor/ by tools/update_vendor.sh needs no packaging change.
pyqula's user guide, which the in-app help shows (decision 13.13), is copied
next to it as guiqula/_vendor/pyqula_user_guide.md: vendor/ stays an exact
copy of upstream, and guiqula/_vendor is not a package.
"""
from pathlib import Path

from setuptools import find_packages, setup
from setuptools.command.build_py import build_py

GUIDE = Path(__file__).resolve().parent / "vendor" / "pyqula_user_guide.md"


class BuildPy(build_py):
    def run(self):
        super().run()
        if not GUIDE.is_file():
            raise FileNotFoundError(f"{GUIDE} is missing: refresh vendor/ with "
                                    f"tools/update_vendor.sh")
        target = Path(self.build_lib) / "guiqula" / "_vendor" / GUIDE.name
        target.parent.mkdir(parents=True, exist_ok=True)
        self.copy_file(str(GUIDE), str(target))


own = find_packages("src")
vendored = ["guiqula._vendor." + name
            for name in find_packages("vendor", include=["pyqula", "pyqula.*"])]
setup(packages=own + vendored, cmdclass={"build_py": BuildPy})
