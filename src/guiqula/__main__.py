"""Command line entry point: ``guiqula`` and ``python -m guiqula``.

    guiqula [--offscreen] [--remote] [document]   open the window
    guiqula run DOCUMENT [--calc ID ...]  run calculations headlessly (PLAN.md 13.3)
    guiqula script DOCUMENT --calc ID     print the pyqula script of a calculation
    guiqula serve [DOCUMENT]              a session without a window, driven through
                                          the remote API (PLAN.md 3.7)
    guiqula mcp                           the MCP server of the Claude add-on (PLAN.md 3.7)
    guiqula desktop [--remove]            a menu entry and an icon on the desktop

A file holding Python nodes is not trusted (PLAN.md 13.7): its nodes are
skipped unless --trust is given, as in the window until it is trusted.
A document, calculation or file that cannot be used is reported in one
line on stderr, with exit status 2 (as argparse does for its own errors).

The Qt application is imported only when the window is requested, so the
headless commands never load Qt.
"""
import argparse
import json
import os
import signal
import sys
from pathlib import Path

import guiqula
from guiqula import env


def _window(argv):
    parser = argparse.ArgumentParser(prog="guiqula", description="Graphical workbench for pyqula.")
    parser.add_argument("--version", action="version", version=f"guiqula {guiqula.__version__}")
    parser.add_argument("--offscreen", action="store_true",
                        help="render without a display (Qt offscreen platform)")
    parser.add_argument("--remote", action="store_true",
                        help="let other programs drive the window through a localhost socket "
                             "for this run (the Claude add-on: guiqula mcp)")
    parser.add_argument("document", nargs="?", help="project file or preset name to open")
    args = parser.parse_args(argv)
    env.configure_qt(offscreen=args.offscreen)
    from guiqula.ui.app import run
    return run(document=args.document, remote=args.remote)


def _run(argv):
    parser = argparse.ArgumentParser(prog="guiqula run",
                                     description="Run calculations of a document without a window.")
    parser.add_argument("document", help="project file or preset name")
    parser.add_argument("--calc", action="append", default=[], metavar="ID",
                        help="calculation to run (repeatable; default: all)")
    parser.add_argument("--out", default=".", help="directory for <calc>.npz and <calc>.json")
    parser.add_argument("--cores", type=int, default=1, help="processes for pyqula's own pool")
    parser.add_argument("--timeout", type=float, default=None, help="seconds per calculation")
    parser.add_argument("--script", action="store_true", help="also write <calc>.py")
    parser.add_argument("--trust", action="store_true", help="run the document's Python nodes")
    args = parser.parse_args(argv)
    from guiqula.io import project, results
    from guiqula.registry import pipeline
    from guiqula.session import Session
    document = project.load(args.document)
    calcs = args.calc or [c.id for c in document.calculations]
    _check_calculations(document, calcs)    # an unknown id, before anything runs
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    # opened by path: the results a project file keeps are there for its from_result Fields
    with Session(args.document, interactive=False, timeout=args.timeout) as session:
        if args.trust:
            session.trusted = True
        for wave in _waves(document, calcs, pipeline):
            jobs = {c: session.run_calculation(c, cores=args.cores) for c in wave}
            for calc, job in jobs.items():
                session.jobs.wait(job)
                report = {"calculation": calc, "status": job.status}
                if job.status == "done":
                    report["files"] = [str(p) for p in results.save(job.value, out / calc)]
                    report.update(job.value.summary())
                    if args.script:
                        path = out / f"{calc}.py"
                        session.act("export_script", calculation=calc, path=str(path))
                        report["files"].append(str(path))
                else:
                    failed += 1
                    report["error"] = job.error
                print(json.dumps(report), flush=True)
    return 1 if failed else 0


def _check_calculations(document, calcs):
    from guiqula.core.document import DocumentError
    known = [c.id for c in document.calculations]
    for calc in calcs:
        if calc not in known:
            raise DocumentError(f"no calculation {calc!r} (calculations: "
                                f"{', '.join(known) or 'none'})")


