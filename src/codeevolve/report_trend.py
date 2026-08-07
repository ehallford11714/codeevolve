"""Top-down planner + SLM/cloud (or heuristic) global trend report writer."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class PlanOutline:
    sections: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"sections": list(self.sections), "priorities": list(self.priorities)}


@dataclass
class TrendReport:
    outline: PlanOutline
    markdown: str
    backend: str
    bullets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "outline": self.outline.to_dict(),
            "bullets": list(self.bullets),
            "markdown": self.markdown,
        }


class ReportBackend(Protocol):
    name: str

    def write(self, outline: PlanOutline, context: dict[str, Any]) -> str: ...


def top_down_plan(context: dict[str, Any]) -> PlanOutline:
    """Deterministic planner: decide section order from signals."""
    metrics = context.get("metrics") or {}
    debt = context.get("debt") or {}
    phylo = context.get("phylogeny") or {}
    sem = context.get("semantics") or {}

    sections = [
        "Executive summary",
        "Rate of change & momentum",
        "Revert rate & stability",
        "Semantic trends & taxonomy",
        "Phylogeny & ecological stage",
        "Dependency churn",
        "Technical debt & deprecations",
        "Architectural mistakes (historical)",
        "Improvement trends",
        "Recommended next moves",
    ]
    priorities: list[str] = []
    if (metrics.get("revert_rate") or 0) > 0.1:
        priorities.append("Stabilize revert hotspots before new feature velocity")
    if (debt.get("score") or 0) > 0.4:
        priorities.append("Pay down deprecation/TODO debt in hot files")
    if (metrics.get("dependency_rate") or 0) > 0.15:
        priorities.append("Audit dependency churn and pin critical packages")
    if (sem.get("semantic_drift") or 0) > 0.35:
        priorities.append("Document semantic drift — themes are shifting quickly")
    stage = phylo.get("current_stage")
    if stage == "disturbance":
        priorities.append("Enter consolidation: increase tests, reduce blast radius")
    elif stage == "growth":
        priorities.append("Protect architecture boundaries while growth continues")
    elif stage == "maturity":
        priorities.append("Invest in observability and deliberate refactors")
    if not priorities:
        priorities.append("Maintain current trajectory; monitor hot files")
    return PlanOutline(sections=sections, priorities=priorities)


class HeuristicBackend:
    name = "heuristic"

    def write(self, outline: PlanOutline, context: dict[str, Any]) -> str:
        m = context.get("metrics") or {}
        d = context.get("debt") or {}
        p = context.get("phylogeny") or {}
        s = context.get("semantics") or {}
        repo = context.get("repo", ".")
        themes = s.get("theme_distribution") or {}
        top_themes = ", ".join(f"{k}={v:.0%}" for k, v in list(themes.items())[:5]) or "n/a"
        mistakes = d.get("architectural_mistakes") or []
        mist_lines = "\n".join(
            f"- **{x.get('title')}** ({x.get('severity')}): {x.get('why')}" for x in mistakes[:5]
        ) or "- None flagged at MVP thresholds."

        lines = [
            f"# CodeEvolve Trend Report — `{repo}`",
            "",
            f"_Backend: {self.name}_",
            "",
            "## Executive summary",
            (
                f"The repository is in ecological stage **{p.get('current_stage', 'unknown')}** "
                f"({p.get('stage_rationale', '')}). "
                f"Stability={m.get('code_stability')}, revert_rate={m.get('revert_rate')}, "
                f"momentum={m.get('momentum')}, debt_score={d.get('score')}."
            ),
            "",
            "## Priorities (planner)",
            *[f"- {x}" for x in outline.priorities],
            "",
            "## Rate of change & momentum",
            (
                f"Across {m.get('commit_count')} commits, total churn={m.get('churn_total')} "
                f"(avg {m.get('avg_churn_per_commit')}/commit). "
                f"Momentum={m.get('momentum')} (recent vs older churn). "
                f"Improvement trend={m.get('improvement_trend')}."
            ),
            "",
            "## Revert rate & stability",
            (
                f"Reverts={m.get('revert_count')} ({m.get('revert_rate'):.1%} of commits). "
                f"Code stability score={m.get('code_stability')} (higher is healthier)."
            ),
            "",
            "## Semantic trends & taxonomy",
            f"Theme mix: {top_themes}. Semantic drift={s.get('semantic_drift')}.",
            "Hierarchy root layers are summarized in the JSON report under `semantics.hierarchy`.",
            "",
            "## Phylogeny & ecological stage",
            (
                f"Max generation={p.get('max_generation')}, branch_factor={p.get('branch_factor')}, "
                f"merges={p.get('merge_count')}. Current stage: **{p.get('current_stage')}**."
            ),
            "",
            "## Dependency churn",
            (
                f"Dependency-related commits={m.get('dependency_change_commits')} "
                f"(rate={m.get('dependency_rate')})."
            ),
            "",
            "## Technical debt & deprecations",
            d.get("summary") or "No debt summary.",
            "",
            "## Architectural mistakes (historical)",
            mist_lines,
            "",
            "## Improvement trends",
            (
                "Positive improvement_trend means recent windows show fewer reverts and/or cooler churn "
                f"relative to earlier history (value={m.get('improvement_trend')})."
            ),
            "",
            "## Recommended next moves",
            *[f"{i+1}. {x}" for i, x in enumerate(outline.priorities)],
            "",
        ]
        return "\n".join(lines)


class OpenAICompatibleBackend:
    name = "openai_compatible"

    def __init__(self) -> None:
        self.api_key = os.environ.get("CODEEVOLVE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = (os.environ.get("CODEEVOLVE_LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("CODEEVOLVE_LLM_MODEL") or "gpt-4o-mini"

    def write(self, outline: PlanOutline, context: dict[str, Any]) -> str:
        if not self.api_key:
            return HeuristicBackend().write(outline, context)
        system = (
            "You are CodeEvolve, a principal engineer writing a global code-evolution trend report. "
            "Follow the provided top-down outline. Be specific, cite the numeric signals, "
            "call out architectural mistakes and momentum. Output Markdown only."
        )
        user = {
            "outline": outline.to_dict(),
            "signals": {
                "metrics": context.get("metrics"),
                "debt": {
                    "score": (context.get("debt") or {}).get("score"),
                    "summary": (context.get("debt") or {}).get("summary"),
                    "architectural_mistakes": (context.get("debt") or {}).get("architectural_mistakes"),
                },
                "phylogeny": {
                    "current_stage": (context.get("phylogeny") or {}).get("current_stage"),
                    "stage_rationale": (context.get("phylogeny") or {}).get("stage_rationale"),
                    "branch_factor": (context.get("phylogeny") or {}).get("branch_factor"),
                    "stages": (context.get("phylogeny") or {}).get("stages"),
                },
                "semantics": {
                    "theme_distribution": (context.get("semantics") or {}).get("theme_distribution"),
                    "semantic_drift": (context.get("semantics") or {}).get("semantic_drift"),
                },
                "repo": context.get("repo"),
            },
        }
        payload = {
            "model": self.model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError, TimeoutError):
            return HeuristicBackend().write(outline, context)


def get_backend(use_llm: bool = False) -> ReportBackend:
    if use_llm or os.environ.get("CODEEVOLVE_USE_LLM", "").lower() in {"1", "true", "yes"}:
        return OpenAICompatibleBackend()
    return HeuristicBackend()


def write_trend_report(context: dict[str, Any], *, use_llm: bool = False) -> TrendReport:
    outline = top_down_plan(context)
    backend = get_backend(use_llm=use_llm)
    md = backend.write(outline, context)
    return TrendReport(
        outline=outline,
        markdown=md,
        backend=backend.name,
        bullets=list(outline.priorities),
    )
