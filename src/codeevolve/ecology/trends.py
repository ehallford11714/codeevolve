"""Lehman trend tests (pure-Python Mann–Kendall + Sen slope)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import MetricBundle


@dataclass
class TrendTest:
    series: str
    n: int
    tau: float
    s_stat: int
    sen_slope: float
    trend: str  # increasing | decreasing | no_trend
    p_approx: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "series": self.series,
            "n": self.n,
            "tau": self.tau,
            "s_stat": self.s_stat,
            "sen_slope": self.sen_slope,
            "trend": self.trend,
            "p_approx": self.p_approx,
        }


@dataclass
class LehmanTrendReport:
    tests: list[TrendTest] = field(default_factory=list)
    law_support: dict[str, str] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tests": [t.to_dict() for t in self.tests],
            "law_support": dict(self.law_support),
            "summary": self.summary,
        }


def mann_kendall(x: list[float]) -> TrendTest:
    """Mann–Kendall with normal approx; Sen's slope median of pairwise slopes."""
    n = len(x)
    if n < 4:
        return TrendTest("series", n, 0.0, 0, 0.0, "no_trend", 1.0)
    s = 0
    slopes: list[float] = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            d = x[j] - x[i]
            s += 1 if d > 0 else (-1 if d < 0 else 0)
            denom = j - i
            if denom:
                slopes.append(d / denom)
    # variance assuming no ties
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    # two-sided p via erfc
    p = math.erfc(abs(z) / math.sqrt(2.0))
    denom = n * (n - 1) / 2.0
    tau = s / denom if denom else 0.0
    slopes.sort()
    mid = len(slopes) // 2
    sen = slopes[mid] if slopes else 0.0
    if p < 0.05 and s > 0:
        trend = "increasing"
    elif p < 0.05 and s < 0:
        trend = "decreasing"
    else:
        trend = "no_trend"
    return TrendTest("series", n, round(tau, 4), s, round(sen, 6), trend, round(p, 4))


def _window_series(commits: list[CommitRecord], *, windows: int = 8) -> dict[str, list[float]]:
    ordered = sorted(commits, key=lambda c: c.timestamp)
    n = len(ordered)
    if n == 0:
        return {}
    chunk = max(1, n // windows)
    churn: list[float] = []
    reverts: list[float] = []
    growth: list[float] = []
    files_seen: set[str] = set()
    work: list[float] = []  # commits per window (organisational work rate)
    for i in range(windows):
        part = ordered[i * chunk : (i + 1) * chunk] if i < windows - 1 else ordered[i * chunk :]
        if not part:
            continue
        ch = sum(c.insertions + c.deletions for c in part) / max(1, len(part))
        rv = sum(1 for c in part if c.is_revert) / max(1, len(part))
        before = len(files_seen)
        for c in part:
            files_seen.update(c.files)
        gr = (len(files_seen) - before) / max(1, len(files_seen))
        churn.append(ch)
        reverts.append(rv)
        growth.append(gr)
        work.append(float(len(part)))
    return {
        "churn_rate": churn,
        "revert_rate": reverts,
        "file_growth": growth,
        "work_rate": work,
    }


def analyze_lehman_trends(commits: list[CommitRecord], metrics: MetricBundle) -> LehmanTrendReport:
    series = _window_series(commits)
    tests: list[TrendTest] = []
    for name, vals in series.items():
        t = mann_kendall(vals)
        t.series = name
        tests.append(t)

    by = {t.series: t for t in tests}
    support: dict[str, str] = {}
    # Map trends → law support / contradict (heuristic)
    if by.get("churn_rate") and by["churn_rate"].trend == "increasing":
        support["continuing_change"] = "support"
    elif by.get("churn_rate"):
        support["continuing_change"] = "weak" if by["churn_rate"].trend == "no_trend" else "contradict"

    if by.get("file_growth") and by["file_growth"].trend == "increasing":
        support["continuing_growth"] = "support"
    elif by.get("file_growth"):
        support["continuing_growth"] = "weak" if by["file_growth"].trend == "no_trend" else "contradict"

    if by.get("revert_rate") and by["revert_rate"].trend == "increasing":
        support["declining_quality"] = "support"
    elif by.get("revert_rate"):
        support["declining_quality"] = "weak" if by["revert_rate"].trend == "no_trend" else "contradict"

    # Self-regulation: work rate should be near-invariant (no strong trend)
    wr = by.get("work_rate")
    if wr:
        support["self_regulation"] = "support" if wr.trend == "no_trend" else "contradict"
        support["organisational_stability"] = support["self_regulation"]

    # Complexity proxy: churn entropy already in metrics — use churn_rate trend as proxy
    if by.get("churn_rate"):
        support["increasing_complexity"] = (
            "support" if by["churn_rate"].trend == "increasing" else "weak"
        )

    support["conservation_of_familiarity"] = (
        "support" if support.get("continuing_growth") != "support" else "contradict"
    )
    support.setdefault("feedback_system", "weak")

    # Touch metrics for unused param silence
    _ = metrics.commit_count

    topped = ", ".join(f"{k}:{v}" for k, v in list(support.items())[:5])
    return LehmanTrendReport(
        tests=tests,
        law_support=support,
        summary=(
            f"Mann–Kendall on {len(tests)} series (hypotheses, not grades); {topped}"
        ),
    )
