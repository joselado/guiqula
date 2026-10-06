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
from pathlib import Path

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
class Lost(ConnectionError):
    """The connection to a running guiqula broke (not a command's own error,
    which is an OSError as well when it is a file that cannot be written)."""


class Attached:
    def __init__(self, found):
        from guiqula.remote.client import Client
        self.found = found
        self.client = Client(found["port"], found["token"])

    def call(self, method, **params):
        try:
            return self.client.call(method, **params)
        except OSError as error:            # ConnectionError, a socket timeout
            raise Lost(str(error)) from None

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
                      max_values={"type": "integer", "minimum": 1}), ("calculation",)), True),
        ("plot", "The figure of a result, as the result view draws it; a stale, running or "
                 "failed one says so in its title and in the text beside it.",
         _schema(CALC, ("calculation",)), True),
        ("screenshot", "A screenshot of the window, or of one of its widgets by name "
                       "(structureView: the canvas; plot_c1: a result view; outliner; "
                       "helpDock...; widgets lists them). Needs a window.",
         _schema({"widget": {"type": "string"}}), True),
        ("widgets", "The names of the window's widgets a screenshot takes (a folded card of "
                    "the start page is listed once Show all or a search has made it).",
         _schema(), True),
        ("help", "Help as Markdown: of a document item (item: t1, c1, s1/base...), of a "
                 "registry entry (kind, with family if ambiguous), or of a section of a "
                 'guide (guide: "pyqula" or "guiqula", anchor: a heading); a guide alone '
                 'gives its contents; guide "plugins" lists the installed plugins; search '
                 "(a question in words) lists the entries and guide sections that answer "
                 "it, best first, each with the arguments that show it in full.",
         _schema({"item": {"type": "string"}, "kind": {"type": "string"},
                  "family": {"type": "string"}, "guide": {"type": "string", "enum": [
                      "pyqula", "guiqula", "plugins"]},
                  "anchor": {"type": "string"}, "search": {"type": "string"},
                  "limit": {"type": "integer", "minimum": 1}}), True),
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
        self.launched = []         # the windows it opened, reaped when they end

    def close(self):
        if self.backend is not None:
            self.backend.close()
            self.backend = None

    # ---- the backend
    def _reap(self):
        """Forget the windows it opened that have ended: poll() reaps them (the
        pid of a zombie looks alive, so its connection file would be kept)."""
        self.launched = [process for process in self.launched if process.poll() is None]

    def _find(self, pid=None):
        """The newest running guiqula (or the one of process pid) that
        answers, attached; None if none. The connection file of a server
        that no longer listens (a window that crashed) is deleted: it would
        be found again at every call."""
        self._reap()
        while (found := connection.find(pid)) is not None:
            try:
                return Attached(found)
            except ConnectionRefusedError:
                Path(found["file"]).unlink(missing_ok=True)
        return None

    def _backend(self):
        if self.backend is not None:
            return self.backend
        attached = self._find() if self.mode != "headless" else None
        if attached is not None:
            self.backend = attached
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
        except Lost as error:            # a command's own OSError (a save) keeps the session
            self.close()
            raise RemoteError(INTERNAL, f"lost {backend.describe()} ({error}); call connect "
                                        f"or try again") from None

    def connect(self, target=None, pid=None, launch=False, document=None):
        self._reap()
        running = [{k: v for k, v in item.items() if k != "token"}
                   for item in connection.instances()]
        if target is None:
            return {"connected": self.backend.describe() if self.backend else None,
                    "running": running}
        if target == "headless":         # the new session first: a wrong name keeps the old
            backend = Headless(document or self.document, self.trust)
            self.close()
            self.backend = backend
            return {"connected": self.backend.describe()}
        backend = self._find(pid)
        if backend is None and launch:
            backend = Attached(self._launch(document))
        if backend is None:
            raise RemoteError(INVALID_PARAMS, "no guiqula runs with remote control on" +
                              ("" if launch else "; launch: true opens one"))
        self.close()
        self.backend = backend
        return {"connected": self.backend.describe(), "running": running}

    def _launch(self, document):
        from guiqula import env
        command = env.launcher() + ["--remote"] + ([document] if document else [])
        options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                   "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            options["creationflags"] = subprocess.DETACHED_PROCESS | \
                subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        process = subprocess.Popen(command, **options)
        self.launched.append(process)
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
        if isinstance(content, dict):           # a tool's own error result (the console's)
            return content
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
        state = PLOT_STATES.get(value.get("state"), "")
        return [_image(value["png"]), _text(f"figure of {calculation}"
                                            + (f", {state}" if state else ""))]

    def tool_screenshot(self, widget=None):
        value = self._call("screenshot", widget=widget)
        return [_image(value["png"]), _text(f"{value['widget']}, {value['size'][0]} x "
                                            f"{value['size'][1]} pixels")]

    def tool_widgets(self):
        return [_text("\n".join(self._call("widgets")))]

    def tool_help(self, item=None, kind=None, family=None, guide=None, anchor=None,
                  search=None, limit=None):
        value = self._call("help", item=item, kind=kind, family=family, guide=guide,
                           anchor=anchor, search=search, limit=limit)
        if search is None:
            return [_text(value["markdown"])]
        lines = []
        for hit in value["hits"]:
            show = (f"kind={hit['kind']!r}, family={hit['family']!r}" if "kind" in hit else
                    f"guide={hit['guide']!r}, anchor={hit['anchor']!r}")
            lines.append(f"- {hit['title']} ({hit['where']}): help({show})"
                         + (f"\n  {hit['snippet']}" if hit["snippet"] else ""))
        return [_text("\n".join(lines) or f"nothing in the help matches {search!r}")]

    def tool_script(self, calculation):
        return [_text(self._call("script", calculation=calculation))]

    def tool_console(self, code, system=None, timeout=120):
        value = self._call("console", code=code, system=system, timeout=timeout)
        output = "\n".join(value.get("output") or [])
        if value.get("error"):                   # the traceback is in the output already
            return _error_content(output or value["error"])
        return [_text(output or f"({value['status']}, no output)")]

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
        """Answer the messages of reader (lines of bytes) on writer until EOF.
        A message that fails is answered with an error, never the end of
        the bridge (and of its own session, with every edit in it)."""
        for line in reader:
            if not line.strip():
                continue
            rid = None
            try:
                try:
                    message = json.loads(line)
                except (ValueError, RecursionError):     # RecursionError: nested too deeply
                    reply = _error(None, PARSE_ERROR, "not JSON")
                else:
                    if isinstance(message, dict) and isinstance(message.get("id"), (int, str)):
                        rid = message["id"]
                    reply = self.handle(message)
                data = None if reply is None else json.dumps(reply)
            except Exception as error:
                data = json.dumps(_error(rid, INTERNAL, f"{type(error).__name__}: {error}"))
            if data is not None:
                writer.write(data.encode() + b"\n")
                writer.flush()


def _json(value):
    return json.dumps(value, indent=1, ensure_ascii=False)


# what the text beside a plot's image says of a result that is not simply current
# (its title carries the mark too, remote/api.py's plot_title)
PLOT_STATES = {"stale": "stale: the model changed since it was computed",
               "failed": "its last run failed: the figure is of the result before it",
               "queued": "a new run of it is queued", "running": "a new run of it is running"}


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

