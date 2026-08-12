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
