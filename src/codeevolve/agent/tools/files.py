"""File read / list tools."""

from __future__ import annotations

from pathlib import Path

from codeevolve.agent.tools.registry import ToolResult


def _safe(root: Path, rel: str) -> Path:
    full = (root / rel.replace("\\", "/").lstrip("./")).resolve()
    if root.resolve() not in full.parents and full != root.resolve():
        raise ValueError(f"path escapes repo: {rel}")
    return full


def file_read(root: Path, path: str, *, max_chars: int = 12000) -> ToolResult:
    try:
        full = _safe(root, path)
        if not full.is_file():
            return ToolResult(ok=False, name="file_read", output=None, error=f"not a file: {path}")
        text = full.read_text(encoding="utf-8", errors="replace")
        return ToolResult(
            ok=True,
            name="file_read",
            output=text[:max_chars],
            meta={"path": path, "chars": len(text), "truncated": len(text) > max_chars},
        )
    except (OSError, ValueError) as exc:
        return ToolResult(ok=False, name="file_read", output=None, error=str(exc))


def file_list(root: Path, path: str = ".", *, glob: str = "*", limit: int = 80) -> ToolResult:
    try:
        base = _safe(root, path)
        if not base.exists():
            return ToolResult(ok=False, name="file_list", output=[], error=f"missing: {path}")
        rows = []
        for p in sorted(base.glob(glob)):
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                rows.append(rel)
            if len(rows) >= limit:
                break
        return ToolResult(ok=True, name="file_list", output=rows, meta={"count": len(rows)})
    except (OSError, ValueError) as exc:
        return ToolResult(ok=False, name="file_list", output=[], error=str(exc))
