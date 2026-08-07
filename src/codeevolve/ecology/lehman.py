"""Lehman law proxy scores from commit metrics."""

from __future__ import annotations

import math
from collections import defaultdict
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
    self_regulation: float
    organisational_stability: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "continuing_change": self.continuing_change,
            "increasing_complexity": self.increasing_complexity,
            "continuing_growth": self.continuing_growth,
            "declining_quality": self.declining_quality,
            "conservation_of_familiarity": self.conservation_of_familiarity,
            "feedback_volatility": self.feedback_volatility,
            "self_regulation": self.self_regulation,
            "organisational_stability": self.organisational_stability,
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

    # Self-regulation / organisational stability: work-rate invariance across windows
    windows = 6
    chunk = max(1, n // windows)
    rates: list[float] = []
    for i in range(windows):
        part = ordered[i * chunk : (i + 1) * chunk] if i < windows - 1 else ordered[i * chunk :]
        if part:
            rates.append(float(len(part)))
    if len(rates) >= 2:
        mean = sum(rates) / len(rates)
        var = sum((r - mean) ** 2 for r in rates) / len(rates)
        cv = math.sqrt(var) / (mean + 1e-9)
        # high self-regulation = low coefficient of variation
        self_reg = max(0.0, min(1.0, 1.0 - cv))
    else:
        self_reg = 0.5

    # Author share entropy as organisational stability proxy
    authors: dict[str, int] = defaultdict(int)
    for c in commits:
        authors[c.author] += 1
    total = sum(authors.values()) or 1
    ent = 0.0
    for v in authors.values():
        p = v / total
        ent -= p * math.log(p + 1e-12, 2)
    max_ent = math.log(max(2, len(authors)), 2)
    org_stab = min(1.0, ent / max_ent) if max_ent else 0.5

    return LehmanScores(
        continuing_change=round(continuing, 4),
        increasing_complexity=round(complexity, 4),
        continuing_growth=round(growth, 4),
        declining_quality=round(quality_decline, 4),
        conservation_of_familiarity=round(familiarity, 4),
        feedback_volatility=round(feedback, 4),
        self_regulation=round(self_reg, 4),
        organisational_stability=round(org_stab, 4),
    )
