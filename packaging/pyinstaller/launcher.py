"""The entry point of the frozen guiqula (packaging/pyinstaller/guiqula.spec).

The workers are started with multiprocessing's spawn method, which in a
frozen application runs this same executable again: freeze_support() turns
that run into the worker, before anything else happens. pyqula's own pool
(the multiprocess package) gets the same treatment.
"""
import multiprocessing
import os
import sys

if __name__ == "__main__":
    # a windowed executable (Windows, macOS) has no standard streams: None, which a
    # library writing to them directly would trip on; the workers inherit this
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    multiprocessing.freeze_support()
    try:
        import multiprocess
        multiprocess.freeze_support()
    except ImportError:
        pass
    from guiqula.__main__ import main
    sys.exit(main())
