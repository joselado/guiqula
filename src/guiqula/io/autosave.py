"""Autosave and crash recovery (PLAN.md 3.5, decision 14.4).

A Session opened with ``autosave=True`` (the window's) owns an Autosaver:
every dispatcher event marks it changed, and Session.poll() calls tick(),
which writes the Document at most once per ``delay`` seconds of quiet (and
at least every ``max_delay`` seconds while changes keep coming), so a
slider drag is one write, not hundreds. No threads and no Qt: whoever
polls the session drives it. A clean close deletes the file; a crash or a
kill leaves it behind.

An autosave file is JSON in ``<user data dir>/autosave/``: the Document, the
project file it belongs to (``source``), whether it had unsaved changes,
and the pid and host of the process that wrote it. recoverable() lists the
files of processes that no longer run (on this host), newest first; by
default only those with unsaved changes, since the others equal a file on
disk.
"""
import json
import os
import socket
import time
from pathlib import Path

from guiqula import env
from guiqula.core.document import Document, DocumentError

FORMAT = "guiqula-autosave"
DELAY = 1.0          # seconds of quiet before a write
MAX_DELAY = 5.0      # longest a change waits while changes keep coming


def autosave_dir():
    return env.user_data_dir() / "autosave"


def pid_alive(pid):
    """Whether a process with this pid runs on this machine."""
    if pid <= 0:            # os.kill(-1, 0) would signal every process we may signal
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":      # os.kill(pid, 0) would terminate the process on Windows
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not _zombie(pid)


def _zombie(pid):
    """Whether the process has ended and waits for its parent to reap it
    (Linux; elsewhere False): os.kill finds it all the same."""
    try:
        with open(f"/proc/{pid}/stat") as stat:
            return stat.read().rpartition(")")[2].split()[0] == "Z"   # after the name
    except (OSError, IndexError):
        return False


class Autosaver:
    def __init__(self, directory=None, delay=DELAY, max_delay=MAX_DELAY, clock=time.monotonic):
        self.directory = Path(directory) if directory is not None else autosave_dir()
        self.started = time.time()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.started))
        self.path = self.directory / f"{stamp}-{os.getpid()}.json"
        self.delay, self.max_delay, self.clock = delay, max_delay, clock
        self.first_change = None    # clock time of the oldest unwritten change
        self.last_change = None     # clock time of the newest one
        self.saved_at = None        # wall time of the last write
        self.error = None           # message of the last failed write

    @property
    def pending(self):
        return self.first_change is not None

    def changed(self):
        now = self.clock()
        if self.first_change is None:
            self.first_change = now
        self.last_change = now

    def due(self):
        if not self.pending:
            return False
        now = self.clock()
        return now - self.last_change >= self.delay or now - self.first_change >= self.max_delay

    def tick(self, document, source=None, modified=True):
        """Write if due; returns True when it wrote."""
        if not self.due():
            return False
        self.write(document, source, modified)
        return True

    def write(self, document, source=None, modified=True):
        data = {"format": FORMAT, "version": 1, "pid": os.getpid(), "host": socket.gethostname(),
                "started": self.started, "saved": time.time(),
                "source": str(source) if source is not None else None, "modified": bool(modified),
                "document": json.loads(document.to_json())}
        self.first_change = self.last_change = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + ".tmp")
            temporary.write_text(json.dumps(data), encoding="utf-8")
            temporary.replace(self.path)
        except OSError as error:     # a full disk must not take the program down
            self.error = f"autosave failed: {error}"
            return None
        self.error = None
        self.saved_at = data["saved"]
        return self.path

    def adopt(self, path):
        """Continue writing to an autosave file taken over from a crashed
        session (recovery), so the recovered work stays recoverable until
        it is saved; this session's own file is removed."""
        path = Path(path)
        if path != self.path:
            self.discard()
            self.path = path
        self.changed()

    def discard(self):
        """Remove the file (a clean close)."""
        for p in (self.path, self.path.with_name(self.path.name + ".tmp")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def read(path):
    """(Document, info) of an autosave file; raises DocumentError."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DocumentError(f"{path}: not a readable autosave ({error})") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise DocumentError(f"{path}: not a guiqula autosave")
    if "document" not in data:
        raise DocumentError(f"{path}: an autosave without its document")
    document = Document.from_data(data["document"])
    info = {k: v for k, v in data.items() if k != "document"}
    info["path"] = str(path)
    return document, info


def recoverable(directory=None, include_unmodified=False):
    """Autosaves left behind by sessions that ended without closing
    cleanly, newest first: dicts with path, saved, source, modified,
    systems (names) and calculations (count). Unreadable files are listed
    with an ``error``: one damaged file (another version's, a truncated
    copy) must not hide the others."""
    directory = Path(directory) if directory is not None else autosave_dir()
    if not directory.is_dir():
        return []
    host = socket.gethostname()
    out = []
    for path in directory.glob("*.json"):
        try:
            document, info = read(path)
            running = info.get("host") == host and pid_alive(int(info.get("pid", -1)))
            info["saved"] = float(info.get("saved", 0))
        except Exception as error:
            out.append({"path": str(path), "saved": _mtime(path), "error": str(error)})
            continue
        if running:
            continue                    # another running session's file
        if not info.get("modified") and not include_unmodified:
            continue
        info.update(systems=[s.name or s.id for s in document.systems],
                    calculations=len(document.calculations))
        out.append(info)
    return sorted(out, key=lambda i: i["saved"], reverse=True)


def _mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def discard(path):
    Path(path).unlink(missing_ok=True)
