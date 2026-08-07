"""Blast-radius scoring from co-change graphs."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from codeevolve.gitlog import CommitRecord


def cochange_degrees(commits: list[CommitRecord]) -> dict[str, int]:
    neighbors: dict[str, set[str]] = defaultdict(set)
    for c in commits:
        files = c.files[:50]
        for a in files:
            for b in files:
                if a != b:
                    neighbors[a].add(b)
    return {p: len(n) for p, n in neighbors.items()}


def blast_radius_table(commits: list[CommitRecord], *, top: int = 20) -> list[dict[str, Any]]:
    deg = cochange_degrees(commits)
    return [
        {"path": p, "co_changers": d, "blast_score": round(min(1.0, d / 40.0), 4)}
        for p, d in sorted(deg.items(), key=lambda x: -x[1])[:top]
    ]
