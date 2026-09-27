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
    from guiqula.session import Session, trusted_on_open
    document = project.load(args.document)
    calcs = args.calc or [c.id for c in document.calculations]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    with Session(document, interactive=False, timeout=args.timeout) as session:
        session.trusted = args.trust or trusted_on_open(args.document, document)
        jobs = {c: session.run_calculation(c, cores=args.cores) for c in calcs}
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
            print(json.dumps(report))
    return 1 if failed else 0


def _script(argv):
    parser = argparse.ArgumentParser(prog="guiqula script",
                                     description="Print the pyqula script of a calculation.")
    parser.add_argument("document")
    parser.add_argument("--calc", required=True, metavar="ID")
    parser.add_argument("--trust", action="store_true",
                        help="write the document's Python nodes (else skipped, as the engine "
                             "skips them in a document that is not trusted)")
    args = parser.parse_args(argv)
    from guiqula.io import project
    from guiqula.io.script import export_script
    from guiqula.session import trusted_on_open
    document = project.load(args.document)
    trusted = args.trust or trusted_on_open(args.document, document)
    sys.stdout.write(export_script(document, args.calc, trusted=trusted))
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
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(True))
    with Session(args.document, warm=not args.no_warm) as session:
        if args.trust:
            session.act("trust")
        api = RemoteAPI(session)
        with Server(api, port=args.port) as server:
            server.publish(window=False, document=str(session.path) if session.path else None)
            session.build_all()
            print(json.dumps({"port": server.port, "pid": os.getpid(),
                              "connection_file": str(server.file)}), flush=True)
            try:
                while not stop:
                    session.poll(0.02)
                    server.poll(0.02)
            except KeyboardInterrupt:
                pass
        api.close()
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
    if argv and argv[0] in commands:
        return commands[argv[0]](argv[1:])
    return _window(argv)


if __name__ == "__main__":
    sys.exit(main())
