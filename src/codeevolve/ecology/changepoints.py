"""Activity changepoint detection (pure-Python binary segmentation + CUSUM).

Inspired by Walden et al. arXiv:2103.11013 — OSS activity is punctuated.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from codeevolve.gitlog import CommitRecord


@dataclass
class MonthlyBucket:
    key: str  # YYYY-MM
    start: datetime
    commits: int = 0
    authors: int = 0
    reverts: int = 0
    churn: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "month": self.key,
            "start": self.start.isoformat(),
            "commits": self.commits,
            "authors": self.authors,
            "reverts": self.reverts,
            "churn": round(self.churn, 2),
        }


@dataclass
class ChangePoint:
    index: int
    when: datetime
    series: str
    direction: str  # up | down
    magnitude: float
    before_mean: float
    after_mean: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "when": self.when.isoformat(),
            "series": self.series,
            "direction": self.direction,
            "magnitude": round(self.magnitude, 4),
            "before_mean": round(self.before_mean, 4),
            "after_mean": round(self.after_mean, 4),
        }


@dataclass
class ChangepointReport:
    months: list[MonthlyBucket] = field(default_factory=list)
    points: list[ChangePoint] = field(default_factory=list)
    method: str = "binary_segmentation"
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "month_count": len(self.months),
            "changepoint_count": len(self.points),
            "months": [m.to_dict() for m in self.months],
            "points": [p.to_dict() for p in self.points],
            "summary": self.summary,
        }


def monthly_activity(commits: list[CommitRecord]) -> list[MonthlyBucket]:
    ordered = sorted(commits, key=lambda c: c.timestamp)
    if not ordered:
        return []
    buckets: dict[str, MonthlyBucket] = {}
    authors_by: dict[str, set[str]] = defaultdict(set)
    for c in ordered:
        ts = c.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        key = f"{ts.year:04d}-{ts.month:02d}"
        if key not in buckets:
            buckets[key] = MonthlyBucket(
                key=key,
                start=datetime(ts.year, ts.month, 1, tzinfo=timezone.utc),
            )
        b = buckets[key]
        b.commits += 1
        b.churn += c.insertions + c.deletions
        if c.is_revert:
            b.reverts += 1
        authors_by[key].add(c.email or c.author)
    for key, b in buckets.items():
        b.authors = len(authors_by[key])
    return [buckets[k] for k in sorted(buckets.keys())]


def _rss(x: list[float]) -> float:
    n = len(x)
    if n <= 1:
        return 0.0
    mu = sum(x) / n
    return sum((v - mu) ** 2 for v in x)


def pelt_lite(
    values: list[float],
    *,
    penalty: float | None = None,
    min_seg: int = 3,
) -> list[int]:
    """Backward-compatible name → binary segmentation changepoint indices."""
    return binary_segmentation(values, penalty=penalty, min_seg=min_seg)


def binary_segmentation(
    values: list[float],
    *,
    penalty: float | None = None,
    min_seg: int = 3,
    max_cps: int = 8,
) -> list[int]:
    """
    Greedy binary segmentation on residual sum of squares.
    Returns sorted changepoint indices (start of new segment).
    """
    n = len(values)
    if n < 2 * min_seg:
        return []
    # Penalty scaled to series variance so clear steps survive
    total_var = _rss(values) / max(1, n)
    pen = penalty if penalty is not None else max(1.0, total_var) * math.log(n) * 0.75

    def best_split(s: int, e: int) -> tuple[int | None, float]:
        if e - s < 2 * min_seg:
            return None, 0.0
        base = _rss(values[s:e])
        best_i: int | None = None
        best_gain = 0.0
        for i in range(s + min_seg, e - min_seg + 1):
            gain = base - _rss(values[s:i]) - _rss(values[i:e])
            if gain > best_gain:
                best_gain = gain
                best_i = i
        return best_i, best_gain

    segments = [(0, n)]
    cps: list[int] = []
    for _ in range(max_cps):
        pick: tuple[int, float, int, int] | None = None  # gain, idx, s, e
        for s, e in segments:
            idx, gain = best_split(s, e)
            if idx is None:
                continue
            if gain > pen and (pick is None or gain > pick[0]):
                pick = (gain, idx, s, e)
        if pick is None:
            break
        _, idx, s, e = pick
        cps.append(idx)
        segments = [(a, b) for a, b in segments if not (a == s and b == e)]
        segments.extend([(s, idx), (idx, e)])
    return sorted(cps)


def cusum_changepoints(
    values: list[float],
    *,
    min_seg: int = 3,
    threshold_scale: float = 1.5,
) -> list[int]:
    """Simple two-sided CUSUM peaks as additional candidates."""
    n = len(values)
    if n < 2 * min_seg:
        return []
    mu = sum(values) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in values) / n) or 1.0
    thr = threshold_scale * sd * math.sqrt(n)
    s_pos = s_neg = 0.0
    cps: list[int] = []
    last = 0
    for i, v in enumerate(values):
        s_pos = max(0.0, s_pos + (v - mu))
        s_neg = min(0.0, s_neg + (v - mu))
        if (s_pos > thr or s_neg < -thr) and i - last >= min_seg and n - i >= min_seg:
            cps.append(i)
            s_pos = s_neg = 0.0
            last = i
    return cps


def detect_changepoints(
    commits: list[CommitRecord],
    *,
    min_seg: int = 3,
) -> ChangepointReport:
    months = monthly_activity(commits)
    if len(months) < 6:
        return ChangepointReport(
            months=months,
            summary=f"Too few months ({len(months)}) for changepoint detection",
        )
    series_map = {
        "commits": [float(m.commits) for m in months],
        "authors": [float(m.authors) for m in months],
        "reverts": [float(m.reverts) for m in months],
        "churn": [float(m.churn) for m in months],
    }
    points: list[ChangePoint] = []
    for name, vals in series_map.items():
        idxs = set(binary_segmentation(vals, min_seg=min_seg))
        idxs |= set(cusum_changepoints(vals, min_seg=min_seg))
        for idx in sorted(idxs):
            if idx < min_seg or idx > len(vals) - min_seg:
                continue
            before = vals[:idx]
            after = vals[idx:]
            bm = sum(before) / len(before)
            am = sum(after) / len(after)
            mag = am - bm
            # Ignore tiny shifts relative to scale
            scale = max(1.0, (sum(vals) / len(vals)))
            if abs(mag) < 0.15 * scale and name != "reverts":
                continue
            if name == "reverts" and abs(mag) < 0.25:
                continue
            points.append(
                ChangePoint(
                    index=idx,
                    when=months[idx].start,
                    series=name,
                    direction="up" if mag >= 0 else "down",
                    magnitude=abs(mag),
                    before_mean=bm,
                    after_mean=am,
                )
            )
    best: dict[tuple[str, str], ChangePoint] = {}
    for p in points:
        key = (p.when.strftime("%Y-%m"), p.series)
        if key not in best or p.magnitude > best[key].magnitude:
            best[key] = p
    points = sorted(best.values(), key=lambda p: (-p.magnitude, p.when))
    n_up = sum(1 for p in points if p.direction == "up")
    n_down = sum(1 for p in points if p.direction == "down")
    return ChangepointReport(
        months=months,
        points=points,
        method="binary_segmentation+cusum",
        summary=(
            f"{len(points)} changepoints across {len(months)} months "
            f"(up={n_up}, down={n_down}); median OSS projects show 1–6 (Walden 2021)"
        ),
    )
