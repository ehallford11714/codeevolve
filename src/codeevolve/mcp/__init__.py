"""MCP stdio server + tool surface for provenance deliberation.

Run: ``python -m codeevolve.mcp`` (or ``codeevolve-mcp``).
"""

from codeevolve.provenance.schema import MCP_TOOLS, dispatch_mcp_tool, schemas, write_schemas

__all__ = ["MCP_TOOLS", "dispatch_mcp_tool", "schemas", "write_schemas"]
