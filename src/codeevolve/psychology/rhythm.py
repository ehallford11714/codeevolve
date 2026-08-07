"""Sprint intensity / fatigue trends from git timestamps."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from codeevolve.gitlog import CommitRecord


@dataclass
class FatigueReport:
    after_hours_rate: float
    weekend_rate: float
    intensity_creep: float
    recovery_ratio: float
    end_of_sprint_dump: float
    weekly: list[dict[str, Any]] = field(default_factory=list)
    fatigue_score: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "after_hours_rate": self.after_hours_rate,
            "weekend_rate": self.weekend_rate,
            "intensity_creep": self.intensity_creep,
            "recovery_ratio": self.recovery_ratio,
            "end_of_sprint_dump": self.end_of_sprint_dump,
            "fatigue_score": self.fatigue_score,
            "weekly": list(self.weekly),
            "summary": self.summary,
        }


def _week_key(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    iso = ts.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def analyze_fatigue(
    commits: list[CommitRecord],
    *,
    workday_start: int = 9,
    workday_end: int = 18,
) -> FatigueReport:
    if not commits:
        return FatigueReport(0, 0, 0, 0, 0, summary="No commits")

    after = 0
    weekend = 0
    by_week: dict[str, dict[str, float]] = defaultdict(lambda: {"commits": 0, "churn": 0})
    for c in commits:
        ts = c.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        local_hour = ts.hour
        if local_hour < workday_start or local_hour >= workday_end:
            after += 1
        if ts.weekday() >= 5:
            weekend += 1
        wk = _week_key(ts)
        by_week[wk]["commits"] += 1
        by_week[wk]["churn"] += c.insertions + c.deletions

    n = len(commits)
    after_hours_rate = after / n
    weekend_rate = weekend / n

    weeks = sorted(by_week.keys())
    weekly = [
        {
            "week": w,
            "commits": int(by_week[w]["commits"]),
            "churn": int(by_week[w]["churn"]),
            "intensity": round(by_week[w]["churn"] / max(1, by_week[w]["commits"]), 2),
        }
        for w in weeks
    ]

    # intensity creep: last third mean intensity vs earlier
    intensities = [w["intensity"] for w in weekly] or [0.0]
    if len(intensities) >= 3:
        cut = max(1, len(intensities) // 3)
        early = sum(intensities[:-cut]) / max(1, len(intensities) - cut)
        late = sum(intensities[-cut:]) / cut
        intensity_creep = (late - early) / (early + 1.0)
    else:
        intensity_creep = 0.0

    median = sorted(intensities)[len(intensities) // 2]
    heavy = sum(1 for i in intensities if i >= median * 1.25) or 1
    light = sum(1 for i in intensities if i <= median * 0.75)
    recovery_ratio = light / heavy

    # end-of-sprint dump: within each week, share of churn in last 20% of commits by time
    dump_scores: list[float] = []
    by_week_commits: dict[str, list[CommitRecord]] = defaultdict(list)
    for c in commits:
        by_week_commits[_week_key(c.timestamp)].append(c)
    for w, items in by_week_commits.items():
        items = sorted(items, key=lambda x: x.timestamp)
        if len(items) < 5:
            continue
        tail = items[int(len(items) * 0.8) :]
        tot = sum(c.insertions + c.deletions for c in items) or 1
        dump_scores.append(sum(c.insertions + c.deletions for c in tail) / tot)
    end_dump = sum(dump_scores) / len(dump_scores) if dump_scores else 0.0

    fatigue_score = min(
        1.0,
        0.35 * after_hours_rate
        + 0.2 * weekend_rate
        + 0.25 * max(0.0, intensity_creep)
        + 0.1 * (1.0 - min(1.0, recovery_ratio))
        + 0.1 * end_dump,
    )
    summary = (
        f"Fatigue={fatigue_score:.2f}; after_hours={after_hours_rate:.0%}, "
        f"creep={intensity_creep:.2f}, recovery={recovery_ratio:.2f}"
    )
    return FatigueReport(
        after_hours_rate=round(after_hours_rate, 4),
        weekend_rate=round(weekend_rate, 4),
        intensity_creep=round(intensity_creep, 4),
        recovery_ratio=round(recovery_ratio, 4),
        end_of_sprint_dump=round(end_dump, 4),
        weekly=weekly[-26:],
        fatigue_score=round(fatigue_score, 4),
        summary=summary,
    )
