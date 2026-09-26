"""Crash reports (PLAN.md 13.14): on an unexpected error, a folder with the
traceback, the log, the Document snapshot and the versions, so that a
student's bug report reproduces. Written to ``<user data dir>/crash-reports/``;
the newest KEEP reports are kept.

Qt-free and pyqula-free: versions are read from package metadata and from
guiqula.vendoring without importing anything heavy.
"""
import json
import os
import platform
import shutil
import sys
import time
from importlib import metadata
from pathlib import Path

import guiqula
from guiqula import env, vendoring

KEEP = 20


def reports_dir():
    return env.user_data_dir() / "crash-reports"


def versions():
    out = {"guiqula": guiqula.__version__, "python": sys.version.split()[0],
           "platform": platform.platform(), "pyqula": vendoring.describe()}
    for package in ("PySide6-Essentials", "PySide6", "numpy", "scipy", "matplotlib", "numba",
                    "jax", "pydantic"):
        try:
            out[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            pass
    return out


def write(traceback_text, document_json=None, log_text="", extra=None, directory=None):
    """Write a report; returns its folder."""
    base = Path(directory) if directory is not None else reports_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = base / f"{stamp}-{os.getpid()}"
    n = 1
    while folder.exists():
        n += 1
        folder = base / f"{stamp}-{os.getpid()}-{n}"
    folder.mkdir(parents=True)
    (folder / "traceback.txt").write_text(traceback_text)
    if document_json:
        (folder / "document.json").write_text(document_json)
    (folder / "log.txt").write_text(log_text or "")
    info = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "argv": sys.argv,
            "versions": versions(), **(extra or {})}
    (folder / "report.json").write_text(json.dumps(info, indent=2, default=str))
    prune(base)
    return folder


def prune(base, keep=KEEP):
    folders = sorted((p for p in Path(base).iterdir() if p.is_dir()),
                     key=lambda p: p.stat().st_mtime)
    for old in folders[:-keep] if keep else folders:
        shutil.rmtree(old, ignore_errors=True)
