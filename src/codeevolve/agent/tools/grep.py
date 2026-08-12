"""Content grep for agent reading (stdlib, no ripgrep required)."""

from __future__ import annotations

import re
from pathlib import Path

from codeevolve.agent.tools.registry import ToolResult

_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", ".codeevolve", "dist", "build"}


def grep(
    root: Path,
    pattern: str,
    *,
    path: str = ".",
    glob: str = "*",
    max_hits: int = 40,
    ignore_case: bool = True,
) -> ToolResult:
    try:
        flags = re.IGNORECASE if ignore_case else 0
        rx = re.compile(pattern, flags)
    except re.error as exc:
        return ToolResult(ok=False, name="grep", output=[], error=f"bad pattern: {exc}")

    base = (root / path).resolve()
    if root.resolve() not in base.parents and base != root.resolve():
        return ToolResult(ok=False, name="grep", output=[], error="path escapes repo")

    hits: list[dict[str, str | int]] = []
    try:
        paths = list(base.rglob(glob)) if base.is_dir() else [base]
    except OSError as exc:
        return ToolResult(ok=False, name="grep", output=[], error=str(exc))

    for fp in paths:
        if not fp.is_file():
            continue
        try:
            rel = fp.relative_to(root).as_posix()
        except ValueError:
            continue
        if any(part in _SKIP for part in rel.split("/")):
            continue
        if fp.stat().st_size > 1_500_000:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                hits.append({"path": rel, "line": i, "text": line[:300]})
                if len(hits) >= max_hits:
                    return ToolResult(
                        ok=True,
                        name="grep",
                        output=hits,
                        meta={"truncated": True, "pattern": pattern},
                    )
    return ToolResult(ok=True, name="grep", output=hits, meta={"count": len(hits), "pattern": pattern})
