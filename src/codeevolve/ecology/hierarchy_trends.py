"""Nest ecological trends under deep code-type hierarchies + write trend prose."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.ecology.stages import EcologyReport
from codeevolve.gitlog import CommitRecord
from codeevolve.taxonomy.keywords import (
    HierarchyNode,
    KeywordTaxonomyReport,
    annotate_hierarchy_ecology,
    render_tree,
)
from codeevolve.taxonomy.tree import TaxonomyReport


@dataclass
class BranchTrend:
    type_key: str
    file_count: int
    churn: int
    touches: int
    dominant_stage: str
    stage_mix: dict[str, int]
    early_churn: int
    late_churn: int
    churn_delta: int
    trend: str  # heating | cooling | stable
    narrative: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_key": self.type_key,
            "file_count": self.file_count,
            "churn": self.churn,
            "touches": self.touches,
            "dominant_stage": self.dominant_stage,
            "stage_mix": dict(self.stage_mix),
            "early_churn": self.early_churn,
            "late_churn": self.late_churn,
            "churn_delta": self.churn_delta,
            "trend": self.trend,
            "narrative": self.narrative,
        }


@dataclass
class NextExperiment:
    id: str
    claim: str
    falsifier: str
    measure: str
    branch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim": self.claim,
            "falsifier": self.falsifier,
            "measure": self.measure,
            "branch": self.branch,
        }


@dataclass
class HierarchyTrendReport:
    ascii_tree: str
    hierarchy: dict[str, Any]
    branch_trends: list[BranchTrend]
    lehman_narrative: str
    ecology_narrative: str
    built_narrative: str
    markdown: str
    summary: str = ""
    next_experiments: list[NextExperiment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ascii_tree": self.ascii_tree,
            "hierarchy": self.hierarchy,
            "branch_trends": [b.to_dict() for b in self.branch_trends],
            "lehman_narrative": self.lehman_narrative,
            "ecology_narrative": self.ecology_narrative,
            "built_narrative": self.built_narrative,
            "next_experiments": [e.to_dict() for e in self.next_experiments],
            "markdown": self.markdown,
            "summary": self.summary,
        }


def propose_next_experiments(
    ecology: EcologyReport,
    branch_trends: list[BranchTrend],
) -> list[NextExperiment]:
    """Falsifiable follow-ups — closes the open-loop report gap."""
    exps: list[NextExperiment] = []
    heating = [b for b in branch_trends if b.trend == "heating"]
    cooling = [b for b in branch_trends if b.trend == "cooling"]
    for i, b in enumerate(heating[:3]):
        exps.append(
            NextExperiment(
                id=f"heat_{i+1}",
                claim=f"{b.type_key} heating will raise coupling or revert pressure within 2 windows",
                falsifier="Next two history windows show flat/down coupling edges touching this type and revert_rate not up",
                measure="coupling.edge_count on paths in type + window-window revert_rate",
                branch=b.type_key,
            )
        )
    for i, b in enumerate(cooling[:2]):
        exps.append(
            NextExperiment(
                id=f"cool_{i+1}",
                claim=f"{b.type_key} cooling reflects consolidation, not abandonment",
                falsifier="File touch count drops >50% while debt/TODO density in branch rises",
                measure="touch_by_type + debt hits on sample_paths",
                branch=b.type_key,
            )
        )
    lt = ecology.lehman_trends
    if lt and any(t.series == "revert_rate" and t.trend == "increasing" for t in lt.tests):
        exps.append(
            NextExperiment(
                id="lehman_quality",
                claim="Rising revert_rate supports declining_quality (hypothesis, not grade)",
                falsifier="Next window revert_rate decreases while churn stays within 20%",
                measure="ecology.lehman_trends.tests[revert_rate]",
            )
        )
    if ecology.global_stage in {"disturbance", "growth"}:
        exps.append(
            NextExperiment(
                id="stage_shift",
                claim=f"Repo remains in {ecology.global_stage} unless test co-touch with hot types rises",
                falsifier="verification/* share of touches on heating branches increases ≥25% relative and stage leaves disturbance/growth",
                measure="hierarchy_trends.branch_trends + ecology.global_stage",
            )
        )
    cal = ecology.calibration
    if cal and cal.changepoints.points:
        top = max(cal.changepoints.points, key=lambda p: p.magnitude)
        exps.append(
            NextExperiment(
                id="changepoint_persist",
                claim=(
                    f"Largest activity changepoint ({top.series} {top.direction} @ {top.when.date()}) "
                    "marks a lasting regime, not a one-month spike"
                ),
                falsifier="Next 3 months return to pre-CP mean within 15% without a reversing CP",
                measure="ecology.calibration.changepoints",
            )
        )
    if cal and any(a.event.kind == "security" for a in cal.anchors):
        exps.append(
            NextExperiment(
                id="security_disturbance",
                claim="Security advisory windows classify as disturbance with elevated reverts or churn",
                falsifier="Advisory±45d segment shows maturity/consolidation with revert_rate flat",
                measure="ecology.calibration.anchors[security]",
            )
        )
    cal = ecology.calibration
    if cal and cal.anchors:
        a = cal.anchors[-1]
        exps.append(
            NextExperiment(
                id="event_anchor",
                claim=f"Latest lifecycle anchor {a.event.label} correctly predicts stage {a.stage}",
                falsifier=(
                    f"Within 90 days, calibrated stage diverges from {a.stage} without a newer "
                    "security/major/revert_storm event"
                ),
                measure="ecology.calibration.global_stage + events",
                branch=a.event.kind,
            )
        )
    if not exps:
        exps.append(
            NextExperiment(
                id="baseline_monitor",
                claim="Typed branch churn mix stays stable (±15%) over next window",
                falsifier="Any top-5 type_key churn_delta magnitude exceeds 15% of prior window churn",
                measure="hierarchy_trends.branch_trends[*].churn_delta",
            )
        )
    return exps[:8]


def _window_churn_by_type(
    commits: list[CommitRecord],
    path_types: dict[str, Any],
    *,
    depth: int = 3,
) -> tuple[dict[str, int], dict[str, int]]:
    ordered = sorted(commits, key=lambda c: c.timestamp)
    if not ordered:
        return {}, {}
    mid = max(1, len(ordered) // 2)
    early, late = ordered[:mid], ordered[mid:]

    def accum(part: list[CommitRecord]) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for c in part:
            share = (c.insertions + c.deletions) // max(1, len(c.files))
            for f in c.files:
                hit = path_types.get(f)
                if not hit:
                    continue
                key = "/".join(hit.type_path[:depth])
                out[key] += share
        return dict(out)

    return accum(early), accum(late)


def _branch_trends(
    kw: KeywordTaxonomyReport,
    ecology: EcologyReport,
    commits: list[CommitRecord],
    taxonomy: TaxonomyReport,
) -> list[BranchTrend]:
    stage_by_clade = {c.clade_id: c.stage for c in ecology.clade_stages}
    early, late = _window_churn_by_type(commits, kw.path_types, depth=3)

    # Aggregate per type_key (up to 3 levels)
    files_by: dict[str, list[str]] = defaultdict(list)
    churn_by: dict[str, int] = defaultdict(int)
    touch_by: dict[str, int] = defaultdict(int)
    for path, hit in kw.path_types.items():
        key = "/".join(hit.type_path[:3])
        files_by[key].append(path)
        # churn from taxonomy allocations if present
    for a in taxonomy.allocations:
        hit = kw.path_types.get(a.path)
        if not hit:
            continue
        key = "/".join(hit.type_path[:3])
        churn_by[key] += a.insertions + a.deletions
        touch_by[key] += 1

    trends: list[BranchTrend] = []
    for key, files in sorted(files_by.items(), key=lambda x: -len(x[1])):
        stages: dict[str, int] = defaultdict(int)
        for f in files:
            cid = taxonomy.path_to_clade.get(f)
            if cid and cid in stage_by_clade:
                stages[stage_by_clade[cid]] += 1
        dominant = max(stages, key=stages.get) if stages else "unknown"  # type: ignore[arg-type]
        e_ch = early.get(key, 0)
        l_ch = late.get(key, 0)
        delta = l_ch - e_ch
        if delta > max(20, int(0.25 * (e_ch + 1))):
            trend = "heating"
        elif delta < -max(20, int(0.25 * (e_ch + 1))):
            trend = "cooling"
        else:
            trend = "stable"
        narrative = (
            f"**{key}** holds {len(files)} files (churn={churn_by[key]}). "
            f"Dominant ecological stage is **{dominant}**. "
            f"Half-history churn moved {e_ch} → {l_ch} ({trend}). "
        )
        if trend == "heating":
            narrative += "Construction energy is concentrating here — protect boundaries and tests."
        elif trend == "cooling":
            narrative += "Activity is settling — good candidate for consolidation or docs."
        else:
            narrative += "Steady maintenance load — watch for silent debt accumulation."
        trends.append(
            BranchTrend(
                type_key=key,
                file_count=len(files),
                churn=churn_by[key],
                touches=touch_by[key],
                dominant_stage=dominant,
                stage_mix=dict(stages),
                early_churn=e_ch,
                late_churn=l_ch,
                churn_delta=delta,
                trend=trend,
                narrative=narrative,
            )
        )
    trends.sort(key=lambda b: (-b.churn, -b.file_count))
    return trends[:40]


def _lehman_narrative(ecology: EcologyReport) -> str:
    lt = ecology.lehman_trends
    lehman = ecology.lehman
    cal = ecology.calibration
    cal_bit = ""
    if cal:
        anchors = ", ".join(
            f"{a.event.label}→{a.stage}" for a in cal.anchors[:5]
        ) or "none"
        cal_bit = (
            f" Calibration method={cal.method} conf={cal.confidence:.2f}; "
            f"events={len(cal.events.events)}, changepoints={len(cal.changepoints.points)}, "
            f"hit_rate={cal.hit_rate}; anchors={anchors}."
        )
    if not lt:
        return (
            f"Global stage **{ecology.global_stage}** — {ecology.stage_rationale}.{cal_bit} "
            "Mann–Kendall trend battery unavailable."
        )
    bits = []
    for t in lt.tests:
        bits.append(f"{t.series} is {t.trend} (τ={t.tau}, p≈{t.p_approx})")
    support = ", ".join(f"{k}={v}" for k, v in list(lt.law_support.items())[:6])
    return (
        f"Global stage **{ecology.global_stage}** — {ecology.stage_rationale}.{cal_bit} "
        f"Lehman proxies: continuing_change={getattr(lehman, 'continuing_change', None)}, "
        f"growth={getattr(lehman, 'continuing_growth', None)}, "
        f"quality={getattr(lehman, 'declining_quality', None)}. "
        f"Trend tests: {'; '.join(bits)}. Law support map: {support}."
    )


def _ecology_narrative(ecology: EcologyReport, branch_trends: list[BranchTrend]) -> str:
    heating = [b for b in branch_trends if b.trend == "heating"][:5]
    cooling = [b for b in branch_trends if b.trend == "cooling"][:5]
    stages = ", ".join(
        f"{c.label or c.clade_id}→{c.stage}" for c in ecology.clade_stages[:8]
    )
    overcrowded = (ecology.niches.to_dict().get("overcrowded") if ecology.niches else None) or []
    lines = [
        f"Clade stages: {stages or 'n/a'}.",
        f"Timeline windows: {ecology.timeline}.",
    ]
    if heating:
        lines.append("Heating branches: " + ", ".join(b.type_key for b in heating) + ".")
    if cooling:
        lines.append("Cooling branches: " + ", ".join(b.type_key for b in cooling) + ".")
    if overcrowded:
        lines.append(f"Overcrowded niches: {overcrowded}.")
    return " ".join(lines)


def _built_narrative(kw: KeywordTaxonomyReport, branch_trends: list[BranchTrend]) -> str:
    fam = ", ".join(f"{k}={v}" for k, v in list(kw.family_counts.items())[:6])
    top = branch_trends[:5]
    detail = "; ".join(f"{b.type_key} ({b.file_count} files, {b.trend})" for b in top)
    return (
        f"{kw.summary} Family mix: {fam}. "
        f"Largest typed constructions: {detail or 'n/a'}."
    )


def write_hierarchy_trend_markdown(report: HierarchyTrendReport) -> str:
    branch_md = "\n".join(
        f"- {b.narrative}" for b in report.branch_trends[:18]
    ) or "- No typed branches."
    exp_md = "\n".join(
        f"- **{e.id}** ({e.branch or 'repo'}): {e.claim}  \n"
        f"  Falsifier: {e.falsifier}  \n"
        f"  Measure: `{e.measure}`"
        for e in report.next_experiments
    ) or "- None proposed."
    return "\n".join(
        [
            "# What Was Built — Nested Hierarchy & Ecological Trends",
            "",
            "## Deep type hierarchy",
            "```",
            report.ascii_tree,
            "```",
            "",
            "## How the construction evolved",
            report.built_narrative,
            "",
            "## Ecological reading",
            report.ecology_narrative,
            "",
            "## Lehman / Mann–Kendall trends",
            report.lehman_narrative,
            "",
            "## Branch-level trend notes",
            branch_md,
            "",
            "## Next experiments (falsifiable)",
            exp_md,
            "",
            f"_{report.summary}_",
            "",
        ]
    )


def analyze_hierarchy_trends(
    commits: list[CommitRecord],
    taxonomy: TaxonomyReport,
    ecology: EcologyReport,
) -> HierarchyTrendReport:
    kw = taxonomy.keyword_taxonomy
    if kw is None:
        # Empty shell if taxonomy skipped keywords
        empty = HierarchyNode(name="built")
        return HierarchyTrendReport(
            ascii_tree="(no keyword taxonomy)",
            hierarchy=empty.to_dict(),
            branch_trends=[],
            lehman_narrative=_lehman_narrative(ecology),
            ecology_narrative=_ecology_narrative(ecology, []),
            built_narrative="Keyword taxonomy unavailable.",
            markdown="",
            summary="No keyword taxonomy attached.",
        )

    stage_by_clade = {c.clade_id: c.stage for c in ecology.clade_stages}
    annotate_hierarchy_ecology(
        kw.hierarchy,
        path_to_clade=taxonomy.path_to_clade,
        clade_stages=stage_by_clade,
        path_types=kw.path_types,
    )
    branches = _branch_trends(kw, ecology, commits, taxonomy)
    built = _built_narrative(kw, branches)
    eco = _ecology_narrative(ecology, branches)
    leh = _lehman_narrative(ecology)
    experiments = propose_next_experiments(ecology, branches)
    ascii_tree = render_tree(kw.hierarchy, max_depth=5)
    report = HierarchyTrendReport(
        ascii_tree=ascii_tree,
        hierarchy=kw.hierarchy.to_dict(),
        branch_trends=branches,
        lehman_narrative=leh,
        ecology_narrative=eco,
        built_narrative=built,
        markdown="",
        next_experiments=experiments,
        summary=(
            f"{len(branches)} typed branches; "
            f"heating={sum(1 for b in branches if b.trend == 'heating')}, "
            f"cooling={sum(1 for b in branches if b.trend == 'cooling')}, "
            f"stage={ecology.global_stage}; "
            f"experiments={len(experiments)}"
        ),
    )
    report.markdown = write_hierarchy_trend_markdown(report)
    return report
