"""Evidence-linked phased refactor plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codeevolve.debt import DebtReport
from codeevolve.refactor.effort import estimate_effort, expected_fitness_gain, priority_for
from codeevolve.risk.weaknesses import RiskReport


WAVE_ORDER = ("stabilize", "contain", "pay_down", "evolve")


@dataclass
class RefactorStep:
    id: str
    title: str
    priority: str
    wave: str
    clade_ids: list[str]
    paths: list[str]
    problem_kind: str
    evidence_refs: list[str]
    actions: list[str]
    acceptance_criteria: list[str]
    estimated_effort: str
    expected_fitness_gain: float
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "wave": self.wave,
            "clade_ids": list(self.clade_ids),
            "paths": list(self.paths),
            "problem_kind": self.problem_kind,
            "evidence_refs": list(self.evidence_refs),
            "actions": list(self.actions),
            "acceptance_criteria": list(self.acceptance_criteria),
            "estimated_effort": self.estimated_effort,
            "expected_fitness_gain": self.expected_fitness_gain,
            "depends_on": list(self.depends_on),
        }


@dataclass
class RefactorPlan:
    waves: list[dict[str, Any]]
    steps: list[RefactorStep]
    markdown: str
    backend: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        by_wave: dict[str, list[dict[str, Any]]] = {w: [] for w in WAVE_ORDER}
        for s in self.steps:
            by_wave.setdefault(s.wave, []).append(s.to_dict())
        return {
            "backend": self.backend,
            "waves": [{"name": w, "steps": by_wave.get(w, [])} for w in WAVE_ORDER],
            "step_count": len(self.steps),
            "markdown": self.markdown,
        }


def _wave_for(kind: str) -> str:
    if kind in {
        "revert_surface",
        "dependency_shock",
        "selection_pressure",
        "sprint_fatigue",
        "cognitive_load",
    }:
        return "stabilize"
    if kind in {"hotspot_blast", "bus_factor", "hotspot_gravity", "circular_risk", "utility_sink"}:
        return "contain"
    if kind in {"test_gap", "low_fitness"} or "debt" in kind or kind.startswith("deprec"):
        return "pay_down"
    return "evolve"


def build_refactor_plan(risk: RiskReport, debt: DebtReport, *, backend: str = "heuristic") -> RefactorPlan:
    steps: list[RefactorStep] = []
    for fp in risk.failure_points:
        wave = _wave_for(fp.kind)
        rid = f"R{len(steps)+1}"
        actions = [
            fp.suggested_intervention or "Inspect and reduce coupling",
            f"Target path/clade: {fp.path} / {fp.clade_id}",
        ]
        if fp.kind == "test_gap":
            actions.append("Add tests for top hot files before new features")
        if fp.kind == "revert_surface":
            actions.append("Quarantine change surface behind feature flags if needed")
        if fp.kind == "selection_pressure":
            actions.append("Triage bug-labeled issues; reduce reopen loops before feature work")
        criteria = [
            f"Severity signal for {fp.id} reduced on next CodeEvolve run",
            "No new revert cluster on the same path in the following window",
        ]
        if fp.kind == "test_gap":
            criteria.append("Test touch ratio rises relative to production churn")
        blast = 0.0
        for ev in fp.evidence:
            if isinstance(ev, dict) and "co_changers" in ev:
                blast = min(1.0, float(ev["co_changers"]) / 40.0)
        steps.append(
            RefactorStep(
                id=rid,
                title=fp.title,
                priority=priority_for(fp.severity, wave),
                wave=wave,
                clade_ids=[fp.clade_id] if fp.clade_id else [],
                paths=[fp.path] if fp.path else [],
                problem_kind=fp.kind,
                evidence_refs=[fp.id],
                actions=actions,
                acceptance_criteria=criteria,
                estimated_effort=estimate_effort(fp.severity, blast),
                expected_fitness_gain=expected_fitness_gain(fp.severity),
            )
        )

    # Ensure debt mistakes appear if not already covered
    covered = {e for s in steps for e in s.evidence_refs}
    for m in debt.architectural_mistakes:
        mid = str(m.get("id") or "arch")
        # already mirrored into risk usually
        if any(mid == s.problem_kind for s in steps):
            continue
        wid = f"DEB-{mid}"
        if wid in covered:
            continue
        steps.append(
            RefactorStep(
                id=f"R{len(steps)+1}",
                title=str(m.get("title") or mid),
                priority="P1",
                wave="contain",
                clade_ids=["global"],
                paths=[],
                problem_kind=mid,
                evidence_refs=[wid],
                actions=[str(m.get("why") or "Address architectural smell"), "Schedule containment refactor"],
                acceptance_criteria=["Mistake no longer flagged at current thresholds"],
                estimated_effort="M",
                expected_fitness_gain=0.15,
            )
        )

    # Sequencing: stabilize before others
    stabilize_ids = [s.id for s in steps if s.wave == "stabilize"]
    for s in steps:
        if s.wave != "stabilize" and stabilize_ids:
            s.depends_on = stabilize_ids[:1]

    md_lines = [
        "# CodeEvolve Refactor Plan",
        "",
        f"_Backend: {backend}_",
        "",
        "Phased waves: **stabilize → contain → pay_down → evolve**. "
        "Each step cites analysis evidence IDs.",
        "",
    ]
    by_wave: dict[str, list[RefactorStep]] = {w: [] for w in WAVE_ORDER}
    for s in steps:
        by_wave.setdefault(s.wave, []).append(s)
    for wave in WAVE_ORDER:
        md_lines.append(f"## {wave.replace('_', ' ').title()}")
        md_lines.append("")
        chunk = by_wave.get(wave) or []
        if not chunk:
            md_lines.append("_No steps in this wave._")
            md_lines.append("")
            continue
        for s in chunk:
            md_lines.append(f"### {s.id} — {s.title} ({s.priority}, effort {s.estimated_effort})")
            md_lines.append(f"- Problem: `{s.problem_kind}`")
            md_lines.append(f"- Evidence: {', '.join(s.evidence_refs)}")
            if s.paths:
                md_lines.append(f"- Paths: {', '.join(s.paths[:5])}")
            md_lines.append(f"- Expected fitness gain: {s.expected_fitness_gain}")
            if s.depends_on:
                md_lines.append(f"- Depends on: {', '.join(s.depends_on)}")
            md_lines.append("- Actions:")
            for a in s.actions:
                md_lines.append(f"  - {a}")
            md_lines.append("- Acceptance:")
            for c in s.acceptance_criteria:
                md_lines.append(f"  - {c}")
            md_lines.append("")

    return RefactorPlan(waves=[], steps=steps, markdown="\n".join(md_lines), backend=backend)
