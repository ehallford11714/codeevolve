"""Core evolution metrics: revert rate, stability, dependency churn, momentum."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codeevolve.gitlog import CommitRecord


DEP_FILE_RE = re.compile(
    r"(requirements.*\.txt|pyproject\.toml|setup\.py|Pipfile|poetry\.lock|"
    r"package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|"
    r"go\.mod|go\.sum|Cargo\.toml|Cargo\.lock|Gemfile|composer\.json)$",
    re.I,
)


@dataclass
class MetricBundle:
    commit_count: int = 0
    revert_count: int = 0
    revert_rate: float = 0.0
    churn_total: int = 0
    avg_churn_per_commit: float = 0.0
    code_stability: float = 0.0  # 0..1 higher = more stable
    dependency_change_commits: int = 0
    dependency_rate: float = 0.0
    file_touch_entropy: float = 0.0
    momentum: float = 0.0  # recent vs older activity
    improvement_trend: float = 0.0  # negative churn slope-ish / fewer reverts recently
    hot_files: list[dict[str, Any]] = field(default_factory=list)
    authors: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit_count": self.commit_count,
            "revert_count": self.revert_count,
            "revert_rate": self.revert_rate,
            "churn_total": self.churn_total,
            "avg_churn_per_commit": self.avg_churn_per_commit,
            "code_stability": self.code_stability,
            "dependency_change_commits": self.dependency_change_commits,
            "dependency_rate": self.dependency_rate,
            "file_touch_entropy": self.file_touch_entropy,
            "momentum": self.momentum,
            "improvement_trend": self.improvement_trend,
            "hot_files": list(self.hot_files),
            "authors": dict(self.authors),
        }


def _entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log(p + 1e-12, 2)
    return h


def compute_metrics(commits: list[CommitRecord]) -> MetricBundle:
    """Compute MVP metrics from commit records (newest-first OK)."""
    n = len(commits)
    if n == 0:
        return MetricBundle()

    reverts = sum(1 for c in commits if c.is_revert)
    churn = sum(c.insertions + c.deletions for c in commits)
    file_counts: dict[str, int] = defaultdict(int)
    authors: dict[str, int] = defaultdict(int)
    dep_commits = 0
    for c in commits:
        authors[c.author] += 1
        touched_dep = False
        for f in c.files:
            file_counts[f] += 1
            if DEP_FILE_RE.search(f):
                touched_dep = True
        if touched_dep:
            dep_commits += 1

    # Stability: inverse of churn intensity and revert pressure and hot-file concentration
    avg_churn = churn / n
    revert_rate = reverts / n
    top_touch = max(file_counts.values()) if file_counts else 0
    concentration = (top_touch / n) if n else 0.0
    # map to 0..1
    stability = 1.0 / (1.0 + 0.002 * avg_churn + 3.0 * revert_rate + 0.5 * concentration)
    stability = max(0.0, min(1.0, stability))

    # Momentum: compare recent third vs older two-thirds by churn rate
    chronological = list(reversed(commits))  # oldest first
    cut = max(1, n // 3)
    recent = chronological[-cut:]
    older = chronological[:-cut] or chronological[:1]
    recent_rate = sum(c.insertions + c.deletions for c in recent) / max(1, len(recent))
    older_rate = sum(c.insertions + c.deletions for c in older) / max(1, len(older))
    momentum = (recent_rate - older_rate) / (older_rate + 1.0)

    recent_reverts = sum(1 for c in recent if c.is_revert) / max(1, len(recent))
    older_reverts = sum(1 for c in older if c.is_revert) / max(1, len(older))
    # improvement: fewer reverts + lower churn recently
    improvement = (older_reverts - recent_reverts) + 0.1 * ((older_rate - recent_rate) / (older_rate + 1.0))

    hot = sorted(file_counts.items(), key=lambda x: -x[1])[:15]
    return MetricBundle(
        commit_count=n,
        revert_count=reverts,
        revert_rate=round(revert_rate, 4),
        churn_total=churn,
        avg_churn_per_commit=round(avg_churn, 2),
        code_stability=round(stability, 4),
        dependency_change_commits=dep_commits,
        dependency_rate=round(dep_commits / n, 4),
        file_touch_entropy=round(_entropy(list(file_counts.values())), 4),
        momentum=round(momentum, 4),
        improvement_trend=round(improvement, 4),
        hot_files=[{"path": p, "touches": t} for p, t in hot],
        authors=dict(authors),
    )


def change_rate_timeline(commits: list[CommitRecord], *, buckets: int = 12) -> list[dict[str, Any]]:
    """Bucket churn over time for rate-of-change charts."""
    if not commits:
        return []
    chronological = sorted(commits, key=lambda c: c.timestamp)
    t0 = chronological[0].timestamp
    t1 = chronological[-1].timestamp
    span = max((t1 - t0).total_seconds(), 1.0)
    width = span / buckets
    bins = [0] * buckets
    counts = [0] * buckets
    for c in chronological:
        idx = int((c.timestamp - t0).total_seconds() / width)
        idx = min(buckets - 1, max(0, idx))
        bins[idx] += c.insertions + c.deletions
        counts[idx] += 1
    out = []
    for i in range(buckets):
        start = datetime.fromtimestamp(t0.timestamp() + i * width, tz=timezone.utc)
        out.append(
            {
                "bucket": i,
                "start": start.isoformat(),
                "commits": counts[i],
                "churn": bins[i],
                "rate": round(bins[i] / max(1, counts[i]), 2),
            }
        )
    return out
