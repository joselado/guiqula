#!/usr/bin/env python
"""Drive guiqula headlessly: build the window offscreen, act on it, take
screenshots (PLAN.md 3.6). This is how Claude "clicks" during development.

Phase-0 stub: builds the window, lists widgets, runs a Python snippet
against it and saves screenshots. Loading a document and running
calculations (``drive.py preset.guiqula --run bands``) need the Document and
the command API, which arrive in phase 1; those arguments are rejected.

Examples:
    python tools/drive.py --shot out.png
    python tools/drive.py --widget placeholder --shot label.png
    python tools/drive.py --list-widgets
    python tools/drive.py --python "print(window.windowTitle())"
"""
import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from guiqula import env  # noqa: E402  (after the sys.path insert)

NOT_YET = 2   # exit code for arguments that need a later phase


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("document", nargs="?",
                        help="project or preset to load (phase 1)")
    parser.add_argument("--run", metavar="CALC", action="append", default=[],
                        help="calculation to run (phase 1)")
    parser.add_argument("--size", default="1200x800", metavar="WxH",
                        help="window size (default 1200x800)")
    parser.add_argument("--python", metavar="CODE", action="append", default=[],
                        help="execute CODE with `app` and `window` in scope; repeatable")
    parser.add_argument("--list-widgets", action="store_true",
                        help="print the tree of widgets that have an objectName")
    parser.add_argument("--widget", metavar="NAME",
                        help="objectName of the widget --shot captures (default: whole window)")
    parser.add_argument("--shot", metavar="PNG", help="save a screenshot")
    return parser.parse_args(argv)


def widget_tree(widget, depth=0):
    lines = []
    name = widget.objectName()
    if name:
        lines.append("  " * depth + f"{name} ({type(widget).__name__})")
        depth += 1
    from PySide6.QtWidgets import QWidget
    for child in widget.findChildren(QWidget, options=_direct_children()):
        lines.extend(widget_tree(child, depth))
    return lines


def _direct_children():
    from PySide6.QtCore import Qt
    return Qt.FindChildOption.FindDirectChildrenOnly


def main(argv=None):
    args = parse_args(argv)
    if args.document or args.run:
        print("drive.py: loading documents and --run need the Document and the "
              "command API, which arrive in phase 1", file=sys.stderr)
        return NOT_YET
    width, height = (int(v) for v in args.size.lower().split("x"))

    env.configure_qt(offscreen=True)
    from PySide6.QtWidgets import QWidget
    from guiqula.ui.app import build_main_window, create_application

    app = create_application()
    window = build_main_window()
    window.resize(width, height)
    window.show()
    app.processEvents()

    for code in args.python:
        exec(code, {"app": app, "window": window})
        app.processEvents()

    if args.list_widgets:
        print("\n".join(widget_tree(window)))

    report = {"window": [window.width(), window.height()]}
    if args.shot:
        target = window
        if args.widget:
            target = window.findChild(QWidget, args.widget)
            if target is None:
                print(f"drive.py: no widget named {args.widget!r}; names:\n"
                      + "\n".join(widget_tree(window)), file=sys.stderr)
                return 1
        path = Path(args.shot).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not target.grab().save(str(path)):
            print(f"drive.py: could not write {path}", file=sys.stderr)
            return 1
        report["shot"] = str(path)
        report["widget"] = args.widget or window.objectName()
    print(json.dumps(report))
    window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
