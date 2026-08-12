"""MCP stdio framing + tool catalog."""

from __future__ import annotations

import io
import json

from codeevolve.mcp.protocol import read_message, write_message
from codeevolve.mcp.server import handle
from codeevolve.provenance.schema import MCP_TOOLS, dispatch_mcp_tool


def test_tool_catalog_includes_analyze_repo():
    names = {t["name"] for t in MCP_TOOLS}
    assert "analyze_repo" in names
    assert "provenance_pack" in names
    assert "viz_phylogeny" in names
    listed = handle({"method": "tools/list"})
    assert {t["name"] for t in listed["tools"]} == names


def test_dispatch_missing_report_hints_analyze():
    out = dispatch_mcp_tool("provenance_pack", {})
    assert "error" in out
    assert "analyze_repo" in (out.get("hint") or out["error"])


def test_content_length_roundtrip():
    class _Out:
        def __init__(self) -> None:
            self.buffer = io.BytesIO()
            self._parts: list[str] = []

        def write(self, s: str) -> int:
            self._parts.append(s)
            return len(s)

        def flush(self) -> None:
            pass

    out = _Out()
    write_message({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}, out)  # type: ignore[arg-type]
    framed = "".join(out._parts).encode("utf-8") + out.buffer.getvalue()
    stdin = io.TextIOWrapper(io.BytesIO(framed), encoding="utf-8")
    msg = read_message(stdin)
    assert msg is not None
    assert msg["result"]["ok"] is True
