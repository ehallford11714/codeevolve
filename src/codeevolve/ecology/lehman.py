"""Lehman law proxy scores from commit metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import MetricBundle


@dataclass
class LehmanScores:
    continuing_change: float
    increasing_complexity: float
    continuing_growth: float
    declining_quality: float
    conservation_of_familiarity: float
    feedback_volatility: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "continuing_change": self.continuing_change,
            "increasing_complexity": self.increasing_complexity,
            "continuing_growth": self.continuing_growth,
            "declining_quality": self.declining_quality,
            "conservation_of_familiarity": self.conservation_of_familiarity,
            "feedback_volatility": self.feedback_volatility,
        }


def compute_lehman(commits: list[CommitRecord], metrics: MetricBundle) -> LehmanScores:
    n = max(1, len(commits))
    ordered = sorted(commits, key=lambda c: c.timestamp)
    mid = max(1, n // 2)
    early, late = ordered[:mid], ordered[mid:]
    early_files = {f for c in early for f in c.files}
    late_files = {f for c in late for f in c.files}
    growth = len(late_files - early_files) / max(1, len(early_files | late_files))
    complexity = min(1.0, metrics.file_touch_entropy / 6.0)
    quality_decline = min(1.0, metrics.revert_rate * 2.5 + (1.0 - metrics.code_stability) * 0.5)
    familiarity = 1.0 - min(1.0, growth)
    feedback = min(1.0, abs(metrics.momentum) / 2.0)
    continuing = min(1.0, metrics.avg_churn_per_commit / 200.0)
    return LehmanScores(
        continuing_change=round(continuing, 4),
        increasing_complexity=round(complexity, 4),
        continuing_growth=round(growth, 4),
        declining_quality=round(quality_decline, 4),
        conservation_of_familiarity=round(familiarity, 4),
        feedback_volatility=round(feedback, 4),
    )
