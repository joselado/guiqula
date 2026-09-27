"""The blocking client of a remote server (remote/server.py): what the MCP
bridge, the tests and any script use to drive a running guiqula.

    from guiqula.remote.client import connect
    with connect() as client:            # the newest running window or server
        client.call("do", command="add_term", args={"system": "s1", "kind": "haldane"})
        client.call("run", calculation="c1")
"""
import itertools
import json
import socket

from guiqula.remote import connection
from guiqula.remote.server import RemoteError

MARGIN = 30.0     # seconds a reply may take beyond the timeout the request asks for
LONGEST_WAIT = 3600.0     # api.LONGEST_WAIT: no request waits longer
WAITING = ("do", "run", "wait", "console")      # api.WAITING: the methods that may wait


class Client:
    def __init__(self, port, token, host="127.0.0.1", timeout=MARGIN):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.reader = self.sock.makefile("rb")
        self.ids = itertools.count(1)
        self.timeout = timeout
        self.info = self.call("hello", token=token)

    def call(self, method, /, **params):
        """Send a request and wait for its reply; raises RemoteError. A
        request that waits (a calculation) is given its "timeout" parameter
        plus a margin, else the longest wait the API allows."""
        rid = next(self.ids)
        message = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        wait = params.get("timeout", LONGEST_WAIT if method in WAITING else 0)
        self.sock.settimeout((wait if isinstance(wait, (int, float)) else LONGEST_WAIT)
                             + self.timeout)
        self.sock.sendall(json.dumps(message).encode() + b"\n")
        while True:
            line = self.reader.readline()
            if not line:
                raise ConnectionError("the server closed the connection")
            reply = json.loads(line)
            if reply.get("id") != rid:
                continue
            if "error" in reply:
                error = reply["error"]
                raise RemoteError(error.get("code"), error.get("message"), error.get("data"))
            return reply.get("result")

    def close(self):
        try:
            self.reader.close()
        finally:
            self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def connect(pid=None, timeout=MARGIN):
    """A Client of the newest running server, or of process pid."""
    found = connection.find(pid)
    if found is None:
        raise ConnectionError("no guiqula is running with remote control on" if pid is None
                              else f"no guiqula with remote control runs as process {pid}")
    return Client(found["port"], found["token"], timeout=timeout)
