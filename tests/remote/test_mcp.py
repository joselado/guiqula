"""guiqula serve and guiqula mcp (the Claude add-on, PLAN.md 3.7), as
processes: the MCP bridge spoken to line by line, with its own session and
attached to a running server; and the bridge's protocol replies."""
import base64
import io
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

import pytest

from guiqula.remote import connection
from guiqula.remote.client import connect
from guiqula.remote.mcp import VERSIONS, Bridge, tools
from guiqula.remote.server import INVALID_PARAMS, RemoteError

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")


def child_env():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([os.path.abspath(SRC)] + [
        p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p])
    return env


class McpProcess:
    def __init__(self, *args):
        self.process = subprocess.Popen([sys.executable, "-m", "guiqula", "mcp", *args],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env=child_env())
        self.ids = 0

    def send(self, method, params=None, notify=False):
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            self.ids += 1
            message["id"] = self.ids
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        self.process.stdin.flush()
        if notify:
            return None
        line = self.process.stdout.readline()
        assert line, self.process.stderr.read().decode()[-3000:]
        reply = json.loads(line)          # nothing but protocol messages on stdout
        assert reply["id"] == self.ids
        return reply

    def tool(self, tool, /, **arguments):
        reply = self.send("tools/call", {"name": tool, "arguments": arguments})
        return reply["result"]

    def close(self):
        self.process.stdin.close()
        assert self.process.wait(timeout=60) == 0
        return self.process.stderr.read().decode()


def text_of(result):
    return "\n".join(c["text"] for c in result["content"] if c["type"] == "text")


def test_protocol_replies():
    bridge = Bridge("headless")
    reply = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "t", "version": "0"}}})
    result = reply["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"]["name"] == "guiqula" and "status" in result["instructions"]
    # an unknown version gets the newest; the 2026 probe falls back to the handshake
    reply = bridge.handle({"id": 2, "method": "initialize", "params": {"protocolVersion": "1999"}})
    assert reply["result"]["protocolVersion"] == VERSIONS[-1]
    assert bridge.handle({"id": 3, "method": "server/discover"})["error"]["code"] == -32601
    assert bridge.handle({"method": "notifications/initialized"}) is None
    assert bridge.handle({"id": 4, "method": "ping"})["result"] == {}
    listed = bridge.handle({"id": 5, "method": "tools/list"})["result"]["tools"]
    assert [t["name"] for t in listed] == [t[0] for t in tools()]
    for tool in listed:
        assert tool["inputSchema"]["type"] == "object" and tool["description"]
        assert "readOnlyHint" in tool["annotations"]
    assert "add_term(system, kind" in next(t for t in listed if t["name"] == "command")[
        "description"]
    reply = bridge.handle({"id": 6, "method": "tools/call", "params": {"name": "nonsense"}})
    assert reply["error"]["code"] == -32602
    reply = bridge.handle({"id": 7, "method": "tools/call",
                           "params": {"name": "status", "arguments": {"bogus": 1}}})
    assert reply["result"]["isError"] is True           # the model sees what was wrong
    assert bridge.backend is None                       # nothing was started for it


def test_a_line_that_fails_does_not_end_the_bridge():
    """One line of deeply nested JSON (json.loads raises RecursionError, not
    ValueError) ended guiqula mcp, and its own session with every edit in
    it: it is a parse error now, and a request that fails is an internal
    error, as for the server (remote/server.py)."""
    bridge = Bridge("headless")
    ping = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
    out = io.BytesIO()
    bridge.serve([b"[" * 100000 + b"]" * 100000 + b"\n", ping + b"\n"], out)
    nested, pong = [json.loads(line) for line in out.getvalue().splitlines()]
    assert nested["error"]["code"] == -32700 and pong == {"jsonrpc": "2.0", "id": 1, "result": {}}
    bridge.handle = lambda message: 1 / 0             # whatever fails inside one request
    out = io.BytesIO()
    bridge.serve([ping + b"\n", ping + b"\n"], out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 1]
    assert replies[0]["error"]["code"] == -32603 and "ZeroDivisionError" in replies[0]["error"][
        "message"]
    assert bridge.backend is None


