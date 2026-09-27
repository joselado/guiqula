"""``guiqula mcp``: the Claude add-on (PLAN.md 3.7), an MCP server on
stdin and stdout whose tools call the remote API (remote/api.py).

It drives a running guiqula (a window with remote control on, File >
Allow remote control or ``guiqula --remote``, or ``guiqula serve``),
found through its connection file; or, when none runs, a Session of its
own, without a window (no screenshots). ``connect`` switches between them
and can open a window. Register it with Claude Code:

    claude mcp add guiqula -- guiqula mcp

The protocol is written here (JSON-RPC 2.0, one message per line, the
initialize handshake of the revisions 2024-11-05 to 2025-11-25), without
the MCP SDK and its dependencies; tests/remote/test_mcp.py drives it with
that SDK's client where it is installed.

Nothing but protocol messages may reach stdout: main() moves the real
stdout aside for them and points file descriptor 1 at stderr, so a print
anywhere, pyqula's in the worker processes included, lands in stderr.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import guiqula
from guiqula.remote import connection
from guiqula.remote.server import (INTERNAL, INVALID_PARAMS, INVALID_REQUEST, NO_METHOD,
                                   PARSE_ERROR, RemoteError, error_of, resolve)

VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
LAUNCH_PATIENCE = 90.0     # seconds a launched window has to publish its connection file

INSTRUCTIONS = """\
guiqula is a graphical workbench for pyqula, a Python tight-binding library. A document \
holds systems (a lattice, geometry operations, Hamiltonian terms and an optional mean \
field; or a classical spin, Ising or lattice-gas model) and calculations on them (bands, \
DOS, Chern numbers, sweeps...). Every change is a command, undoable and checked: call \
`status` first; `catalogue` lists the lattices, operations, terms and calculations with \
their parameters; `command` changes the document (add_system, add_geometry_op, add_term, \
set_param, add_calculation, remove, undo...); `run_calculation`, then `result` or `plot`, \
shows what comes out. A term parameter is a Field: a number, an expression of the position \
as a string ("0.3*cos(x)"), or an object (piecewise per region, profile, painted...; `help` \
with guide "guiqula" and anchor "Fields"). `help` also gives pyqula's own documentation of \
any entry. With a window what you do shows there and `screenshot` shows it; without one the \
bridge runs a session of its own. Python nodes run only in a trusted document."""


# ---- backends: a running guiqula, or a Session of the bridge's own
class Attached:
    def __init__(self, found):
        from guiqula.remote.client import Client
        self.found = found
        self.client = Client(found["port"], found["token"])

    def call(self, method, **params):
        return self.client.call(method, **params)

    def describe(self):
        what = "the window" if self.found.get("window") else "guiqula serve"
        return f"{what} of process {self.found['pid']}"

    def close(self):
        self.client.close()


class Headless:
    def __init__(self, document=None, trust=False):
        from guiqula.remote.api import RemoteAPI
        from guiqula.session import Session
        self.session = Session(document)
        if trust:
            self.session.act("trust")
        self.api = RemoteAPI(self.session)
        if self.session.document.systems:
            self.session.build_all()

    def call(self, method, **params):
        return resolve(self.api(method, params), self.session.poll)

    def describe(self):
        return "a session of the bridge's own, without a window"

    def close(self):
        self.api.close()
        self.session.close()


def _session_actions():
    from guiqula.commands.dispatcher import _signature
    from guiqula.session import ACTIONS, Session
    return {name: _signature(getattr(Session, "_action_" + name)) for name in ACTIONS}


def _command_description():
    from guiqula.commands import Dispatcher
    from guiqula.remote.api import WINDOW_ACTIONS
    mutations = Dispatcher().mutations()
    lines = ["Run a guiqula command: a mutation of the document (undoable) or an action. "
             "args is an object of its parameters. The reply comes once the geometry is "
             "rebuilt and says each system's sites, Hilbert space and invalid entries. "
             "Mutations:"]
    lines += [f"- {name}({', '.join(params)})" for name, params in mutations.items()]
    lines.append("Actions:")
    lines += [f"- {name}({', '.join(params)})" for name, params in _session_actions().items()]
    lines.append("With a window, also: " + "; ".join(
        f"{name}({params})" for name, params in WINDOW_ACTIONS.items()) + ".")
    lines.append("Ids: s1 systems, o1 geometry ops, t1 terms, r1 regions, c1 calculations. "
                 "A term's params are Fields (a number, an expression string, or an object).")
    return "\n".join(lines)


