"""Per-clade ecological stages + Lehman law proxies."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import MetricBundle
from codeevolve.phylogeny import EcologicalStage, analyze_phylogeny
from codeevolve.taxonomy.tree import TaxonomyReport


@dataclass
class CladeStage:
    clade_id: str
    label: str
    stage: EcologicalStage
    rationale: str
    churn: int
    touches: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "clade_id": self.clade_id,
            "label": self.label,
            "stage": self.stage,
            "rationale": self.rationale,
            "churn": self.churn,
            "touches": self.touches,
        }


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


@dataclass
class EcologyReport:
    global_stage: EcologicalStage
    stage_rationale: str
    clade_stages: list[CladeStage]
    lehman: LehmanScores
    timeline: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_stage": self.global_stage,
            "stage_rationale": self.stage_rationale,
            "clade_stages": [c.to_dict() for c in self.clade_stages],
            "lehman": self.lehman.to_dict(),
            "timeline": list(self.timeline),
        }


def _clade_stage(churn: int, touches: int, revert_frac: float, n_files: int) -> tuple[EcologicalStage, str]:
    if touches < 3 or n_files <= 2:
        return "pioneer", "Sparse activity / small surface"
    if revert_frac > 0.15:
        return "disturbance", "Elevated revert fraction on clade"
    if churn > 800 and revert_frac < 0.05:
        return "growth", "High churn with low reverts"
    if churn < 120 and touches > 5:
        return "maturity", "Low churn with recurring maintenance"
    if touches > 8 and churn < 400:
        return "consolidation", "Moderate activity, cooling churn"
    if touches <= 2 and n_files > 5:
        return "decline", "Files present but little recent activity"
    return "growth", "Default expansion pattern"


def _lehman(commits: list[CommitRecord], metrics: MetricBundle) -> LehmanScores:
    n = max(1, len(commits))
    ordered = sorted(commits, key=lambda c: c.timestamp)
    mid = max(1, n // 2)
    early, late = ordered[:mid], ordered[mid:]
    early_files = {f for c in early for f in c.files}
    late_files = {f for c in late for f in c.files}
    growth = len(late_files - early_files) / max(1, len(early_files | late_files))
    complexity = min(1.0, metrics.file_touch_entropy / 6.0)
    quality_decline = min(1.0, metrics.revert_rate * 2.5 + (1.0 - metrics.code_stability) * 0.5)
    # familiarity: bounded novelty — new file fraction in late window
    familiarity = 1.0 - min(1.0, growth)
    # feedback volatility: |momentum|
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


def analyze_ecology(
    commits: list[CommitRecord],
    metrics: MetricBundle,
    taxonomy: TaxonomyReport,
) -> EcologyReport:
    phy = analyze_phylogeny(commits, metrics)
    # per-clade stats
    clade_churn: dict[str, int] = defaultdict(int)
    clade_touch: dict[str, int] = defaultdict(int)
    clade_reverts: dict[str, int] = defaultdict(int)
    for a in taxonomy.allocations:
        clade_churn[a.clade_id] += a.insertions + a.deletions
        clade_touch[a.clade_id] += 1
    for c in commits:
        if not c.is_revert:
            continue
        for f in c.files:
            cid = taxonomy.path_to_clade.get(f)
            if cid:
                clade_reverts[cid] += 1

    by_id = {c.id: c for c in taxonomy.clades}
    clade_stages: list[CladeStage] = []
    for cid, clade in by_id.items():
        touches = clade_touch[cid]
        revs = clade_reverts[cid]
        rf = revs / max(1, touches)
        stage, why = _clade_stage(clade_churn[cid], touches, rf, len(clade.files))
        clade_stages.append(
            CladeStage(
                clade_id=cid,
                label=clade.label,
                stage=stage,
                rationale=why,
                churn=clade_churn[cid],
                touches=touches,
            )
        )
    clade_stages.sort(key=lambda x: -x.churn)

    # coarse timeline by thirds
    ordered = sorted(commits, key=lambda c: c.timestamp)
    timeline: list[dict[str, Any]] = []
    if ordered:
        chunk = max(1, len(ordered) // 3)
        for i, label in enumerate(["early", "mid", "late"]):
            part = ordered[i * chunk : (i + 1) * chunk] if i < 2 else ordered[i * chunk :]
            if not part:
                continue
            ch = sum(c.insertions + c.deletions for c in part)
            rv = sum(1 for c in part if c.is_revert)
            timeline.append(
                {
                    "window": label,
                    "commits": len(part),
                    "churn": ch,
                    "revert_rate": round(rv / len(part), 4),
                }
            )

    return EcologyReport(
        global_stage=phy.current_stage,
        stage_rationale=phy.stage_rationale,
        clade_stages=clade_stages,
        lehman=_lehman(commits, metrics),
        timeline=timeline,
    )