def test_a_window_that_crashed_is_not_found_again():
    """The connection file of a window that crashed while its pid still
    looks alive (a zombie of the bridge that launched it, or a pid used
    again) names a port nobody listens on: the bridge deletes it and goes
    on as when none runs, instead of failing every call with
    ConnectionRefusedError and never launching a new window."""
    if connection.instances():
        pytest.skip("another guiqula serves remotely in this run")
    with socket.socket() as sock:                 # a port nothing listens on
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    path = connection.write(port, "token", window=True)
    try:
        status = Bridge("attach").call_tool("status", {})
        assert status["isError"] and "guiqula --remote" in text_of(status), text_of(status)
        assert not path.exists()
        path = connection.write(port, "token", window=True)
        with pytest.raises(RemoteError) as error:
            Bridge("auto").connect(target="window")
        assert error.value.code == INVALID_PARAMS and not path.exists()
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.skipif(not hasattr(os, "waitid"), reason="os.waitid (POSIX)")
def test_a_window_it_opened_is_reaped_when_it_ends():
    """A window the bridge launched and that ended stayed a zombie of the
    bridge, whose pid looks alive: its connection file was kept."""
    bridge = Bridge("attach")
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    bridge.launched.append(child)
    os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)      # ended, not reaped
    bridge.connect()
    assert child.returncode == 0 and bridge.launched == []


@pytest.mark.parametrize("version", ["2024-11-05"])
def test_old_revisions_get_no_annotations(version):
    bridge = Bridge("headless")
    bridge.handle({"id": 1, "method": "initialize", "params": {"protocolVersion": version}})
    listed = bridge.handle({"id": 2, "method": "tools/list"})["result"]["tools"]
    assert all("annotations" not in t for t in listed)


def test_the_text_beside_a_plot_names_its_state():
    """A stale, failed, queued or running result's figure is sent with a line
    saying so (its title carries the mark too, test_api)."""
    bridge = Bridge("headless")
    replies = {}

    def call(method, **params):
        assert method == "plot"
        return {"png": "", "calculation": params["calculation"], "state": replies["state"]}
    bridge._call = call
    replies["state"] = "stale"
    assert bridge.tool_plot("c1")[1]["text"] == \
        "figure of c1, stale: the model changed since it was computed"
    replies["state"] = "failed"
    assert "last run failed" in bridge.tool_plot("c1")[1]["text"]
    replies["state"] = "done"
    assert bridge.tool_plot("c1")[1]["text"] == "figure of c1"


