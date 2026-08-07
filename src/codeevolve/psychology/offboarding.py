"""Offboarding / knowledge-loss simulation (bus-factor stress test)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import MetricBundle


@dataclass
class OffboardingReport:
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    top_authors: list[dict[str, Any]] = field(default_factory=list)
    mastery_drop_top1: float = 0.0
    mastery_drop_top3: float = 0.0
    uncovered_hotspots: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarios": list(self.scenarios),
            "top_authors": list(self.top_authors[:10]),
            "mastery_drop_top1": self.mastery_drop_top1,
            "mastery_drop_top3": self.mastery_drop_top3,
            "uncovered_hotspots": list(self.uncovered_hotspots[:20]),
            "summary": self.summary,
        }


def simulate_offboarding(
    commits: list[CommitRecord],
    metrics: MetricBundle,
    *,
    remove_ns: tuple[int, ...] = (1, 2, 3),
) -> OffboardingReport:
    """Simulate removing top-N authors by commit share; measure mastery drop."""
    if not commits:
        return OffboardingReport(summary="No commits")

    authors_by_file: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    author_commits: dict[str, int] = defaultdict(int)
    for c in commits:
        author_commits[c.author] += 1
        for f in c.files:
            authors_by_file[f][c.author] += 1

    ranked = sorted(author_commits.items(), key=lambda x: -x[1])
    top_authors = [{"author": a, "commits": n, "share": round(n / len(commits), 4)} for a, n in ranked[:10]]

    hot = {h["path"] for h in metrics.hot_files[:15]}
    # Baseline mastery: sum of touches on hot files
    baseline = 0.0
    for path in hot:
        baseline += sum(authors_by_file.get(path, {}).values())
    baseline = max(1.0, baseline)

    scenarios: list[dict[str, Any]] = []
    drop_top1 = drop_top3 = 0.0
    uncovered: list[str] = []

    for n_rem in remove_ns:
        gone = {a for a, _ in ranked[:n_rem]}
        remaining = 0.0
        lost_paths = []
        for path in hot:
            contrib = authors_by_file.get(path, {})
            rem = sum(v for a, v in contrib.items() if a not in gone)
            remaining += rem
            if rem == 0 and contrib:
                lost_paths.append(path)
        drop = 1.0 - (remaining / baseline)
        scenarios.append(
            {
                "remove_top_n": n_rem,
                "removed": [a for a, _ in ranked[:n_rem]],
                "mastery_drop": round(drop, 4),
                "uncovered_hotspots": lost_paths[:15],
            }
        )
        if n_rem == 1:
            drop_top1 = drop
            uncovered = lost_paths
        if n_rem == 3:
            drop_top3 = drop

    return OffboardingReport(
        scenarios=scenarios,
        top_authors=top_authors,
        mastery_drop_top1=round(drop_top1, 4),
        mastery_drop_top3=round(drop_top3, 4),
        uncovered_hotspots=uncovered,
        summary=(
            f"Top-1 offboarding mastery drop {drop_top1:.0%}; "
            f"top-3 {drop_top3:.0%}; {len(uncovered)} hotspots fully uncovered"
        ),
    )
