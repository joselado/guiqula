"""Command line entry point: ``guiqula`` and ``python -m guiqula``.

    guiqula [--offscreen] [document]      open the window
    guiqula run DOCUMENT [--calc ID ...]  run calculations headlessly (PLAN.md 13.3)
    guiqula script DOCUMENT --calc ID     print the pyqula script of a calculation

A file holding Python nodes is not trusted (PLAN.md 13.7): its nodes are
skipped unless --trust is given, as in the window until it is trusted.

The Qt application is imported only when the window is requested, so the
headless commands never load Qt.
"""
import argparse
import json
import sys
from pathlib import Path

import guiqula
from guiqula import env


def _window(argv):
    parser = argparse.ArgumentParser(prog="guiqula", description="Graphical workbench for pyqula.")
    parser.add_argument("--version", action="version", version=f"guiqula {guiqula.__version__}")
    parser.add_argument("--offscreen", action="store_true",
                        help="render without a display (Qt offscreen platform)")
    parser.add_argument("document", nargs="?", help="project file or preset name to open")
    args = parser.parse_args(argv)
    env.configure_qt(offscreen=args.offscreen)
    from guiqula.ui.app import run
    return run(document=args.document)


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


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"run": _run, "script": _script}
    if argv and argv[0] in commands:
        return commands[argv[0]](argv[1:])
    return _window(argv)


if __name__ == "__main__":
    sys.exit(main())
