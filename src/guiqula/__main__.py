"""Command line entry point: ``guiqula`` and ``python -m guiqula``.

The Qt application is imported only when the window is requested, so the
headless runner planned for phase 1 (PLAN.md 13.3) never loads Qt.
"""
import argparse
import sys

import guiqula
from guiqula import env


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="guiqula", description="Graphical workbench for pyqula.")
    parser.add_argument("--version", action="version",
                        version=f"guiqula {guiqula.__version__}")
    parser.add_argument("--offscreen", action="store_true",
                        help="render without a display (Qt offscreen platform)")
    args = parser.parse_args(argv)
    env.configure_qt(offscreen=args.offscreen)
    from guiqula.ui.app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
