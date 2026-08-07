"""Align changepoints to lifecycle events and recalibrate ecological stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from codeevolve.ecology.changepoints import ChangepointReport, ChangePoint, detect_changepoints
from codeevolve.ecology.events import EventCorpus, LifecycleEvent, collect_lifecycle_events
from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import MetricBundle
from codeevolve.phylogeny import EcologicalStage, classify_ecological_stages

_VALID_STAGES = {
    "pioneer",
    "growth",
    "disturbance",
    "consolidation",
    "maturity",
    "decline",
}


@dataclass
class AlignedAnchor:
    event: LifecycleEvent
    changepoint: ChangePoint | None
    delta_days: float | None
    stage: EcologicalStage
    confidence: float
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.to_dict(),
            "changepoint": self.changepoint.to_dict() if self.changepoint else None,
            "delta_days": None if self.delta_days is None else round(self.delta_days, 1),
            "stage": self.stage,
            "confidence": round(self.confidence, 3),
            "rationale": self.rationale,
        }


@dataclass
class LabeledSegment:
    start: datetime
    end: datetime
    stage: EcologicalStage
    confidence: float
    source: str  # event | changepoint | heuristic
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "stage": self.stage,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "label": self.label,
        }


@dataclass
class EcologyCalibration:
    events: EventCorpus
    changepoints: ChangepointReport
    anchors: list[AlignedAnchor] = field(default_factory=list)
    segments: list[LabeledSegment] = field(default_factory=list)
    global_stage: EcologicalStage = "pioneer"
    stage_rationale: str = ""
    confidence: float = 0.0
    method: str = "event_changepoint"
    heuristic_stage: EcologicalStage = "pioneer"
    hit_rate: float | None = None  # fraction of large CPs near events
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "global_stage": self.global_stage,
            "stage_rationale": self.stage_rationale,
            "confidence": round(self.confidence, 3),
            "heuristic_stage": self.heuristic_stage,
            "hit_rate": None if self.hit_rate is None else round(self.hit_rate, 3),
            "summary": self.summary,
            "events": self.events.to_dict(),
            "changepoints": self.changepoints.to_dict(),
            "anchors": [a.to_dict() for a in self.anchors[:40]],
            "segments": [s.to_dict() for s in self.segments[:40]],
        }


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _nearest_cp(
    when: datetime,
    points: list[ChangePoint],
    *,
    max_days: float = 45.0,
    series_pref: set[str] | None = None,
) -> tuple[ChangePoint | None, float | None]:
    best: ChangePoint | None = None
    best_d: float | None = None
    for p in points:
        if series_pref and p.series not in series_pref:
            continue
        d = abs((_aware(p.when) - _aware(when)).total_seconds()) / 86400.0
        if d <= max_days and (best_d is None or d < best_d):
            best, best_d = p, d
    return best, best_d


def align_events_to_changepoints(
    events: list[LifecycleEvent],
    cps: list[ChangePoint],
    *,
    max_days: float = 45.0,
) -> list[AlignedAnchor]:
    # Prefer large-magnitude changepoints for hit matching
    mag_sorted = sorted(cps, key=lambda p: -p.magnitude)
    top = mag_sorted[: max(6, len(mag_sorted) // 3)] or cps
    anchors: list[AlignedAnchor] = []
    for ev in events:
        stage = ev.stage_hint if ev.stage_hint in _VALID_STAGES else "growth"
        pref = {"commits", "authors", "churn"}
        if ev.kind in {"security", "revert_storm"}:
            pref = {"reverts", "commits", "churn"}
        cp, delta = _nearest_cp(ev.when, top, max_days=max_days, series_pref=pref)
        if cp is None:
            cp, delta = _nearest_cp(ev.when, cps, max_days=max_days)
        conf = ev.confidence
        why = f"event:{ev.kind}:{ev.label} → {stage}"
        if cp is not None and delta is not None:
            conf = min(0.98, conf + 0.08 + max(0.0, 0.12 * (1.0 - delta / max_days)))
            # Directional refinement
            if stage == "growth" and cp.direction == "down" and cp.series in {"commits", "churn"}:
                stage = "consolidation"
                why += f"; CP {cp.series} down @ {cp.when.date()} (Δ{delta:.0f}d) → consolidation"
            elif stage == "maturity" and cp.direction == "up" and cp.series == "reverts":
                stage = "disturbance"
                why += f"; CP reverts up @ {cp.when.date()}"
            else:
                why += f"; aligned CP {cp.series} {cp.direction} (Δ{delta:.0f}d)"
        else:
            why += "; no CP within ±45d (event-only hypothesis)"
            conf *= 0.85
        anchors.append(
            AlignedAnchor(
                event=ev,
                changepoint=cp,
                delta_days=delta,
                stage=stage,  # type: ignore[arg-type]
                confidence=conf,
                rationale=why,
            )
        )
    anchors.sort(key=lambda a: a.event.when)
    return anchors


def _build_segments(
    commits: list[CommitRecord],
    anchors: list[AlignedAnchor],
    cps: list[ChangePoint],
) -> list[LabeledSegment]:
    if not commits:
        return []
    ordered = sorted(commits, key=lambda c: c.timestamp)
    t0, t1 = _aware(ordered[0].timestamp), _aware(ordered[-1].timestamp)
    # Boundary times from anchors + large CPs
    bounds: list[tuple[datetime, EcologicalStage, float, str, str]] = []
    for a in anchors:
        bounds.append((_aware(a.event.when), a.stage, a.confidence, "event", a.event.label))
    for p in sorted(cps, key=lambda x: -x.magnitude)[:8]:
        # Map CP direction to soft stage if no event nearby
        if p.direction == "up" and p.series in {"commits", "authors", "churn"}:
            st: EcologicalStage = "growth"
        elif p.direction == "up" and p.series == "reverts":
            st = "disturbance"
        elif p.direction == "down" and p.series in {"commits", "churn"}:
            st = "consolidation"
        elif p.direction == "down" and p.series == "authors":
            st = "decline"
        else:
            st = "growth"
        bounds.append((_aware(p.when), st, 0.45, "changepoint", f"{p.series}:{p.direction}"))
    bounds.sort(key=lambda b: b[0])
    # Dedup bounds within 14 days — keep higher confidence
    cleaned: list[tuple[datetime, EcologicalStage, float, str, str]] = []
    for b in bounds:
        if cleaned and abs((b[0] - cleaned[-1][0]).total_seconds()) < 14 * 86400:
            if b[2] > cleaned[-1][2]:
                cleaned[-1] = b
            continue
        cleaned.append(b)
    if not cleaned:
        return [
            LabeledSegment(t0, t1, "growth", 0.3, "heuristic", "no anchors"),
        ]
    segments: list[LabeledSegment] = []
    # Leading segment before first bound
    first = cleaned[0]
    if first[0] > t0 + timedelta(days=7):
        segments.append(
            LabeledSegment(t0, first[0], "pioneer", 0.55, "event", "pre-first-anchor")
        )
    for i, (when, stage, conf, src, label) in enumerate(cleaned):
        end = cleaned[i + 1][0] if i + 1 < len(cleaned) else t1
        if end <= when:
            end = when + timedelta(days=1)
        segments.append(LabeledSegment(when, end, stage, conf, src, label))
    return segments


def _stage_at(segments: list[LabeledSegment], when: datetime) -> tuple[EcologicalStage, float, str] | None:
    when = _aware(when)
    for s in segments:
        if _aware(s.start) <= when <= _aware(s.end):
            return s.stage, s.confidence, f"segment:{s.source}:{s.label}"
    if segments:
        # after last
        last = segments[-1]
        if when >= _aware(last.start):
            return last.stage, last.confidence * 0.9, f"trailing:{last.label}"
    return None


def calibrate_ecology(
    repo,
    commits: list[CommitRecord],
    metrics: MetricBundle,
    *,
    owner: str | None = None,
    name: str | None = None,
    include_ghsa: bool = True,
) -> EcologyCalibration:
    _, heuristic_stage, heur_why = classify_ecological_stages(commits, metrics)
    events = collect_lifecycle_events(
        repo, commits, owner=owner, name=name, include_ghsa=include_ghsa
    )
    cps = detect_changepoints(commits)
    # Large CPs for hit-rate
    large = sorted(cps.points, key=lambda p: -p.magnitude)[: max(1, len(cps.points) // 2)]
    anchors = align_events_to_changepoints(events.events, cps.points)
    segments = _build_segments(commits, anchors, cps.points)

    hit = None
    if large and events.events:
        hits = 0
        for p in large:
            best = min(
                (abs((_aware(p.when) - _aware(e.when)).total_seconds()) / 86400.0 for e in events.events),
                default=999.0,
            )
            if best <= 45.0:
                hits += 1
        hit = hits / max(1, len(large))

    # Current stage: end of history
    if commits:
        now = _aware(max(c.timestamp for c in commits))
    else:
        now = datetime.now(timezone.utc)
    seg = _stage_at(segments, now)
    if seg and seg[1] >= 0.5:
        stage, conf, why = seg
        method = "event_changepoint"
        rationale = f"{why}; calibrated over heuristic ({heuristic_stage}: {heur_why})"
    elif anchors:
        # nearest recent anchor
        recent = [a for a in anchors if _aware(a.event.when) <= now]
        if recent:
            a = recent[-1]
            age = (now - _aware(a.event.when)).total_seconds() / 86400.0
            # Decay confidence with age
            conf = a.confidence * max(0.4, 1.0 - age / 365.0)
            if conf >= 0.45:
                stage, method = a.stage, "event_anchor"
                rationale = f"latest anchor {a.event.label} → {stage} (age {age:.0f}d); {a.rationale}"
            else:
                stage, conf, method = heuristic_stage, 0.4, "heuristic_fallback"
                rationale = f"anchors stale; {heur_why}"
        else:
            stage, conf, method = heuristic_stage, 0.4, "heuristic_fallback"
            rationale = heur_why
    else:
        stage, conf, method = heuristic_stage, 0.35, "heuristic_fallback"
        rationale = f"no lifecycle anchors; {heur_why}"

    # Soft overrides from global metrics still apply for clear disturbance
    if metrics.revert_rate > 0.12 and stage != "disturbance":
        stage = "disturbance"
        conf = max(conf, 0.7)
        rationale = f"global revert_rate={metrics.revert_rate} forces disturbance; was {rationale}"

    summary = (
        f"Calibrated stage={stage} (conf={conf:.2f}, method={method}); "
        f"events={len(events.events)}, changepoints={len(cps.points)}, "
        f"anchors={len(anchors)}, hit_rate={hit if hit is not None else 'n/a'}"
    )
    return EcologyCalibration(
        events=events,
        changepoints=cps,
        anchors=anchors,
        segments=segments,
        global_stage=stage,  # type: ignore[arg-type]
        stage_rationale=rationale,
        confidence=conf,
        method=method,
        heuristic_stage=heuristic_stage,
        hit_rate=hit,
        summary=summary,
    )
