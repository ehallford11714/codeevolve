"""CodeEvolve MCP server (stdio) for Cursor and other MCP hosts.

Protocol: JSON-RPC with Content-Length framing (MCP standard).
Also accepts bare JSON lines for simple tests.

  python -m codeevolve.mcp
  python -m codeevolve.mcp --jsonl   # line-oriented legacy mode
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from codeevolve import __version__
from codeevolve.mcp.protocol import run_mcp_loop
from codeevolve.provenance.schema import MCP_TOOLS, dispatch_mcp_tool, schemas


def handle_jsonl(message: dict[str, Any]) -> dict[str, Any]:
    """Legacy one-line JSON protocol used by unit tests."""
    method = message.get("method") or message.get("action")
    if method in {"tools/list", "list_tools", "schemas"}:
        return {"tools": MCP_TOOLS, "schemas": schemas()}
    if method in {"tools/call", "call"}:
        name = message.get("name") or (message.get("params") or {}).get("name")
        args = message.get("arguments") or (message.get("params") or {}).get("arguments") or {}
        if not name:
            return {"error": "tool name required"}
        return {"result": dispatch_mcp_tool(str(name), dict(args))}
    return {"error": f"unknown method: {method}", "methods": ["tools/list", "tools/call"]}


# Back-compat for tests / callers that imported `handle`
handle = handle_jsonl


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CodeEvolve MCP server")
    p.add_argument(
        "--jsonl",
        action="store_true",
        help="Use newline JSON protocol instead of Content-Length MCP framing",
    )
    args = p.parse_args(argv)

    if args.jsonl:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as exc:
                print(json.dumps({"error": f"invalid json: {exc}"}), flush=True)
                continue
            print(json.dumps(handle_jsonl(msg), default=str), flush=True)
        return 0

    return run_mcp_loop(
        server_name="codeevolve",
        server_version=__version__,
        list_tools=lambda: MCP_TOOLS,
        call_tool=dispatch_mcp_tool,
    )


if __name__ == "__main__":
    raise SystemExit(main())