def _schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required),
            "additionalProperties": False}


CALC = {"calculation": {"type": "string", "description": "calculation id, e.g. c1"}}
TIMEOUT = {"timeout": {"type": "number", "description": "seconds to wait (default 300)"}}


def tools():
    """[(name, description, input schema, read only)]"""
    return [
        ("status", "Outline of the open document: systems (lattice, geometry ops, regions, "
                   "terms, Hilbert space, the latest build: sites and dimension; invalid "
                   "entries), calculations with their status and estimated seconds, undo "
                   "steps, and the window's state. Start here.", _schema(), True),
        ("document", "The whole document as JSON (every parameter of every entry).",
         _schema(), True),
        ("commands", "Every command with its parameters (mutations and actions, the "
                     "window's included).", _schema(), True),
        ("catalogue", "What can be added: registry entries (lattice, geometry_op, term, "
                      "meanfield, model, calculation) with their parameters. Without a family "
                      "or a search, one line per entry.",
         _schema({"family": {"type": "string", "enum": ["lattice", "geometry_op", "term",
                                                        "meanfield", "model", "calculation"]},
                  "system_kind": {"type": "string", "enum": ["quantum", "classical_spin",
                                                             "lattice_gas", "ising"]},
                  "search": {"type": "string", "description": "words to look for"}}), True),
        ("command", _command_description(),
         _schema({"name": {"type": "string"},
                  "args": {"type": "object", "description": "the command's parameters"}},
                 ("name",)), False),
        ("run_calculation", "Run a calculation and wait for it; replies with the result's "
                            "summary (arrays and their shapes and ranges).",
         _schema(dict(CALC, **TIMEOUT, cores={"type": "integer", "description":
                                              "processes for pyqula's own pool"}),
                 ("calculation",)), False),
        ("wait", "Wait for a calculation that is still running.",
         _schema(dict(CALC, **TIMEOUT), ("calculation",)), True),
        ("result", "A result: summary, arrays with shapes and ranges, and the values of the "
                   "arrays asked for (long arrays are thinned to max_values numbers).",
         _schema(dict(CALC, arrays={"description": 'array names, or "all"',
                                    "anyOf": [{"type": "array", "items": {"type": "string"}},
                                              {"type": "string", "enum": ["all"]}]},
                      max_values={"type": "integer"}), ("calculation",)), True),
        ("plot", "The figure of a result, as the result view draws it.",
         _schema(CALC, ("calculation",)), True),
        ("screenshot", "A screenshot of the window, or of one of its widgets by name "
                       "(structureView: the canvas; plot_c1: a result view; outliner; "
                       "helpDock...; widgets lists them). Needs a window.",
         _schema({"widget": {"type": "string"}}), True),
        ("widgets", "The names of the window's widgets a screenshot takes.", _schema(), True),
        ("help", "Help as Markdown: of a document item (item: t1, c1, s1/base...), of a "
                 "registry entry (kind, with family if ambiguous), or of a section of a "
                 'guide (guide: "pyqula" or "guiqula", anchor: a heading); a guide alone '
                 'gives its contents; guide "plugins" lists the installed plugins.',
         _schema({"item": {"type": "string"}, "kind": {"type": "string"},
                  "family": {"type": "string"}, "guide": {"type": "string", "enum": [
                      "pyqula", "guiqula", "plugins"]},
                  "anchor": {"type": "string"}}), True),
        ("script", "The standalone pyqula script that computes a calculation.",
         _schema(CALC, ("calculation",)), True),
        ("console", "Run Python in guiqula's console worker: g and h (the geometry and "
                    "Hamiltonian of a system, the first by default), doc, do(...) for "
                    "commands, np, pyqula. Returns the output.",
         _schema({"code": {"type": "string"}, "system": {"type": "string"}, **TIMEOUT},
                 ("code",)), False),
        ("connect", "Which guiqula the tools drive: lists the running ones; target "
                    '"window" attaches to one (pid, or the newest; launch: open a window '
                    'if none runs, with a document), "headless" starts a session without a '
                    "window (with a document: a preset name or a file).",
         _schema({"target": {"type": "string", "enum": ["window", "headless"]},
                  "pid": {"type": "integer"}, "launch": {"type": "boolean"},
                  "document": {"type": "string"}}), False),
    ]


