#!/usr/bin/env python
"""Drive guiqula headlessly: open the window offscreen, load a document,
apply commands, run calculations through the Run button, take screenshots
(PLAN.md 3.6). This is how Claude "clicks" during development; it goes
through the same Session and command API as the window and the tests.

Examples:
    python tools/drive.py honeycomb_zeeman_rashba --run c1 --shot bands.png
    python tools/drive.py project.guiqula --do '{"do": "set_param", "entry": "t2",
        "name": "c", "value": 0.3}' --run c1 --widget plotView --shot plot.png
    python tools/drive.py --list-widgets
    python tools/drive.py preset --python "print(session.document.to_json())"

A --do object names a mutation or an action with "do" and gives its
arguments as the other keys; --commands FILE holds a JSON list of them.
The report printed last is JSON: the document outline, job and result
summaries, the end of the log, and the screenshot path.
"""
import argparse
import json
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from guiqula import env  # noqa: E402  (after the sys.path insert)


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     epilog=__doc__.split("\n\n", 1)[1],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("document", nargs="?", help="project file or preset name to open")
    parser.add_argument("--do", action="append", default=[], metavar="JSON",
                        help='command, e.g. \'{"do": "add_term", "system": "s1", "kind": "haldane"}\'')
    parser.add_argument("--commands", metavar="FILE", help="JSON list of --do objects")
    parser.add_argument("--run", action="append", default=[], metavar="CALC",
                        help="calculation id to run with the Run button (repeatable)")
    parser.add_argument("--cores", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=600, help="seconds to wait for jobs")
    parser.add_argument("--no-warm", action="store_true", help="skip the numba warm-up")
    parser.add_argument("--no-session", action="store_true",
                        help="only the window, without workers or a document")
    parser.add_argument("--size", default="1200x800", metavar="WxH", help="window size")
    parser.add_argument("--python", action="append", default=[], metavar="CODE",
                        help="execute CODE with app, window, session in scope; repeatable")
    parser.add_argument("--list-widgets", action="store_true",
                        help="print the tree of widgets that have an objectName")
    parser.add_argument("--widget", metavar="NAME", help="objectName of the widget --shot captures")
    parser.add_argument("--shot", metavar="PNG", help="save a screenshot")
    return parser.parse_args(argv)


def widget_tree(widget, depth=0):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget
    lines = []
    name = widget.objectName()
    if name and not name.startswith("qt_"):
        lines.append("  " * depth + f"{name} ({type(widget).__name__})")
        depth += 1
    for child in widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        lines.extend(widget_tree(child, depth))
    return lines


def settle(app, window, session, timeout):
    """Process events until no job is pending (builds and runs), including
    the build the window schedules shortly after a document change."""
    deadline = time.monotonic() + timeout
    while True:
        app.processEvents()
        pending = session is not None and (
            window.build_timer.isActive() or not all(j.done for j in session.jobs.jobs.values()))
        if not pending:
            app.processEvents()
            return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)


def outline(document):
    out = []
    for system in document.systems:
        out.append({"system": system.id, "lattice": system.geometry.base.kind,
                    "ops": [f"{o.id}:{o.kind}" + ("" if o.enabled else "(off)")
                            for o in system.geometry.ops],
                    "terms": [f"{t.id}:{t.kind}" + ("" if t.enabled else "(off)")
                              for t in system.hamiltonian.terms] if system.hamiltonian else []})
    out.append({"calculations": [f"{c.id}:{c.kind}@{c.system}" for c in document.calculations]})
    return out


def main(argv=None):
    args = parse_args(argv)
    width, height = (int(v) for v in args.size.lower().split("x"))
    commands = [json.loads(text) for text in args.do]
    if args.commands:
        commands += json.loads(Path(args.commands).read_text())

    env.configure_qt(offscreen=True)
    from PySide6.QtWidgets import QWidget
    from guiqula.ui.app import build_main_window, create_application

    app = create_application()
    window = build_main_window()
    window.resize(width, height)
    window.show()
    app.processEvents()
    session = None
    report = {"window": [width, height]}
    status = 0
    try:
        if not args.no_session:
            session = window.start_session(args.document, warm=not args.no_warm)
        elif args.document or commands or args.run:
            print("drive.py: --no-session cannot load documents or run", file=sys.stderr)
            return 2
        for command in commands:
            command = dict(command)
            name = command.pop("do")
            value = session.run(name, **command)
            report.setdefault("commands", []).append({"do": name, "result": value})
            app.processEvents()
        for calc in args.run:
            window.select_calculation(calc)
            window.run_button.click()
            job = session.calc_jobs[calc]
            deadline = time.monotonic() + args.timeout
            while not job.done and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            if job.status != "done":
                status = 1
        settle(app, window, session, args.timeout)
        for code in args.python:
            exec(code, {"app": app, "window": window, "session": session})
            app.processEvents()
        if args.list_widgets:
            print("\n".join(widget_tree(window)))
        if session is not None:
            report["document"] = outline(session.document)
            report["jobs"] = [j.summary() for j in session.jobs.jobs.values() if j.kind != "build"]
            report["results"] = {c: r.summary() for c, r in session.results.items()}
            report["stale"] = [c for c in session.results if session.is_stale(c)]
            report["log"] = window.log.toPlainText().splitlines()[-20:]
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
        print(json.dumps(report, default=str))
        return status
    finally:
        window.close()
        app.processEvents()


if __name__ == "__main__":
    sys.exit(main())
