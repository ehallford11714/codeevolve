"""Memory tools wrappers."""

from __future__ import annotations

from typing import Any

from codeevolve.agent.tools.registry import ToolResult


def memory_search(memory: Any, query: str, *, limit: int = 12) -> ToolResult:
    if memory is None:
        return ToolResult(ok=False, name="memory_search", output=[], error="memory not configured")
    rows = memory.search(query, limit=limit)
    return ToolResult(ok=True, name="memory_search", output=[r.to_dict() for r in rows])


def memory_add(
    memory: Any,
    content: str,
    *,
    kind: str = "working",
    tags: list[str] | None = None,
) -> ToolResult:
    if memory is None:
        return ToolResult(ok=False, name="memory_add", output=None, error="memory not configured")
    item = memory.add(content, kind=kind, tags=tags or [])  # type: ignore[arg-type]
    memory.save()
    return ToolResult(ok=True, name="memory_add", output=item.to_dict())
