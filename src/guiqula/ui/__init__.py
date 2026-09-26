"""PySide6 user interface: main window, outliner, properties, viewport,
console, job panel (PLAN.md section 4). Widgets carry stable objectNames so
tests and tools/drive.py can find them.

The only package besides remote/ that may import Qt; it must never import
pyqula, jax or numba (PLAN.md 13.15; tests/ui/test_startup.py checks it).
"""
