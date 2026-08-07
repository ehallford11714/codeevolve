"""Black-box dynamical layer for provenance: state trajectory, impulses, basins, episodes.

Observational only — no ODE simulation, no chaos claims on short series.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from codeevolve.ecology.changepoints import MonthlyBucket, monthly_activity
from codeevolve.gitlog import CommitRecord


@dataclass
class StateSample:
    when: str  # ISO month start
    month: str  # YYYY-MM
    activity: float
    authors: float
    churn: float
    instability: float  # reverts / commits
    load: float = 0.0
    selection: float = 0.0
    typed_heat: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "when": self.when,
            "month": self.month,
            "activity": round(self.activity, 4),
            "authors": round(self.authors, 4),
            "churn": round(self.churn, 4),
            "instability": round(self.instability, 4),
            "load": round(self.load, 4),
            "selection": round(self.selection, 4),
            "typed_heat": round(self.typed_heat, 4),
            "raw": dict(self.raw),
        }

    def vector(self) -> dict[str, float]:
        return {
            "activity": self.activity,
            "authors": self.authors,
            "churn": self.churn,
            "instability": self.instability,
            "load": self.load,
            "selection": self.selection,
            "typed_heat": self.typed_heat,
        }


@dataclass
class ImpulseResponse:
    event_label: str
    event_kind: str
    event_when: str
    horizon_months: int
    delta: dict[str, float]
    pre: dict[str, float]
    post: dict[str, float]
    confidence: float
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_label": self.event_label,
            "event_kind": self.event_kind,
            "event_when": self.event_when,
            "horizon_months": self.horizon_months,
            "delta": {k: round(v, 4) for k, v in self.delta.items()},
            "pre": {k: round(v, 4) for k, v in self.pre.items()},
            "post": {k: round(v, 4) for k, v in self.post.items()},
            "confidence": round(self.confidence, 3),
            "summary": self.summary,
        }


@dataclass
class RegimeBasin:
    stage: str
    start: str
    end: str
    occupancy: float
    sample_count: int
    mean_state: dict[str, float]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "start": self.start,
            "end": self.end,
            "occupancy": round(self.occupancy, 3),
            "sample_count": self.sample_count,
            "mean_state": {k: round(v, 4) for k, v in self.mean_state.items()},
            "summary": self.summary,
        }


@dataclass
class PathEpisode:
    path: str
    start_sha: str
    end_sha: str
    start_when: str | None
    end_when: str | None
    touches: int
    churn: int
    clade_id: str | None
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "start_sha": self.start_sha,
            "end_sha": self.end_sha,
            "start_when": self.start_when,
            "end_when": self.end_when,
            "touches": self.touches,
            "churn": self.churn,
            "clade_id": self.clade_id,
            "summary": self.summary,
        }


@dataclass
class DynamicsReport:
    samples: list[StateSample] = field(default_factory=list)
    impulses: list[ImpulseResponse] = field(default_factory=list)
    basins: list[RegimeBasin] = field(default_factory=list)
    episodes: list[PathEpisode] = field(default_factory=list)
    insufficient: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": len(self.samples),
            "impulse_count": len(self.impulses),
            "basin_count": len(self.basins),
            "episode_count": len(self.episodes),
            "insufficient": self.insufficient,
            "summary": self.summary,
            "samples": [s.to_dict() for s in self.samples],
            "impulses": [i.to_dict() for i in self.impulses],
            "basins": [b.to_dict() for b in self.basins],
            "episodes": [e.to_dict() for e in self.episodes[:80]],
        }


def _z(series: list[float]) -> list[float]:
    if not series:
        return []
    mu = sum(series) / len(series)
    var = sum((x - mu) ** 2 for x in series) / max(1, len(series))
    sd = var**0.5
    if sd < 1e-9:
        return [0.0 for _ in series]
    return [(x - mu) / sd for x in series]


def build_state_trajectory(
    commits: list[CommitRecord],
    *,
    fatigue_weekly: list[dict[str, Any]] | None = None,
    selection_score: float = 0.0,
    branch_heat: dict[str, float] | None = None,
) -> list[StateSample]:
    months = monthly_activity(commits)
    if not months:
        return []

    load_by_month: dict[str, float] = {}
    for w in fatigue_weekly or []:
        week = str(w.get("week") or w.get("start") or "")
        if len(week) >= 7:
            key = week[:7]
            load_by_month[key] = max(load_by_month.get(key, 0.0), float(w.get("intensity") or 0.0))

    heat_vals = list((branch_heat or {}).values())
    mean_heat = sum(heat_vals) / max(1, len(heat_vals))

    raw_act = [float(m.commits) for m in months]
    raw_auth = [float(m.authors) for m in months]
    raw_churn = [float(m.churn) for m in months]
    raw_inst = [m.reverts / max(1, m.commits) for m in months]
    raw_load = [load_by_month.get(m.key, 0.0) for m in months]

    z_act, z_auth, z_churn, z_inst, z_load = (
        _z(raw_act),
        _z(raw_auth),
        _z(raw_churn),
        _z(raw_inst),
        _z(raw_load),
    )

    samples: list[StateSample] = []
    for i, m in enumerate(months):
        samples.append(
            StateSample(
                when=m.start.isoformat(),
                month=m.key,
                activity=z_act[i],
                authors=z_auth[i],
                churn=z_churn[i],
                instability=z_inst[i],
                load=z_load[i],
                selection=float(selection_score),
                typed_heat=mean_heat,
                raw={
                    "commits": m.commits,
                    "authors": m.authors,
                    "churn": m.churn,
                    "reverts": m.reverts,
                    "load": raw_load[i],
                },
            )
        )
    return samples


def _mean_vec(samples: list[StateSample]) -> dict[str, float]:
    if not samples:
        return {}
    keys = list(samples[0].vector().keys())
    out: dict[str, float] = {}
    for k in keys:
        out[k] = sum(s.vector()[k] for s in samples) / len(samples)
    return out


def compute_impulse_responses(
    samples: list[StateSample],
    events: list[dict[str, Any]],
    *,
    horizon: int = 3,
) -> list[ImpulseResponse]:
    if len(samples) < 6:
        return []
    by_month = {s.month: s for s in samples}
    months = [s.month for s in samples]
    out: list[ImpulseResponse] = []
    for ev in events[:20]:
        when = str(ev.get("when") or "")
        if len(when) < 7:
            continue
        mkey = when[:7]
        if mkey not in by_month:
            # nearest month
            mkey = min(months, key=lambda m: abs(_month_ord(m) - _month_ord(when[:7])))
        idx = months.index(mkey)
        pre_sl = samples[max(0, idx - horizon) : idx]
        post_sl = samples[idx : min(len(samples), idx + horizon)]
        if len(pre_sl) < 1 or len(post_sl) < 1:
            continue
        pre = _mean_vec(pre_sl)
        post = _mean_vec(post_sl)
        delta = {k: post.get(k, 0.0) - pre.get(k, 0.0) for k in pre}
        conf = min(0.9, 0.35 + 0.1 * len(pre_sl) + 0.1 * len(post_sl))
        kind = str(ev.get("kind") or "event")
        label = str(ev.get("label") or kind)
        dominant = max(delta.items(), key=lambda kv: abs(kv[1])) if delta else ("activity", 0.0)
        out.append(
            ImpulseResponse(
                event_label=label,
                event_kind=kind,
                event_when=when,
                horizon_months=horizon,
                delta=delta,
                pre=pre,
                post=post,
                confidence=conf,
                summary=(
                    f"After {label} ({kind}), {dominant[0]} Δ={dominant[1]:+.2f} "
                    f"over {horizon} months"
                ),
            )
        )
    return out


def _month_ord(ym: str) -> int:
    try:
        y, m = ym.split("-")[:2]
        return int(y) * 12 + int(m)
    except (ValueError, IndexError):
        return 0


def compute_regime_basins(
    samples: list[StateSample],
    segments: list[dict[str, Any]],
) -> list[RegimeBasin]:
    if not samples:
        return []
    total = len(samples)
    basins: list[RegimeBasin] = []
    if segments:
        for seg in segments:
            stage = str(seg.get("stage") or "unknown")
            start = str(seg.get("start") or "")[:7]
            end = str(seg.get("end") or "")[:7]
            in_seg = [
                s
                for s in samples
                if (not start or s.month >= start) and (not end or s.month <= end or end == "")
            ]
            if not in_seg and start:
                in_seg = [s for s in samples if s.month >= start][:3]
            occ = len(in_seg) / max(1, total)
            mean = _mean_vec(in_seg) if in_seg else {}
            basins.append(
                RegimeBasin(
                    stage=stage,
                    start=str(seg.get("start") or samples[0].when),
                    end=str(seg.get("end") or samples[-1].when),
                    occupancy=occ,
                    sample_count=len(in_seg),
                    mean_state=mean,
                    summary=f"basin {stage} occupancy={occ:.0%} n={len(in_seg)}",
                )
            )
    else:
        # heuristic basins from instability/activity terciles
        for stage, pred in (
            ("growth", lambda s: s.activity > 0.5 and s.instability < 0.5),
            ("disturbance", lambda s: s.instability > 0.8),
            ("consolidation", lambda s: s.activity < 0 and s.instability < 0),
        ):
            in_b = [s for s in samples if pred(s)]
            if not in_b:
                continue
            basins.append(
                RegimeBasin(
                    stage=stage,
                    start=in_b[0].when,
                    end=in_b[-1].when,
                    occupancy=len(in_b) / total,
                    sample_count=len(in_b),
                    mean_state=_mean_vec(in_b),
                    summary=f"heuristic basin {stage} occupancy={len(in_b)/total:.0%}",
                )
            )
    return basins


def path_episodes_from_allocations(
    allocations: list[dict[str, Any]],
    *,
    gap_commits: int = 5,
    max_paths: int = 40,
) -> list[PathEpisode]:
    """Cluster per-path deltas into episodes by coarse sha/order gaps."""
    by_path: dict[str, list[dict[str, Any]]] = {}
    for a in allocations:
        p = str(a.get("path") or "")
        if not p:
            continue
        by_path.setdefault(p, []).append(a)

    # rank paths by touch count
    ranked = sorted(by_path.items(), key=lambda kv: -len(kv[1]))[:max_paths]
    episodes: list[PathEpisode] = []
    for path, rows in ranked:
        # preserve order as given (usually commit order)
        cur: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            if cur and i > 0:
                # break episode every gap_commits touches as a simple heuristic
                if len(cur) >= gap_commits:
                    episodes.append(_episode(path, cur))
                    cur = []
            cur.append(row)
        if cur:
            episodes.append(_episode(path, cur))
    return episodes[:80]


def _episode(path: str, rows: list[dict[str, Any]]) -> PathEpisode:
    churn = sum(int(r.get("insertions") or 0) + int(r.get("deletions") or 0) for r in rows)
    start = rows[0]
    end = rows[-1]
    cid = str(end.get("clade_id") or start.get("clade_id") or "") or None
    return PathEpisode(
        path=path,
        start_sha=str(start.get("sha") or "")[:12],
        end_sha=str(end.get("sha") or "")[:12],
        start_when=start.get("when") or start.get("timestamp"),
        end_when=end.get("when") or end.get("timestamp"),
        touches=len(rows),
        churn=churn,
        clade_id=cid,
        summary=f"episode {path}: {len(rows)} touches, churn={churn}, clade={cid}",
    )


def build_dynamics(report: dict[str, Any], commits: list[CommitRecord] | None = None) -> DynamicsReport:
    """Build dynamics from report dict; commits optional for fresher monthly series."""
    fat = report.get("fatigue") or {}
    sel = report.get("selection") or {}
    ht = report.get("hierarchy_trends") or {}
    heat = {
        str(b.get("type_key")): float(b.get("churn_delta") or b.get("churn") or 0)
        for b in (ht.get("branch_trends") or [])
        if isinstance(b, dict) and b.get("type_key")
    }

    if commits:
        samples = build_state_trajectory(
            commits,
            fatigue_weekly=fat.get("weekly") or [],
            selection_score=float(sel.get("pressure_score") or 0.0),
            branch_heat=heat,
        )
    else:
        # rebuild from ecology calibration months if present
        months = ((report.get("ecology") or {}).get("calibration") or {}).get("changepoints") or {}
        buckets = months.get("months") or []
        samples = []
        for b in buckets:
            if not isinstance(b, dict):
                continue
            commits_n = float(b.get("commits") or 0)
            samples.append(
                StateSample(
                    when=str(b.get("start") or b.get("month") or ""),
                    month=str(b.get("month") or "")[:7],
                    activity=commits_n,
                    authors=float(b.get("authors") or 0),
                    churn=float(b.get("churn") or 0),
                    instability=float(b.get("reverts") or 0) / max(1.0, commits_n),
                    load=0.0,
                    selection=float(sel.get("pressure_score") or 0.0),
                    typed_heat=0.0,
                    raw=b,
                )
            )
        # z-score if we built from raw
        if samples:
            for key in ("activity", "authors", "churn", "instability"):
                vals = [getattr(s, key) for s in samples]
                zs = _z(vals)
                for s, z in zip(samples, zs):
                    setattr(s, key, z)

    cal = (report.get("ecology") or {}).get("calibration") or {}
    event_rows: list[dict[str, Any]] = []
    ev = cal.get("events")
    if isinstance(ev, dict):
        event_rows = [e for e in (ev.get("events") or []) if isinstance(e, dict)]
    elif isinstance(ev, list):
        event_rows = [e for e in ev if isinstance(e, dict)]

    impulses = compute_impulse_responses(samples, event_rows, horizon=3)
    basins = compute_regime_basins(samples, list(cal.get("segments") or []))
    tax = report.get("taxonomy") or {}
    episodes = path_episodes_from_allocations(list(tax.get("allocations") or []))

    insufficient = len(samples) < 12
    return DynamicsReport(
        samples=samples,
        impulses=impulses,
        basins=basins,
        episodes=episodes,
        insufficient=insufficient,
        summary=(
            f"Dynamics: {len(samples)} state samples, {len(impulses)} impulse responses, "
            f"{len(basins)} basins, {len(episodes)} path episodes"
            + ("; insufficient history for strong DST claims" if insufficient else "")
        ),
    )