def _waves(document, calcs, pipeline):
    """The calculations in groups that run one after the other: one whose
    system reads the result of another being run (a from_result Field)
    comes after it, as the window's user would run them."""
    reads = {c: set(pipeline.result_references(document, document.calculation(c).system))
             for c in calcs}
    waves, left = [], list(calcs)
    while left:
        wave = [c for c in left if not (reads[c] - {c}) & set(left)] or list(left)   # a cycle
        waves.append(wave)
        left = [c for c in left if c not in wave]
    return waves


def _script(argv):
    parser = argparse.ArgumentParser(prog="guiqula script",
                                     description="Print the pyqula script of a calculation.")
    parser.add_argument("document")
    parser.add_argument("--calc", required=True, metavar="ID")
    parser.add_argument("--trust", action="store_true",
                        help="write the document's Python nodes (else skipped, as the engine "
                             "skips them in a document that is not trusted)")
    args = parser.parse_args(argv)
    from guiqula.session import Session
    # opened by path, as guiqula run does: a from_result Field reads the result the
    # file keeps, and the entries pyqula rejected in the calculation's result (when it
    # is current) are written as comments (its batch worker starts and stops unused)
    with Session(args.document, interactive=False, warm=False) as session:
        if args.trust:
            session.trusted = True
        _check_calculations(session.document, [args.calc])
        sys.stdout.write(session.act("export_script", calculation=args.calc))
    return 0


def _serve(argv):
    parser = argparse.ArgumentParser(
        prog="guiqula serve", description="A session without a window, driven through the "
                                          "remote API (a client, or guiqula mcp, finds it by "
                                          "its connection file). Stops on Ctrl+C or SIGTERM.")
    parser.add_argument("document", nargs="?", help="project file or preset name")
    parser.add_argument("--port", type=int, default=0, help="port (default: any free one)")
    parser.add_argument("--trust", action="store_true", help="run the document's Python nodes")
    parser.add_argument("--no-warm", action="store_true", help="skip the numba warm-up")
    args = parser.parse_args(argv)
    from guiqula.remote.api import RemoteAPI
    from guiqula.remote.server import Server
    from guiqula.session import Session
    # SIGTERM stops it as Ctrl+C does, wherever it is (a flag read by the loop waited
    # for whatever the loop was busy with); the connection file is deleted on the way out
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        with Session(args.document, warm=not args.no_warm) as session:
            if args.trust:
                session.act("trust")
            api = RemoteAPI(session)
            try:
                with Server(api, port=args.port) as server:
                    server.publish(window=False,
                                   document=str(session.path) if session.path else None)
                    session.build_all()
                    print(json.dumps({"port": server.port, "pid": os.getpid(),
                                      "connection_file": str(server.file)}), flush=True)
                    while True:
                        session.poll(0.02)
                        server.poll(0.02)
            finally:
                api.close()
    except KeyboardInterrupt:
        pass
    return 0


def _desktop(argv):
    parser = argparse.ArgumentParser(
        prog="guiqula desktop", description="Put guiqula in the desktop's application menu, "
                                            "with its icon and the .guiqula file type, for "
                                            "this interpreter (the current user only).")
    parser.add_argument("--remove", action="store_true", help="take it out again")
    args = parser.parse_args(argv)
    from guiqula import desktop
    done = desktop.remove() if args.remove else desktop.install()
    for path in done:
        print(("removed " if args.remove else "wrote ") + path)
    if not done:
        print("nothing to remove" if args.remove else "nothing written")
    return 0


def _mcp(argv):
    from guiqula.remote.mcp import main as mcp_main
    return mcp_main(argv)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"run": _run, "script": _script, "serve": _serve, "mcp": _mcp,
                "desktop": _desktop}
    if argv and argv[0] in ("run", "script", "serve"):
        try:
            return commands[argv[0]](argv[1:])
        except (ValueError, OSError) as error:   # a document, a calculation, a file
            print(f"guiqula {argv[0]}: {error}", file=sys.stderr)
            return 2
    if argv and argv[0] in commands:
        return commands[argv[0]](argv[1:])
    return _window(argv)


if __name__ == "__main__":
    sys.exit(main())
