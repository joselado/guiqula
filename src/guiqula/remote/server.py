"""A JSON-RPC 2.0 server on a localhost socket (PLAN.md 3.7).

One JSON message per line, both ways. The first request of a connection
must be ``hello`` with the token of the connection file
(remote/connection.py); anything else is refused and the connection
closed. Then every request names a method of the handler (remote/api.py)
with its parameters as an object.

The server never runs by itself: poll() accepts connections, reads
requests, calls the handler and writes the replies, and the host calls it
from its own loop (the window's timer, ``guiqula serve``), so the Session
is only ever touched from one thread. A handler that has to wait (a
calculation, the builds after a command) returns a Pending: poll() checks
it every time and sends the reply once it is ready, or when its time is up,
so a long calculation never holds up the window.

Error codes: the JSON-RPC ones (-32700 parse error, -32600 invalid
request, -32601 unknown method, -32602 invalid parameters, -32603 internal
error), -32000 a command refused (the Document is unchanged), -32001 not
authorized.
"""
import hmac
import json
import secrets
import selectors
import socket
import time
import traceback

from guiqula.commands import CommandError
from guiqula.remote import connection

PARSE_ERROR, INVALID_REQUEST, NO_METHOD, INVALID_PARAMS, INTERNAL = \
    -32700, -32600, -32601, -32602, -32603
REFUSED, UNAUTHORIZED = -32000, -32001
LINE_LIMIT = 64 * 2**20      # a request longer than this closes the connection


class RemoteError(Exception):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def error_of(method, error):
    """(code, message, data) of an exception raised by a handler: a refused
    command (a CommandError, or the ValueError of a window action given a
    wrong value) is -32000, wrong parameters -32602, anything else an
    internal error with its traceback."""
    if isinstance(error, RemoteError):
        return error.code, error.message, error.data
    if isinstance(error, CommandError):
        return REFUSED, str(error), None
    if isinstance(error, (ValueError, LookupError)):
        return REFUSED, f"{method}: {error}", traceback.format_exc()
    if isinstance(error, TypeError):
        return INVALID_PARAMS, f"{method}: {error}", None
    return INTERNAL, f"{method}: {type(error).__name__}: {error}", traceback.format_exc()


class Pending:
    """A reply that is not ready yet: ready() says when it is, finish(timed_out)
    makes it (timed_out is true when timeout seconds went by first)."""

    def __init__(self, ready, finish, timeout=None):
        self.ready = ready
        self.finish = finish
        self.deadline = None if timeout is None else time.monotonic() + timeout

    def due(self):
        """None while waiting, else the value to send (or an exception to raise)."""
        if self.ready():
            return self.finish(False)
        if self.deadline is not None and time.monotonic() > self.deadline:
            return self.finish(True)
        return None


def resolve(value, poll, interval=0.05):
    """Wait for a Pending in this thread, calling poll(interval) meanwhile
    (a host without a server of its own: the MCP bridge's own Session)."""
    while isinstance(value, Pending):
        due = value.due()
        if due is not None:
            return due
        poll(interval)
    return value


class _Connection:
    def __init__(self, sock, address):
        self.sock = sock
        self.address = address
        self.inbox = b""
        self.outbox = b""
        self.authorized = False
        self.closing = False       # close once the outbox is written


