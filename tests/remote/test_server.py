"""The JSON-RPC server and its connection files (remote/server.py,
remote/connection.py), with a toy handler: no Session, no workers."""
import json
import os
import socket
import stat
import threading
import time

import pytest

from guiqula.commands import CommandError
from guiqula.remote import connection
from guiqula.remote.client import Client
from guiqula.remote.server import (INVALID_PARAMS, NO_METHOD, PARSE_ERROR, REFUSED,
                                   UNAUTHORIZED, Pending, RemoteError, Server, resolve)


class Toy:
    def __init__(self):
        self.flag = False

    def __call__(self, method, params):
        if method == "hello":
            return {"hi": True}
        if method == "echo":
            return params
        if method == "big":
            return {"data": "x" * (4 * 2**20)}
        if method == "refuse":
            raise CommandError("no")
        if method == "typed":
            return (lambda a: a)(**params)
        if method == "later":
            return Pending(lambda: self.flag, lambda timed_out: {"timed_out": timed_out},
                           params.get("timeout"))
        if method == "crash":
            raise ZeroDivisionError("boom")
        raise RemoteError(NO_METHOD, f"unknown {method}")


@pytest.fixture
def served():
    """A server polled by a thread (the host's loop), and its handler."""
    toy = Toy()
    server = Server(toy)
    server.publish(window=False)
    stop = threading.Event()
    thread = threading.Thread(target=lambda: [server.poll(0.01) for _ in iter(stop.is_set, True)])
    thread.start()
    yield server, toy
    stop.set()
    thread.join()
    server.close()


def raw(server):
    sock = socket.create_connection(("127.0.0.1", server.port), timeout=10)
    return sock, sock.makefile("rb")


def send(sock, reader, message):
    sock.sendall((message if isinstance(message, bytes) else json.dumps(message).encode())
                 + b"\n")
    return json.loads(reader.readline())


def test_round_trip_and_errors(served):
    server, toy = served
    with Client(server.port, server.token) as client:
        assert client.info == {"hi": True}
        assert client.call("echo", a=1, b=[1, 2]) == {"a": 1, "b": [1, 2]}
        for method, params, code in (("nothing", {}, NO_METHOD), ("refuse", {}, REFUSED),
                                     ("typed", {"b": 1}, INVALID_PARAMS)):
            with pytest.raises(RemoteError) as error:
                client.call(method, **params)
            assert error.value.code == code
        with pytest.raises(RemoteError) as error:
            client.call("crash")
        assert "ZeroDivisionError" in error.value.message and "Traceback" in error.value.data
        assert len(client.call("big")["data"]) == 4 * 2**20      # written over many polls
        assert client.call("echo", z=0) == {"z": 0}              # the connection is still fine


def test_the_token_is_required(served):
    server, _ = served
    sock, reader = raw(server)
    reply = send(sock, reader, {"jsonrpc": "2.0", "id": 1, "method": "echo", "params": {}})
    assert reply["error"]["code"] == UNAUTHORIZED
    assert reader.readline() == b""                          # and the connection is closed
    sock, reader = raw(server)
    reply = send(sock, reader, {"jsonrpc": "2.0", "id": 1, "method": "hello",
                                "params": {"token": "wrong"}})
    assert reply["error"]["code"] == UNAUTHORIZED
    with pytest.raises(RemoteError):
        Client(server.port, server.token[:-1] + "x")


def test_malformed_requests(served):
    server, _ = served
    sock, reader = raw(server)
    send(sock, reader, {"jsonrpc": "2.0", "id": 1, "method": "hello",
                        "params": {"token": server.token}})
    assert send(sock, reader, b"{not json")["error"]["code"] == PARSE_ERROR
    assert send(sock, reader, {"id": 2, "params": {}})["error"]["code"] == -32600
    assert send(sock, reader, {"id": 3, "method": "echo", "params": [1]})["error"]["code"] \
        == INVALID_PARAMS
    # a notification (no id) gets no reply: the next reply is the next request's
    sock.sendall(json.dumps({"jsonrpc": "2.0", "method": "echo", "params": {}}).encode() + b"\n")
    assert send(sock, reader, {"id": 4, "method": "echo", "params": {"n": 4}})["result"] == \
        {"n": 4}


def test_deeply_nested_json_does_not_stop_the_server(served):
    """json.loads raises RecursionError, not ValueError, on it: one line,
    before any hello, ended `guiqula serve`."""
    server, _ = served
    sock, reader = raw(server)
    assert send(sock, reader, b"[" * 100000)["error"]["code"] == PARSE_ERROR
    with Client(server.port, server.token) as client:
        assert client.call("echo", a=1) == {"a": 1}


def test_pending_replies_do_not_block_other_clients(served):
    server, toy = served
    replies = {}
    with Client(server.port, server.token) as first, Client(server.port, server.token) as second:
        thread = threading.Thread(target=lambda: replies.update(first.call("later", timeout=30)))
        thread.start()
        time.sleep(0.2)
        assert second.call("echo", ok=True) == {"ok": True}     # served while the first waits
        assert thread.is_alive()
        toy.flag = True
        thread.join(10)
        assert replies == {"timed_out": False}
        toy.flag = False
        assert first.call("later", timeout=0.2) == {"timed_out": True}


def test_resolve_polls_until_ready():
    ticks = []
    pending = Pending(lambda: len(ticks) >= 3, lambda timed_out: "done")
    assert resolve(pending, lambda interval: ticks.append(interval)) == "done"
    assert len(ticks) == 3 and resolve(5, None) == 5


def test_connection_files(served):
    server, _ = served
    path = server.file
    assert path.parent == connection.directory()
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600      # the token is the user's only
    found = connection.find(os.getpid())
    assert found["port"] == server.port and found["token"] == server.token
    assert found["window"] is False
    server.update(document="x.guiqula")
    assert connection.find(os.getpid())["document"] == "x.guiqula"
    # a file left by a process that is gone is dropped from the listing and deleted
    dead = connection.directory() / "gone.json"
    dead.write_text(json.dumps({"pid": 2**22 + 12345, "host": socket.gethostname(),
                                "port": 1, "token": "t", "started": time.time()}))
    assert all(i["pid"] != 2**22 + 12345 for i in connection.instances())
    assert not dead.exists()


def test_close_deletes_the_connection_file():
    server = Server(Toy())
    path = server.publish()
    assert path.exists()
    server.close()
    assert not path.exists()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", server.port), timeout=2)
