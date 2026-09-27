#!/usr/bin/env python
"""Check `guiqula mcp` with the official MCP SDK's client (PLAN.md 3.7).

guiqula writes the MCP protocol itself, without the SDK; this script runs
the SDK's own stdio client against it: the handshake (a 2026 client first
probes server/discover and falls back to initialize), the tool list, text
and image results, a refused command. Run it with any Python that has the
SDK (`pip install mcp`, 1.x or 2.x), for instance a scratch venv; the
bridge itself runs under --python (default: this interpreter) with src/ on
its path:

    python tools/mcp_check.py --python /path/to/guiqula/python
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


async def check(python):
    from mcp import StdioServerParameters
    env = dict(os.environ, PYTHONPATH=str(SRC))
    params = StdioServerParameters(command=python, env=env, args=[
        "-m", "guiqula", "mcp", "--headless", "--document", "honeycomb_zeeman_rashba"])
    report = {}
    try:
        from mcp import Client                   # the SDK 2.x
    except ImportError:
        Client = None
    if Client is not None:
        async with Client(params) as client:
            report["connected"] = type(client.server_info).__name__
            report["server"] = client.server_info.name if client.server_info else None
            report["protocol"] = client.protocol_version
            await run_checks(client, report)
    else:                                        # the SDK 1.x
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                init = await client.initialize()
                report["server"] = init.serverInfo.name
                report["protocol"] = init.protocolVersion
                await run_checks(client, report)
    return report


def kinds(result):
    return [c.type for c in result.content]


def text(result):
    return "\n".join(c.text for c in result.content if c.type == "text")


def is_error(result):
    return getattr(result, "is_error", getattr(result, "isError", None))


async def run_checks(client, report):
    listed = await client.list_tools()
    report["tools"] = [t.name for t in listed.tools]
    status = await client.call_tool("status", {})
    report["status"] = text(status).splitlines()[0]
    added = await client.call_tool("command", {"name": "add_term", "args": {
        "system": "s1", "kind": "haldane", "params": {"t": 0.05}}})
    report["add_term"] = json.loads(text(added))["result"]
    refused = await client.call_tool("command", {"name": "add_term", "args": {
        "system": "s9", "kind": "haldane"}})
    report["refused"] = [is_error(refused), text(refused)]
    run = await client.call_tool("run_calculation", {"calculation": "c1"})
    report["run"] = json.loads(text(run))["status"]
    plot = await client.call_tool("plot", {"calculation": "c1"})
    report["plot"] = kinds(plot)
    shot = await client.call_tool("screenshot", {})
    report["screenshot"] = [is_error(shot), text(shot)]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--python", default=sys.executable,
                        help="the interpreter that runs guiqula mcp (it needs guiqula's "
                             "dependencies)")
    args = parser.parse_args()
    report = asyncio.run(check(args.python))
    print(json.dumps(report, indent=1))
    ok = (report["add_term"] == "t3" and report["refused"][0] is True and report["run"] == "done"
          and report["plot"][0] == "image" and report["screenshot"][0] is True
          and "status" in report["tools"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
