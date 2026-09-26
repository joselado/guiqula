"""Package list for setuptools; everything else is in pyproject.toml.

vendor/pyqula is packaged as guiqula._vendor.pyqula (the mapping is in
pyproject.toml). Its subpackages are listed here rather than by hand so a
refresh of vendor/ by tools/update_vendor.sh needs no packaging change.
"""
from setuptools import find_packages, setup

own = find_packages("src")
vendored = ["guiqula._vendor." + name
            for name in find_packages("vendor", include=["pyqula", "pyqula.*"])]
setup(packages=own + vendored)