class Server:
    """handler(method, params) -> value or Pending; raises RemoteError,
    CommandError (refused), TypeError (bad parameters)."""

    def __init__(self, handler, host="127.0.0.1", port=0, token=None):
        self.handler = handler
        self.token = token or secrets.token_urlsafe(32)
        self.listener = socket.create_server((host, port))
        self.listener.setblocking(False)
        self.host, self.port = self.listener.getsockname()[:2]
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.listener, selectors.EVENT_READ, None)
        self.connections = []
        self.pending = []          # [(connection, request id, Pending)]
        self.file = None           # the connection file, once published
        self.requests = 0          # handled so far (the window shows it)
        self.errors = []           # internal errors: (method, traceback), newest last

    def publish(self, **info):
        """Write the connection file clients find the server by."""
        self.file = connection.write(self.port, self.token, **info)
        return self.file

    def update(self, **info):
        if self.file is not None:
            try:
                connection.update(self.file, **info)
            except (OSError, ValueError):
                pass

    # ---- the loop
    def poll(self, timeout=0.0):
        """Serve what is waiting; returns the number of events handled."""
        count = 0
        for key, events in self.selector.select(timeout):
            count += 1
            if key.data is None:
                self._accept()
                continue
            conn = key.data
            if events & selectors.EVENT_READ:
                self._read(conn)
            if events & selectors.EVENT_WRITE and conn in self.connections:
                self._flush(conn)
        self._check_pending()
        return count

    def _accept(self):
        try:
            sock, address = self.listener.accept()
        except (BlockingIOError, InterruptedError):
            return
        sock.setblocking(False)
        conn = _Connection(sock, address)
        self.connections.append(conn)
        self.selector.register(sock, selectors.EVENT_READ, conn)

    def _read(self, conn):
        try:
            data = conn.sock.recv(1 << 16)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self._close(conn)
            return
        conn.inbox += data
        while b"\n" in conn.inbox and conn in self.connections and not conn.closing:
            line, conn.inbox = conn.inbox.split(b"\n", 1)
            if line.strip():
                self._handle(conn, line)
        if len(conn.inbox) > LINE_LIMIT:
            self._close(conn)

    def _handle(self, conn, line):
        try:
            request = json.loads(line)
        except ValueError:
            self._reply(conn, None, error=(PARSE_ERROR, "not JSON"))
            return
        if not isinstance(request, dict) or not isinstance(request.get("method"), str):
            self._reply(conn, request.get("id") if isinstance(request, dict) else None,
                        error=(INVALID_REQUEST, "a request is an object with a method"))
            return
        rid, method = request.get("id"), request["method"]
        params = request.get("params") or {}
        if not isinstance(params, dict):
            self._reply(conn, rid, error=(INVALID_PARAMS, "params must be an object"))
            return
        if not conn.authorized:
            token = params.get("token")
            if method != "hello" or not isinstance(token, str) or \
                    not hmac.compare_digest(token.encode(), self.token.encode()):
                self._reply(conn, rid, error=(UNAUTHORIZED, "say hello with the token of the "
                                                            "connection file first"))
                conn.closing = True
                self._flush(conn)
                return
            conn.authorized = True
            params = {}
        self.requests += 1
        try:
            value = self.handler(method, params)
        except Exception as error:
            self._reply(conn, rid, error=self._error_of(method, error))
            return
        if isinstance(value, Pending):
            self.pending.append((conn, rid, value))
        elif rid is not None:
            self._reply(conn, rid, result=value)

    def _error_of(self, method, error):
        code, message, data = error_of(method, error)
        if code == INTERNAL:
            self.errors.append((method, data))
            del self.errors[:-20]
        return code, message, data

    def _check_pending(self):
        for item in list(self.pending):
            conn, rid, pending = item
            if conn not in self.connections:
                self.pending.remove(item)
                continue
            try:
                value = pending.due()
            except Exception as error:
                self.pending.remove(item)
                self._reply(conn, rid, error=self._error_of("pending", error))
                continue
            if value is not None:
                self.pending.remove(item)
                if rid is not None:
                    self._reply(conn, rid, result=value)

    def _reply(self, conn, rid, result=None, error=None):
        message = {"jsonrpc": "2.0", "id": rid}
        if error is not None:
            message["error"] = {"code": error[0], "message": error[1]}
            if len(error) > 2 and error[2] is not None:
                message["error"]["data"] = error[2]
        else:
            message["result"] = result
        try:
            data = json.dumps(message, allow_nan=False)
        except (TypeError, ValueError) as problem:
            data = json.dumps({"jsonrpc": "2.0", "id": rid, "error": {
                "code": INTERNAL, "message": f"the reply is not JSON: {problem}"}})
        conn.outbox += data.encode() + b"\n"
        self._flush(conn)

    def _flush(self, conn):
        while conn.outbox:
            try:
                sent = conn.sock.send(conn.outbox)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                self._close(conn)
                return
            conn.outbox = conn.outbox[sent:]
        if not conn.outbox and conn.closing:
            self._close(conn)
            return
        wanted = selectors.EVENT_READ | (selectors.EVENT_WRITE if conn.outbox else 0)
        self.selector.modify(conn.sock, wanted, conn)

    def _close(self, conn):
        if conn in self.connections:
            self.connections.remove(conn)
            self.selector.unregister(conn.sock)
        conn.sock.close()

    def close(self):
        """Stop listening, drop the clients, delete the connection file."""
        for conn in list(self.connections):
            self._close(conn)
        self.selector.unregister(self.listener)
        self.listener.close()
        self.selector.close()
        if self.file is not None:
            self.file.unlink(missing_ok=True)
            self.file = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