def test_mcp_with_its_own_session():
    mcp = McpProcess("--headless", "--document", "honeycomb_zeeman_rashba")
    try:
        reply = mcp.send("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                        "clientInfo": {"name": "test", "version": "0"}})
        assert reply["result"]["protocolVersion"] == "2025-11-25"
        mcp.send("notifications/initialized", notify=True)
        assert len(mcp.send("tools/list")["result"]["tools"]) == len(tools())
        status = mcp.tool("status")
        assert not status["isError"]
        assert text_of(status).startswith("connected to a session of the bridge's own")
        assert json.loads(text_of(status).split("\n", 1)[1])["systems"][0]["id"] == "s1"
        added = mcp.tool("command", name="add_term", args={"system": "s1", "kind": "haldane",
                                                            "params": {"t": 0.05}})
        assert json.loads(text_of(added))["result"] == "t3"
        refused = mcp.tool("command", name="add_term", args={"system": "s9", "kind": "haldane"})
        assert refused["isError"] and "s9" in text_of(refused)
        # a command's own OSError, and a connect to a misspelt document, keep the session
        unsaved = mcp.tool("command", name="save", args={"path": "no/such/folder/x.guiqula"})
        assert unsaved["isError"] and "lost" not in text_of(unsaved)
        assert mcp.tool("connect", target="headless", document="no_such_preset")["isError"]
        assert '"t3"' in text_of(mcp.tool("status"))
        run = json.loads(text_of(mcp.tool("run_calculation", calculation="c1")))
        assert run["status"] == "done", run
        plot = mcp.tool("plot", calculation="c1")
        image = plot["content"][0]
        assert image["type"] == "image" and image["mimeType"] == "image/png"
        assert base64.b64decode(image["data"])[:4] == b"\x89PNG"
        assert text_of(plot) == "figure of c1"             # current: nothing more to say
        shot = mcp.tool("screenshot")
        assert shot["isError"] and "window" in text_of(shot)
        assert "add_haldane" in text_of(mcp.tool("help", kind="haldane"))
        found = text_of(mcp.tool("help", search="rashba", limit=2))
        assert "help(kind='rashba', family='term')" in found
        assert "get_bands" in text_of(mcp.tool("script", calculation="c1"))
        out = mcp.tool("console", code="print('from the console', h.intra.shape)")
        assert "from the console (16, 16)" in text_of(out) and not out["isError"]
        failed = mcp.tool("console", code="1/0")
        assert failed["isError"] and "ZeroDivisionError" in text_of(failed)
        undo = json.loads(text_of(mcp.tool("command", name="undo")))
        assert undo["result"]["redo"][0].startswith("add")      # the history after it
    finally:
        stderr = mcp.close()
    assert "Traceback" not in stderr, stderr[-3000:]


def test_serve_and_attach():
    serve = subprocess.Popen([sys.executable, "-m", "guiqula", "serve", "honeycomb_zeeman_rashba",
                              "--no-warm"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=child_env(), text=True)
    try:
        info = json.loads(serve.stdout.readline())
        assert os.path.exists(info["connection_file"])
        with connect(info["pid"]) as client:
            assert client.info["window"] is False
            reply = client.call("do", command="set_param",
                                args={"entry": "t2", "name": "c", "value": 0.2})
            assert reply["systems"]["s1"]["build"]["current"]
        mcp = McpProcess("--attach")
        try:
            mcp.send("initialize", {"protocolVersion": "2025-06-18"})
            status = mcp.tool("status")
            assert text_of(status).startswith(f"connected to guiqula serve of process "
                                              f"{info['pid']}")
            document = json.loads(text_of(mcp.tool("document")))
            assert document["systems"][0]["hamiltonian"]["terms"][1]["params"]["c"] == 0.2
            listed = json.loads(text_of(mcp.tool("connect")))
            assert info["pid"] in [r["pid"] for r in listed["running"]]
            assert all("token" not in r for r in listed["running"])
        finally:
            mcp.close()
    finally:
        serve.send_signal(signal.SIGTERM)       # on Windows: TerminateProcess, no clean stop
        code = serve.wait(timeout=60)
    if os.name == "posix":
        assert code == 0, serve.stderr.read()[-3000:]
        assert not os.path.exists(info["connection_file"])     # removed on a clean stop


def test_serve_goes_on_while_the_console_runs():
    """do console waited for its job inside guiqula serve's loop: no other
    client got an answer, not even interrupt_console, and SIGTERM (a flag
    read by that loop) did not stop it. The reply waits in a Pending now."""
    serve = subprocess.Popen([sys.executable, "-m", "guiqula", "serve", "honeycomb_zeeman_rashba",
                              "--no-warm"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=child_env(), text=True)
    replies = []

    def endless():
        try:
            with connect(info["pid"]) as client:
                replies.append(client.call("do", command="console",
                                           args={"code": "while True: pass"}, timeout=300))
        except (OSError, RemoteError) as error:        # serve stopped under it
            replies.append(error)
    try:
        info = json.loads(serve.stdout.readline())
        thread = threading.Thread(target=endless, daemon=True)
        thread.start()
        time.sleep(2)
        with connect(info["pid"], timeout=10) as other:
            assert other.call("status")["systems"][0]["id"] == "s1"
            other.call("do", command="interrupt_console")
        thread.join(30)
        assert replies[0]["result"]["status"] == "cancelled"
        thread = threading.Thread(target=endless, daemon=True)
        thread.start()
        time.sleep(2)
    finally:
        serve.send_signal(signal.SIGTERM)
        try:
            code = serve.wait(timeout=30)
        except subprocess.TimeoutExpired:
            serve.kill()
            serve.wait()
            raise
    if os.name == "posix":
        assert code == 0, serve.stderr.read()[-3000:]
        assert not os.path.exists(info["connection_file"])


def test_attach_without_a_server_says_so():
    before = {i["pid"] for i in connection.instances()}
    mcp = McpProcess("--attach")
    try:
        mcp.send("initialize", {"protocolVersion": "2025-06-18"})
        if before:
            pytest.skip("another guiqula serves remotely in this run")
        status = mcp.tool("status")
        assert status["isError"] and "guiqula --remote" in text_of(status)
    finally:
        mcp.close()


@pytest.mark.skipif(not os.environ.get("GUIQULA_MCP_PYTHON"),
                    reason="set GUIQULA_MCP_PYTHON to a Python with the MCP SDK (pip install mcp)")
def test_the_sdk_client_understands_the_bridge(repo):
    """The official MCP SDK's client against guiqula's own protocol code."""
    done = subprocess.run([os.environ["GUIQULA_MCP_PYTHON"], str(repo / "tools" / "mcp_check.py"),
                           "--python", sys.executable], capture_output=True, text=True,
                          timeout=600, env=child_env())
    assert done.returncode == 0, done.stdout + done.stderr[-3000:]
    assert json.loads(done.stdout)["server"] == "guiqula"
