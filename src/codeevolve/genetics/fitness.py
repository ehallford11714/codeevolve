"""Module / file fitness scores from churn and revert pressure."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from codeevolve.gitlog import CommitRecord


def file_fitness_map(commits: list[CommitRecord]) -> dict[str, dict[str, Any]]:
    ordered = sorted(commits, key=lambda c: c.timestamp)
    counts: dict[str, int] = defaultdict(int)
    reverts: dict[str, int] = defaultdict(int)
    churn: dict[str, int] = defaultdict(int)
    for c in ordered:
        share = (c.insertions + c.deletions) / max(1, len(c.files))
        for f in c.files:
            counts[f] += 1
            churn[f] += int(share)
            if c.is_revert:
                reverts[f] += 1
    out: dict[str, dict[str, Any]] = {}
    for path, n in counts.items():
        rr = reverts[path] / max(1, n)
        fitness = 1.0 / (1.0 + 2.0 * rr + 0.001 * churn[path] / max(1, n))
        out[path] = {
            "fitness": round(fitness, 4),
            "appearances": n,
            "revert_touches": reverts[path],
            "churn": churn[path],
        }
    return out


def mean_fitness(scores: dict[str, dict[str, Any]]) -> float:
    if not scores:
        return 0.0
    return round(sum(v["fitness"] for v in scores.values()) / len(scores), 4)
