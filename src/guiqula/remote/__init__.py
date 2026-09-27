"""Remote control of a running guiqula, the Claude add-on (PLAN.md 3.7).

- ``api.py``: the methods a remote client calls, over a Session (and the
  window, when there is one): the outline of the document, the registry's
  catalogue, any command, runs, results, figures, screenshots, help;
- ``server.py``: a JSON-RPC 2.0 server on a localhost socket, protected by
  a token, polled from the host's loop (the window's timer, or ``guiqula
  serve``), so the Session is only ever touched from one thread;
- ``connection.py``: the files that tell a client where a server listens;
- ``client.py``: the blocking client of that server;
- ``mcp.py``: ``guiqula mcp``, a stdio MCP server whose tools call the API
  of a running window (or of its own headless Session), which Claude Code
  talks to;
- ``window.py``: what the API asks of the window (screenshots, its state).

Qt is allowed here (only window.py and the figure of ``plot`` use it),
pyqula is not: this runs in the UI process.
"""
