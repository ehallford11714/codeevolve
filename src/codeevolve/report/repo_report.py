"""Drafted full repository evolution report."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codeevolve.models.backends import get_narrative_backend
from codeevolve.models.router import resolve_backend_name


@dataclass
class RepoReportDoc:
    markdown: str
    backend: str
    sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "sections": list(self.sections),
            "markdown": self.markdown,
        }


def _template(ctx: dict[str, Any]) -> str:
    m = ctx.get("metrics") or {}
    d = ctx.get("debt") or {}
    p = ctx.get("phylogeny") or {}
    e = ctx.get("ecology") or {}
    t = ctx.get("taxonomy") or {}
    g = ctx.get("genetics") or {}
    r = ctx.get("risk") or {}
    s = ctx.get("semantics") or {}
    sym = ctx.get("symbols") or {}
    sel = ctx.get("selection") or {}
    fat = ctx.get("fatigue") or {}
    load = ctx.get("cognitive_load") or {}
    drift = ctx.get("drift") or {}
    stab = ctx.get("stability") or {}
    repo = ctx.get("repo", ".")
    tier = ctx.get("model_tier") or (ctx.get("tier") or {}).get("name") or "slm"
    lehman = e.get("lehman") or {}
    niches = (e.get("niches") or {}).get("overcrowded") or []
    weaknesses = r.get("failure_points") or []
    weak_lines = "\n".join(
        f"- **{w.get('id')}** ({w.get('severity')}): {w.get('title')} — `{w.get('path')}`"
        for w in weaknesses[:12]
    ) or "- None ranked."
    clade_lines = "\n".join(
        f"- `{c.get('id')}` **{c.get('label')}** ({c.get('layer')}): "
        f"{c.get('role') or ''} · {c.get('file_count')} files, churn={c.get('churn')}"
        for c in (t.get("clades") or [])[:10]
    ) or "- No clades."
    drift_lines = "\n".join(
        f"- `{d.get('clade_id')}` {d.get('label')}: drift={d.get('drift')}"
        for d in (drift.get("clade_drift") or [])[:8]
    ) or "- n/a"
    stage_lines = "\n".join(
        f"- `{c.get('clade_id')}` → **{c.get('stage')}** — {c.get('rationale')}"
        for c in (e.get("clade_stages") or [])[:10]
    ) or "- n/a"
    mist = d.get("architectural_mistakes") or []
    mist_lines = "\n".join(
        f"- **{x.get('title')}** ({x.get('severity')}): {x.get('why')}" for x in mist[:6]
    ) or "- None flagged."

    return "\n".join(
        [
            f"# CodeEvolve Repository Report — `{repo}`",
            "",
            f"_Model tier: **{tier}** · taxonomy guide: {(t.get('guidance') or {}).get('engine') or (t.get('guidance') or {}).get('model')}_",
            "",
            "## Executive summary",
            (
                f"Stage **{e.get('global_stage') or p.get('current_stage')}** "
                f"(hypothesis — {e.get('stage_rationale') or p.get('stage_rationale')}). "
                f"Composite stability={stab.get('composite', m.get('code_stability'))}, "
                f"revert_rate={m.get('revert_rate')}, debt={d.get('score')}, "
                f"drift={drift.get('global_drift')}, fatigue={fat.get('fatigue_score')}, "
                f"cognitive_load={load.get('load_index')}, "
                f"failure_points={r.get('count', len(weaknesses))}."
            ),
            "",
            f"Hero signals: {(ctx.get('signal_confidence') or {}).get('hero_ranking')}; "
            f"{(ctx.get('signal_confidence') or {}).get('summary') or ''}",
            "",
            "## Stability decomposition",
            f"- Structural: {stab.get('structural')}",
            f"- Behavioral: {stab.get('behavioral')}",
            f"- Dependency: {stab.get('dependency')}",
            f"- Test: {stab.get('test')}",
            f"- Rhythm: {stab.get('rhythm')}",
            f"- Composite: {stab.get('composite')}",
            "",
            "## Taxonomy map (SLM-guided)",
            f"Files indexed: {t.get('file_count')}. Layers: {t.get('layers')}.",
            f"Languages: {t.get('languages')}. Guidance: {t.get('guidance')}.",
            "",
            clade_lines,
            "",
            "### Word2Vec / semantic niches",
            ((t.get("word2vec") or {}).get("summary") or "_word2vec n/a_"),
            ((t.get("semantic") or {}).get("summary") or "_semantic taxonomy n/a_"),
            (
                "Niches: "
                + ", ".join(
                    f"{n.get('id')}:{n.get('label')}"
                    for n in ((t.get("semantic") or {}).get("niches") or [])[:8]
                )
            ),
            "",
            "## Sprint & fatigue trends",
            fat.get("summary") or "_n/a_",
            f"After-hours={fat.get('after_hours_rate')}, weekend={fat.get('weekend_rate')}, "
            f"intensity_creep={fat.get('intensity_creep')}, recovery_ratio={fat.get('recovery_ratio')}.",
            "",
            "## Cognitive & ownership load",
            load.get("summary") or "_n/a_",
            "",
            "## Genetic drift",
            drift.get("summary") or "_n/a_",
            "",
            drift_lines,
            "",
            "## Evolutionary history",
            f"Commits={m.get('commit_count')}, churn={m.get('churn_total')}, "
            f"momentum={m.get('momentum')}, improvement_trend={m.get('improvement_trend')}.",
            f"Timeline windows: {e.get('timeline')}.",
            "",
            "### Lehman proxies (not grades)",
            f"- Continuing change: {lehman.get('continuing_change')}",
            f"- Increasing complexity: {lehman.get('increasing_complexity')}",
            f"- Continuing growth: {lehman.get('continuing_growth')}",
            f"- Declining quality: {lehman.get('declining_quality')}",
            f"- Conservation of familiarity: {lehman.get('conservation_of_familiarity')}",
            f"- Feedback volatility: {lehman.get('feedback_volatility')}",
            f"- Self regulation: {lehman.get('self_regulation')}",
            f"- Organisational stability: {lehman.get('organisational_stability')}",
            "",
            "### Hypothesis panel",
            (ctx.get("hypothesis_panel") or {}).get("disclaimer") or "",
            (ctx.get("hypothesis_panel") or {}).get("summary") or "_n/a_",
            (
                "Claims: "
                + ", ".join(
                    f"{c.get('id')}={c.get('verdict')}@{c.get('confidence')}"
                    for c in ((ctx.get("hypothesis_panel") or {}).get("claims") or [])[:8]
                )
            ),
            "",
            "### Lehman trend tests (Mann–Kendall)",
            (
                f"Support map: {(e.get('lehman_trends') or {}).get('law_support')}; "
                f"{(e.get('lehman_trends') or {}).get('summary') or '_n/a_'}"
            ),
            "",
            "## Coupling, clones & reticulation",
            (ctx.get("coupling") or {}).get("summary") or "_n/a_",
            (ctx.get("clones") or {}).get("summary") or "_n/a_",
            (ctx.get("reticulation") or {}).get("summary") or "_n/a_",
            (ctx.get("cst_evolution") or {}).get("summary") or "_n/a_",
            "",
            "## Dependencies & offboarding",
            (ctx.get("dependencies") or {}).get("summary") or "_n/a_",
            (ctx.get("offboarding") or {}).get("summary") or "_n/a_",
            (ctx.get("fork_lineage") or {}).get("summary") or "_n/a_",
            "",
            "## Phylogeny & gene flow",
            (
                f"Max generation={p.get('max_generation')}, branch_factor={p.get('branch_factor')}, "
                f"merges={p.get('merge_count')}, hybridization={g.get('hybridization_events')}, "
                f"HGT suspects={len(g.get('hgt_suspects') or [])}, "
                f"renames={g.get('rename_events')}."
            ),
            "",
            "### Clade stages",
            stage_lines,
            "",
            f"Overcrowded niches: {niches or 'none'}.",
            "",
            "## Symbols",
            (
                f"Engine={sym.get('engine')}, symbols={sym.get('symbol_count')}, "
                f"kinds={sym.get('kind_counts')}."
            ),
            "",
            "## Selection pressure (GitHub Issues/PRs)",
            (
                f"pressure_score={sel.get('pressure_score')}, "
                f"bug_label_rate={sel.get('bug_label_rate')}, "
                f"open_issues={sel.get('open_issues')}, "
                f"pr_merge_rate={sel.get('pr_merge_rate')}."
                if sel
                else "_Not a GitHub remote / selection skipped._"
            ),
            "",
            "## Debt & architectural mistakes",
            d.get("summary") or "No debt summary.",
            "",
            mist_lines,
            "",
            "## Weaknesses & failure points",
            r.get("summary") or "",
            "",
            weak_lines,
            "",
            "## Semantic trends",
            f"Themes: {s.get('theme_distribution')}. Drift={s.get('semantic_drift')}.",
            "",
            "## Momentum & improvement",
            (
                f"Momentum={m.get('momentum')}, improvement_trend={m.get('improvement_trend')}, "
                f"dependency_rate={m.get('dependency_rate')}."
            ),
            "",
            "## Appendix",
            "See JSON fields `taxonomy`, `genetics`, `ecology`, `risk`, `debt`, `metrics` for evidence.",
            "",
        ]
    )


def write_repo_report(context: dict[str, Any], *, llm: str | bool | None = False) -> RepoReportDoc:
    sections = [
        "Executive summary",
        "Stability decomposition",
        "Taxonomy map (SLM-guided)",
        "Sprint & fatigue trends",
        "Cognitive & ownership load",
        "Genetic drift",
        "Evolutionary history",
        "Phylogeny & gene flow",
        "Debt & architectural mistakes",
        "Weaknesses & failure points",
        "Momentum & improvement",
        "Appendix",
    ]
    backend_name = resolve_backend_name(llm)
    md = _template(context)
    if backend_name != "heuristic":
        narr = get_narrative_backend(llm)
        polished = narr.write(
            "You are CodeEvolve. Rewrite the repository evolution report in clear Markdown. "
            "Keep all numeric evidence. Structure: Summary, Taxonomy, History, Phylogeny, "
            "Debt, Weaknesses, Momentum. Do not invent files.",
            {"draft": md, "signals": {k: context.get(k) for k in ("metrics", "ecology", "risk", "debt")}},
        )
        # Keep templated draft if polish failed / returned JSON dump fallback
        looks_real = bool(
            polished
            and "Executive summary" in polished
            and "System intent:" not in polished
            and not polished.lstrip().startswith("# Narrative")
        )
        if looks_real:
            md = polished
            backend_name = narr.name
        else:
            backend_name = f"{narr.name}+template"
    else:
        backend_name = "heuristic"
    return RepoReportDoc(markdown=md, backend=backend_name, sections=sections)
