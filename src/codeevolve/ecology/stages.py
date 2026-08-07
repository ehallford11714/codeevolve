"""Per-clade ecological stages + Lehman law proxies + niches."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.ecology.lehman import LehmanScores, compute_lehman
from codeevolve.ecology.niches import NicheReport, analyze_niches
from codeevolve.ecology.trends import LehmanTrendReport, analyze_lehman_trends
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
class EcologyReport:
    global_stage: EcologicalStage
    stage_rationale: str
    clade_stages: list[CladeStage]
    lehman: LehmanScores
    niches: NicheReport
    timeline: list[dict[str, Any]] = field(default_factory=list)
    lehman_trends: LehmanTrendReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_stage": self.global_stage,
            "stage_rationale": self.stage_rationale,
            "clade_stages": [c.to_dict() for c in self.clade_stages],
            "lehman": self.lehman.to_dict(),
            "lehman_trends": self.lehman_trends.to_dict() if self.lehman_trends else None,
            "niches": self.niches.to_dict(),
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


def analyze_ecology(
    commits: list[CommitRecord],
    metrics: MetricBundle,
    taxonomy: TaxonomyReport,
) -> EcologyReport:
    phy = analyze_phylogeny(commits, metrics)
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
        lehman=compute_lehman(commits, metrics),
        niches=analyze_niches(taxonomy),
        timeline=timeline,
        lehman_trends=analyze_lehman_trends(commits, metrics),
    )
