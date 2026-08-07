"""Diff-aware comparison against a previous EvolveReport JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReportDiff:
    improved: list[str] = field(default_factory=list)
    worsened: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    deltas: dict[str, Any] = field(default_factory=dict)
    markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "improved": list(self.improved),
            "worsened": list(self.worsened),
            "unchanged": list(self.unchanged),
            "deltas": dict(self.deltas),
            "markdown": self.markdown,
        }


def _get(d: dict[str, Any], *path: str, default: float = 0.0) -> float:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def diff_reports(current: dict[str, Any], previous: dict[str, Any]) -> ReportDiff:
    metrics = [
        ("stability.composite", ("stability", "composite"), True),
        ("metrics.code_stability", ("metrics", "code_stability"), True),
        ("metrics.revert_rate", ("metrics", "revert_rate"), False),
        ("debt.score", ("debt", "score"), False),
        ("fatigue.fatigue_score", ("fatigue", "fatigue_score"), False),
        ("cognitive_load.load_index", ("cognitive_load", "load_index"), False),
        ("drift.global_drift", ("drift", "global_drift"), False),
        ("risk.count", ("risk", "count"), False),
    ]
    # risk.count may be missing — use failure_points len
    improved: list[str] = []
    worsened: list[str] = []
    unchanged: list[str] = []
    deltas: dict[str, Any] = {}

    for label, path, higher_better in metrics:
        if label == "risk.count":
            cur = float(len((current.get("risk") or {}).get("failure_points") or []))
            prev = float(len((previous.get("risk") or {}).get("failure_points") or []))
        else:
            cur = _get(current, *path)
            prev = _get(previous, *path)
        delta = cur - prev
        deltas[label] = {"previous": prev, "current": cur, "delta": round(delta, 4)}
        if abs(delta) < 1e-4:
            unchanged.append(label)
        elif (delta > 0 and higher_better) or (delta < 0 and not higher_better):
            improved.append(f"{label} {delta:+.4f}")
        else:
            worsened.append(f"{label} {delta:+.4f}")

    md = ["# CodeEvolve Diff Report", "", "## Improved"]
    md.extend([f"- {x}" for x in improved] or ["- None"])
    md += ["", "## Worsened"]
    md.extend([f"- {x}" for x in worsened] or ["- None"])
    md += ["", "## Unchanged"]
    md.extend([f"- {x}" for x in unchanged] or ["- None"])
    md.append("")
    return ReportDiff(
        improved=improved,
        worsened=worsened,
        unchanged=unchanged,
        deltas=deltas,
        markdown="\n".join(md),
    )


def load_previous(path: Path | str) -> dict[str, Any] | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
