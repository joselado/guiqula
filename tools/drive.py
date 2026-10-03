#!/usr/bin/env python
"""Drive guiqula headlessly: open the window offscreen, load a document,
apply commands, run calculations through the Run button, take screenshots
(PLAN.md 3.6). This is how Claude "clicks" during development; it goes
through the same Session and command API as the window and the tests.

Examples:
    python tools/drive.py honeycomb_zeeman_rashba --run c1 --shot bands.png
    python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "select_sites", "box": [0.9, -2, 2.1, 2]}'
        --do '{"do": "remove_selected"}' --widget structureView --shot sculpted.png
    python tools/drive.py --recover --shot recovered.png
    python tools/drive.py project.guiqula --do '{"do": "set_param", "entry": "t2",
        "name": "c", "value": 0.3}' --run c1 --widget plot_c1 --shot plot.png
    python tools/drive.py --list-widgets
    python tools/drive.py preset --python "print(session.document.to_json())"

A --do object names a mutation or an action with "do" and gives its
arguments as the other keys; --commands FILE holds a JSON list of them.
Window actions work too: select, workspace, tool, select_sites,
region_from_selection, remove_selected, canvas_view (structure, hamiltonian,
field), preview (a term's Field on the structure), auto_rerun, theme
(system, light, dark), export_bundle (calculation, path: figure, data and
script in one folder), help (entry, or guide and anchor: the Help dock),
projection (auto, xy, 3d), renderer_3d (matplotlib, pyvista: the 3D drawing,
whose widgets are structureScene and plotScene_<calculation id>), view_3d (name:
front, back, right, left, top, bottom, perspective, orthographic, flip, all,
selected, reset; calculation: a result's scene instead of the canvas's),
plot_text (small, normal, large), ui_text (normal, large: the text of the
menus, panels and forms), log (enabled: the bottom area, Log and Console,
hidden by default), panel (name: a dock, helpDock or Help, ...; shown:
false hides it), reset_layout (the default arrangement of the panels),
add_menu (section: s1/geometry, s1/regions, s1/hamiltonian, s1/model,
calculations or systems, and search: an Add menu opened as its "+" does,
whose widget is paletteMenu_<family> or regionsMenu), run_stale (every
stale result), start (search: the start page's filter, whose widget is
startPage, shown while the document has no system; its cards are
startLattice_<kind>, startPreset_<name>, ...); the session's undo, redo
(with "steps") and history; lock and unlock are mutations. The driven window never reads or writes the settings file. Every
calculation's result has its own view, plot_<calculation id>. After each command the driver
waits for the rebuild of the geometry, so a selection sees the new sites.
The report printed last is JSON: the document outline, the builds, job and
result summaries, the selection, the canvas view, the tab shown and the
open result views, the end of the log, and the screenshot.
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
                        help="calculation id to run with the Run button (repeatable); a slow one "
                             "is confirmed in the cost bar (the report's cost_guard)")
    parser.add_argument("--cores", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=600, help="seconds to wait for jobs")
    parser.add_argument("--no-warm", action="store_true", help="skip the numba warm-up")
    parser.add_argument("--trust", action="store_true",
                        help="let the document's Python nodes run (a file with Python code "
                             "is not trusted otherwise; same as --do '{\"do\": \"trust\"}')")
    parser.add_argument("--no-session", action="store_true",
                        help="only the window, without workers or a document")
    parser.add_argument("--recover", action="store_true",
                        help="recover the newest unsaved work of a session that did not close "
                             "cleanly, before the commands")
    parser.add_argument("--hold", type=float, default=0.0, metavar="SECONDS",
                        help="keep the window running (autosave included) for this long "
                             "before the report")
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


def settle(app, window, session, timeout, builds_only=False):
    """Process events until no job is pending (builds and runs, or builds
    only), including the build the window schedules shortly after a
    document change."""
    deadline = time.monotonic() + timeout
    while True:
        app.processEvents()
        pending = session is not None and (
            window.build_timer.isActive() or not all(
                j.done for j in session.jobs.jobs.values() if j.kind == "build" or not builds_only))
        if not pending:
            app.processEvents()
            return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)


def outline(document):
    """Systems with their ops and terms (a classical system's model's too,
    and the model's kind), then the calculations."""
    from guiqula.core.document import terms_of
    out = []
    for system in document.systems:
        item = {"system": system.id, "name": system.name, "lattice": system.geometry.base.kind,
                "ops": [f"{o.id}:{o.kind}" + ("" if o.enabled else "(off)")
                        for o in system.geometry.ops],
                "terms": [f"{t.id}:{t.kind}" + ("" if t.enabled else "(off)")
                          for t in terms_of(system)]}
        if system.model is not None:
            item["model"] = system.model.kind
        out.append(item)
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
        elif args.document or commands or args.run or args.recover:
            print("drive.py: --no-session cannot load documents or run", file=sys.stderr)
            return 2
        if args.recover:
            report["recovered"] = session.act("recover")
        if args.trust:
            report["trusted"] = session.act("trust")
        settle(app, window, session, args.timeout, builds_only=True)
        for command in commands:
            command = dict(command)
            name = command.pop("do")
            value = session.run(name, **command)
            report.setdefault("commands", []).append({"do": name, "result": value})
            settle(app, window, session, args.timeout, builds_only=True)
        for calc in args.run:
            window.select_calculation(calc)
            window.run_button.click()
            if calc not in session.calc_jobs and window.cost_bar.isVisible():
                # the cost guard asks before a slow run: --run means run, so answer it
                from PySide6.QtWidgets import QPushButton
                window.cost_bar.findChild(QPushButton, "runAnywayButton").click()
                report.setdefault("cost_guard", []).append(calc)
            job = session.calc_jobs.get(calc)
            if job is None:
                print(f"drive.py: {calc} did not start (see the log in the report)",
                      file=sys.stderr)
                status = 1
                continue
            deadline = time.monotonic() + args.timeout
            while not job.done and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            if job.status != "done":
                status = 1
        settle(app, window, session, args.timeout)
        deadline = time.monotonic() + args.hold
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        for code in args.python:
            exec(code, {"app": app, "window": window, "session": session})
            app.processEvents()
        if args.list_widgets:
            print("\n".join(widget_tree(window)))
        if session is not None:
            report["document"] = outline(session.document)
            report["builds"] = {s: {k: b[k] for k in ("sites", "dimensionality", "mode", "dimension")}
                                for s, b in session.builds.items()}
            report["build_errors"] = dict(session.build_errors)
            report["selected"] = window.selected
            report["workspace"] = window.workspace
            report["canvas_view"] = window.canvas_view
            report["projection"] = window.structure.projection
            report["renderer_3d"] = window.structure.renderer_3d
            report["tab"] = window.current_tab()
            report["result_views"] = list(window.plots)
            report["selection"] = len(window.structure.selected())
            report["modified"] = session.modified
            report["undo"] = session.dispatcher.history()["undo"][:10]
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
