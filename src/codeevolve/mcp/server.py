"""Minimal stdio MCP-style tool server for provenance packs.

Not a full MCP SDK server — exposes list/call over JSON lines for agents/tests:
  {"method":"tools/list"}
  {"method":"tools/call","name":"provenance_pack","arguments":{...}}
"""

from __future__ import annotations

import json
import sys
from typing import Any

from codeevolve.provenance.schema import MCP_TOOLS, dispatch_mcp_tool, schemas


def handle(message: dict[str, Any]) -> dict[str, Any]:
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


def main(argv: list[str] | None = None) -> int:
    _ = argv
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"invalid json: {exc}"}), flush=True)
            continue
        print(json.dumps(handle(msg), default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
