"""CodeEvolve-native tools: morphemes + provenance hints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codeevolve.agent.morpheme import morphemes_from_repo
from codeevolve.agent.tools.registry import ToolResult


def morpheme_scan(root: Path, paths: list[str] | None = None) -> ToolResult:
    data = morphemes_from_repo(root, paths=paths)
    return ToolResult(ok=True, name="morpheme_scan", output=data, meta={"count": data.get("morpheme_count")})


def provenance_hint(root: Path, *, path: str | None = None) -> ToolResult:
    report_path = root / ".codeevolve" / "report.json"
    if not report_path.is_file():
        return ToolResult(
            ok=False,
            name="provenance_hint",
            output=None,
            error="no .codeevolve/report.json — run analyze first",
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ToolResult(ok=False, name="provenance_hint", output=None, error=str(exc))

    from codeevolve.provenance.ledger import build_provenance_ledger, query_provenance

    ledger = build_provenance_ledger(report)
    if path:
        pack = query_provenance(ledger, path_pack=path)
    else:
        pack = query_provenance(ledger, pack=True)
    frames = []
    for fr in (pack.get("frames") or [])[:8]:
        if isinstance(fr, dict):
            frames.append(
                {
                    "id": fr.get("id"),
                    "claim": fr.get("claim"),
                    "stance": fr.get("stance"),
                    "falsifier": fr.get("falsifier"),
                }
            )
    return ToolResult(
        ok=True,
        name="provenance_hint",
        output={"frames": frames, "howto": pack.get("howto"), "path": path},
        meta={"frame_count": len(frames)},
    )


def _load_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def graph_search(
    root: Path,
    *,
    query: str = "",
    flow: bool = False,
    kernel: str | None = None,
    limit: int = 12,
    family: str | None = None,
    pivot: str | None = None,
    precedent: bool | str = False,
    traverse: str = "wave",
    depth: int = 2,
    surface: bool = False,
    previous: str | dict[str, Any] | None = None,
    delta: bool = False,
) -> ToolResult:
    report = None
    report_path = root / ".codeevolve" / "report.json"
    if report_path.is_file():
        report = _load_json_dict(report_path)
        if report is None:
            return ToolResult(ok=False, name="graph_search", output=None, error="unreadable report.json")
    prev_report: dict[str, Any] | None = None
    if isinstance(previous, dict):
        prev_report = previous
    elif previous:
        prev_path = Path(str(previous))
        if not prev_path.is_file():
            prev_path = root / str(previous)
        if prev_path.is_file():
            prev_report = _load_json_dict(prev_path)
    agent_dir = root / ".codeevolve" / "agent"
    from codeevolve.graph import query_context

    payload = query_context(
        report=report,
        agent_dir=agent_dir if agent_dir.is_dir() else None,
        search=query or None,
        flow=flow or bool(kernel),
        kernel=kernel,
        family=family,
        pivot=pivot,
        precedent=precedent,
        surface=surface,
        previous=prev_report,
        delta=bool(delta) or prev_report is not None,
        traverse=traverse,
        depth=depth,
        limit=limit,
    )
    if payload.get("node_count") == 0:
        return ToolResult(
            ok=False,
            name="graph_search",
            output=payload,
            error="empty graph — run analyze and/or agent first",
        )
    return ToolResult(
        ok=True,
        name="graph_search",
        output=payload,
        meta={"nodes": payload.get("node_count"), "hits": len(payload.get("hits") or [])},
    )

