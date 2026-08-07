"""Weakness and failure-point ranking."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.debt import DebtReport
from codeevolve.genetics.lineage import GeneticsReport
from codeevolve.gitlog import CommitRecord
from codeevolve.ingest.github_api import SelectionPressure
from codeevolve.metrics import MetricBundle
from codeevolve.psychology.load import CognitiveLoadReport
from codeevolve.psychology.rhythm import FatigueReport
from codeevolve.risk.blast_radius import cochange_degrees
from codeevolve.taxonomy.tree import TaxonomyReport


@dataclass
class FailurePoint:
    id: str
    kind: str
    severity: float
    path: str
    clade_id: str
    title: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    suggested_intervention: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "severity": self.severity,
            "path": self.path,
            "clade_id": self.clade_id,
            "title": self.title,
            "evidence": list(self.evidence),
            "suggested_intervention": self.suggested_intervention,
        }


@dataclass
class RiskReport:
    failure_points: list[FailurePoint]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_points": [f.to_dict() for f in self.failure_points],
            "count": len(self.failure_points),
            "summary": self.summary,
        }


def analyze_risk(
    commits: list[CommitRecord],
    metrics: MetricBundle,
    taxonomy: TaxonomyReport,
    genetics: GeneticsReport,
    debt: DebtReport,
    *,
    selection: SelectionPressure | None = None,
    fatigue: FatigueReport | None = None,
    cognitive_load: CognitiveLoadReport | None = None,
) -> RiskReport:
    points: list[FailurePoint] = []
    n = max(1, len(commits))

    deg = cochange_degrees(commits)
    revert_files: dict[str, int] = defaultdict(int)
    authors_by_file: dict[str, set[str]] = defaultdict(set)
    test_touch = 0
    prod_touch = 0
    for c in commits:
        files = c.files[:50]
        for a in files:
            authors_by_file[a].add(c.author)
            if c.is_revert:
                revert_files[a] += 1
            if re.search(r"(^|/)tests?(/|$)|_test\.|spec\.", a, re.I):
                test_touch += 1
            else:
                prod_touch += 1

    for i, hot in enumerate(metrics.hot_files[:8]):
        path = hot["path"]
        touches = hot["touches"]
        blast = deg.get(path, 0)
        # Soft-cap hotspot severity so mature OSS doesn't all score 1.0
        import math

        sev = min(1.0, 0.35 + 0.35 * math.log1p(touches) / math.log1p(n) + 0.25 * math.log1p(blast) / math.log1p(40))
        points.append(
            FailurePoint(
                id=f"W{len(points)+1}",
                kind="hotspot_blast",
                severity=round(sev, 3),
                path=path,
                clade_id=taxonomy.path_to_clade.get(path, "clade_unknown"),
                title=f"Hotspot with blast radius ({blast} co-changers)",
                evidence=[{"touches": touches, "co_changers": blast}],
                suggested_intervention="Extract boundaries; add characterization tests before further growth",
            )
        )

    for path, rc in sorted(revert_files.items(), key=lambda x: -x[1])[:6]:
        if rc < 2:
            continue
        points.append(
            FailurePoint(
                id=f"W{len(points)+1}",
                kind="revert_surface",
                severity=round(min(1.0, 0.4 + rc / 5.0), 3),
                path=path,
                clade_id=taxonomy.path_to_clade.get(path, "clade_unknown"),
                title="Repeated revert surface",
                evidence=[{"revert_touches": rc}],
                suggested_intervention="Freeze API; add regression tests for reverted behaviors",
            )
        )

    for path, authors in authors_by_file.items():
        if len(authors) == 1 and path in {h["path"] for h in metrics.hot_files[:10]}:
            points.append(
                FailurePoint(
                    id=f"W{len(points)+1}",
                    kind="bus_factor",
                    severity=0.55,
                    path=path,
                    clade_id=taxonomy.path_to_clade.get(path, "clade_unknown"),
                    title="Single-owner hotspot (bus factor = 1)",
                    evidence=[{"owners": list(authors)}],
                    suggested_intervention="Spread ownership; document invariants",
                )
            )
            if len(points) > 20:
                break

    if prod_touch > 20 and test_touch < prod_touch * 0.25:
        points.append(
            FailurePoint(
                id=f"W{len(points)+1}",
                kind="test_gap",
                severity=0.7,
                path="(repository)",
                clade_id="global",
                title="Test co-touch lag vs production churn",
                evidence=[{"prod_touches": prod_touch, "test_touches": test_touch}],
                suggested_intervention="Raise test co-evolution on high-churn clades",
            )
        )

    if metrics.dependency_rate > 0.12:
        points.append(
            FailurePoint(
                id=f"W{len(points)+1}",
                kind="dependency_shock",
                severity=round(min(1.0, metrics.dependency_rate * 3), 3),
                path="(manifests/lockfiles)",
                clade_id="global",
                title="Elevated dependency churn",
                evidence=[{"dependency_rate": metrics.dependency_rate}],
                suggested_intervention="Pin critical deps; batch upgrades with CI gates",
            )
        )

    # Low fitness lineages
    for lin in genetics.lineages[:5]:
        if lin.fitness < 0.45:
            points.append(
                FailurePoint(
                    id=f"W{len(points)+1}",
                    kind="low_fitness",
                    severity=round(1.0 - lin.fitness, 3),
                    path=lin.path,
                    clade_id=lin.clade_id,
                    title="Low evolutionary fitness (churn/revert pressure)",
                    evidence=[{"fitness": lin.fitness, "appearances": lin.appearances}],
                    suggested_intervention="Refactor or isolate; reduce revert triggers",
                )
            )

    if fatigue and fatigue.fatigue_score >= 0.45:
        points.append(
            FailurePoint(
                id=f"W{len(points)+1}",
                kind="sprint_fatigue",
                severity=round(min(1.0, 0.4 + fatigue.fatigue_score), 3),
                path="(work rhythm)",
                clade_id="global",
                title="Elevated sprint fatigue / intensity creep",
                evidence=[fatigue.to_dict()],
                suggested_intervention="Schedule recovery week; reduce after-hours and end-of-sprint dumps",
            )
        )

    if cognitive_load and cognitive_load.load_index >= 0.5:
        points.append(
            FailurePoint(
                id=f"W{len(points)+1}",
                kind="cognitive_load",
                severity=round(min(1.0, 0.35 + cognitive_load.load_index), 3),
                path="(attention / ownership)",
                clade_id="global",
                title="High cognitive-load proxy (switches + ownership stress)",
                evidence=[cognitive_load.to_dict()],
                suggested_intervention="Reduce cross-clade commits; spread ownership on hot paths",
            )
        )

    if selection and selection.pressure_score >= 0.35:
        points.append(
            FailurePoint(
                id=f"W{len(points)+1}",
                kind="selection_pressure",
                severity=round(min(1.0, 0.4 + selection.pressure_score), 3),
                path="(github issues/prs)",
                clade_id="global",
                title="Elevated external selection pressure (bugs/reopens/backlog)",
                evidence=[
                    {
                        "pressure_score": selection.pressure_score,
                        "bug_label_rate": selection.bug_label_rate,
                        "open_issues": selection.open_issues,
                        "reopened_like": selection.reopened_like,
                    }
                ],
                suggested_intervention="Prioritize bug triage and reopen reduction before expanding scope",
            )
        )

    for m in debt.architectural_mistakes:
        mid = m.get("id", "arch")
        points.append(
            FailurePoint(
                id=f"W{len(points)+1}",
                kind=str(mid),
                severity=0.75 if m.get("severity") == "high" else 0.5,
                path=(m.get("evidence") or [{}])[0].get("path", "(arch)")
                if isinstance(m.get("evidence"), list) and m.get("evidence")
                else "(arch)",
                clade_id="global",
                title=str(m.get("title") or mid),
                evidence=[{"mistake_id": mid, "why": m.get("why")}],
                suggested_intervention="See architectural mistake rationale; schedule containment refactor",
            )
        )

    # Dedup by (kind, path)
    seen: set[tuple[str, str]] = set()
    uniq: list[FailurePoint] = []
    for p in sorted(points, key=lambda x: -x.severity):
        key = (p.kind, p.path)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    # re-id
    for i, p in enumerate(uniq, 1):
        p.id = f"W{i}"

    top = ", ".join(f"{p.id}:{p.kind}" for p in uniq[:5]) or "none"
    summary = f"{len(uniq)} failure points ranked; top: {top}"
    return RiskReport(failure_points=uniq[:40], summary=summary)
