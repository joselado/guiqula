"""Connection files (PLAN.md 3.7): a running remote server writes one to
the user data directory ($GUIQULA_DATA_DIR overrides it), readable by the
user only, with its port and token; a client reads it to find the server.
The file is deleted when the server stops; the file of a process that is
gone (a crash) is deleted by the next listing.
"""
import json
import os
import socket
import time

import guiqula
from guiqula import env
from guiqula.io.autosave import pid_alive


def directory():
    return env.user_data_dir() / "remote"


def write(port, token, **info):
    """Write this process's connection file; returns its path."""
    folder = directory()
    folder.mkdir(parents=True, exist_ok=True)
    host = socket.gethostname()
    path = folder / f"{host}-{os.getpid()}.json"
    data = dict(info, port=port, token=token, pid=os.getpid(), host=host,
                started=time.time(), guiqula=guiqula.__version__)
    temporary = path.with_suffix(".tmp")
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w") as out:
        json.dump(data, out)
    os.replace(temporary, path)
    return path


def update(path, **info):
    """Change what a connection file says (the document the window shows)."""
    data = json.loads(path.read_text())
    data.update(info)
    temporary = path.with_suffix(".tmp")
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w") as out:
        json.dump(data, out)
    os.replace(temporary, path)


def instances():
    """The servers running on this machine, newest first (each the dict of
    its file, with "file" its path)."""
    folder = directory()
    if not folder.is_dir():
        return []
    host = socket.gethostname()
    found = []
    for path in folder.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            pid = int(data["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if data.get("host") != host:        # a home directory shared between machines
            continue
        if not pid_alive(pid):
            path.unlink(missing_ok=True)
            continue
        data["file"] = str(path)
        found.append(data)
    return sorted(found, key=lambda d: d.get("started", 0), reverse=True)


def find(pid=None):
    """The newest running server, or the one of process pid; None if none."""
    for data in instances():
        if pid is None or data["pid"] == pid:
            return data
    return None