# ---- the bridge
class Bridge:
    def __init__(self, mode="auto", document=None, trust=False):
        self.mode = mode           # auto, attach, headless
        self.document = document
        self.trust = trust
        self.backend = None
        self.version = VERSIONS[-1]
        self._tools = None

    def close(self):
        if self.backend is not None:
            self.backend.close()
            self.backend = None

    # ---- the backend
    def _backend(self):
        if self.backend is not None:
            return self.backend
        found = connection.find() if self.mode != "headless" else None
        if found is not None:
            self.backend = Attached(found)
        elif self.mode == "attach":
            raise RemoteError(INVALID_PARAMS, "no guiqula runs with remote control on: open "
                                              "one with guiqula --remote, or call connect")
        else:
            self.backend = Headless(self.document, self.trust)
        return self.backend

    def _call(self, method, **params):
        backend = self._backend()
        try:
            return backend.call(method, **params)
        except (ConnectionError, OSError) as error:
            self.close()
            raise RemoteError(INTERNAL, f"lost {backend.describe()} ({error}); call connect "
                                        f"or try again") from None

    def connect(self, target=None, pid=None, launch=False, document=None):
        running = [{k: v for k, v in item.items() if k != "token"}
                   for item in connection.instances()]
        if target is None:
            return {"connected": self.backend.describe() if self.backend else None,
                    "running": running}
        if target == "headless":
            self.close()
            self.backend = Headless(document or self.document, self.trust)
            return {"connected": self.backend.describe()}
        found = connection.find(pid)
        if found is None and launch:
            found = self._launch(document)
        if found is None:
            raise RemoteError(INVALID_PARAMS, "no guiqula runs with remote control on" +
                              ("" if launch else "; launch: true opens one"))
        self.close()
        self.backend = Attached(found)
        return {"connected": self.backend.describe(), "running": running}

    def _launch(self, document):
        command = [sys.executable, "-m", "guiqula", "--remote"] + ([document] if document else [])
        options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                   "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            options["creationflags"] = subprocess.DETACHED_PROCESS | \
                subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        process = subprocess.Popen(command, **options)
        deadline = time.monotonic() + LAUNCH_PATIENCE
        while time.monotonic() < deadline:
            found = connection.find(process.pid)
            if found is not None:
                return found
            if process.poll() is not None:
                raise RemoteError(INTERNAL, f"the window exited with code {process.returncode}")
            time.sleep(0.2)
        raise RemoteError(INTERNAL, "the window did not turn remote control on in time")

    # ---- the tools
    def tool_list(self):
        if self._tools is None:
            listed = []
            for name, description, schema, read_only in tools():
                item = {"name": name, "description": description, "inputSchema": schema}
                if self.version >= "2025-03-26":
                    item["annotations"] = {"readOnlyHint": read_only}
                listed.append(item)
            self._tools = listed
        return self._tools

    def call_tool(self, name, arguments):
        handler = getattr(self, "tool_" + name, None)
        if handler is None:
            raise RemoteError(INVALID_PARAMS, f"unknown tool {name!r}")
        try:
            content = handler(**(arguments or {}))
        except Exception as error:          # the model reads what went wrong
            code, text, data = error_of(name, error)
            if code == INTERNAL and data:
                text += "\n" + str(data)[-2000:]
            return _error_content(text)
        return {"content": content, "isError": False}

    def tool_status(self):
        value = self._call("status")
        return [_text(f"connected to {self.backend.describe()}\n" + _json(value))]

    def tool_document(self):
        return [_text(_json(self._call("document")))]

    def tool_commands(self):
        return [_text(_json(self._call("commands")))]

    def tool_catalogue(self, family=None, system_kind=None, search=None):
        return [_text(_json(self._call("catalogue", family=family, system_kind=system_kind,
                                       search=search)))]

    def tool_command(self, name, args=None):
        return [_text(_json(self._call("do", command=name, args=args or {})))]

    def tool_run_calculation(self, calculation, timeout=300, cores=1):
        return [_text(_json(self._call("run", calculation=calculation, timeout=timeout,
                                       cores=cores)))]

    def tool_wait(self, calculation, timeout=300):
        return [_text(_json(self._call("wait", calculation=calculation, timeout=timeout)))]

    def tool_result(self, calculation, arrays=None, max_values=2000):
        return [_text(_json(self._call("result", calculation=calculation, arrays=arrays,
                                       max_values=max_values)))]

    def tool_plot(self, calculation):
        value = self._call("plot", calculation=calculation)
        return [_image(value["png"]), _text(f"figure of {calculation}")]

    def tool_screenshot(self, widget=None):
        value = self._call("screenshot", widget=widget)
        return [_image(value["png"]), _text(f"{value['widget']}, {value['size'][0]} x "
                                            f"{value['size'][1]} pixels")]

    def tool_widgets(self):
        return [_text("\n".join(self._call("widgets")))]

    def tool_help(self, item=None, kind=None, family=None, guide=None, anchor=None):
        value = self._call("help", item=item, kind=kind, family=family, guide=guide,
                           anchor=anchor)
        return [_text(value["markdown"])]

    def tool_script(self, calculation):
        return [_text(self._call("script", calculation=calculation))]

    def tool_console(self, code, system=None, timeout=120):
        value = self._call("console", code=code, system=system, timeout=timeout)
        parts = list(value.get("output") or [])
        if value.get("value") is not None:
            parts.append(repr(value["value"]) if not isinstance(value["value"], str)
                         else value["value"])
        if value.get("error"):
            return _error_content("\n".join(parts + [value["error"]]))
        return [_text("\n".join(parts) or f"({value['status']}, no output)")]

    def tool_connect(self, target=None, pid=None, launch=False, document=None):
        return [_text(_json(self.connect(target, pid, launch, document)))]

    # ---- the protocol
    def handle(self, message):
        """The reply to one message (None for a notification or a response)."""
        if not isinstance(message, dict) or "method" not in message:
            return None if isinstance(message, dict) else _error(None, INVALID_REQUEST,
                                                                 "not a request")
        rid, method = message.get("id"), message["method"]
        params = message.get("params") or {}
        if rid is None:                  # notifications: initialized, cancelled...
            return None
        try:
            if method == "initialize":
                asked = params.get("protocolVersion")
                self.version = asked if asked in VERSIONS else VERSIONS[-1]
                self._tools = None
                result = {"protocolVersion": self.version,
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "guiqula", "version": guiqula.__version__},
                          "instructions": INSTRUCTIONS}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tool_list()}
            elif method == "tools/call":
                result = self.call_tool(params.get("name"), params.get("arguments"))
            else:
                return _error(rid, NO_METHOD, f"method not found: {method}")
        except RemoteError as error:
            return _error(rid, error.code, error.message)
        except Exception as error:
            return _error(rid, INTERNAL, f"{type(error).__name__}: {error}")
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def serve(self, reader, writer):
        """Answer the messages of reader (lines of bytes) on writer until EOF."""
        for line in reader:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                reply = _error(None, PARSE_ERROR, "not JSON")
            else:
                reply = self.handle(message)
            if reply is not None:
                writer.write(json.dumps(reply).encode() + b"\n")
                writer.flush()


def _json(value):
    return json.dumps(value, indent=1, ensure_ascii=False)


def _text(text):
    return {"type": "text", "text": text}


def _image(data):
    return {"type": "image", "data": data, "mimeType": "image/png"}


def _error_content(text):
    return {"content": [_text(text)], "isError": True}


def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="guiqula mcp", description=__doc__.split("\n\n")[0])
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--attach", action="store_true",
                        help="only drive a running guiqula, never a session of its own")
    choice.add_argument("--headless", action="store_true",
                        help="always run a session of its own, without a window")
    parser.add_argument("--document", help="preset or file its own session opens")
    parser.add_argument("--trust", action="store_true",
                        help="let its own session run the document's Python nodes")
    args = parser.parse_args(argv)
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "wb")
    sys.stdout.flush()
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())      # prints go to stderr, children's too
    sys.stdout = sys.stderr
    bridge = Bridge("attach" if args.attach else "headless" if args.headless else "auto",
                    args.document, args.trust)
    try:
        bridge.serve(sys.stdin.buffer, protocol)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
    return 0

