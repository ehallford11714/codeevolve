"""Public CodeEvolve facade."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from codeevolve.debt import DebtReport, analyze_debt
from codeevolve.ecology import EcologyReport, analyze_ecology
from codeevolve.genetics import GeneticsReport, analyze_genetics
from codeevolve.genetics.drift import DriftReport, analyze_drift
from codeevolve.gitlog import CommitRecord, load_commits
from codeevolve.ingest import resolve_repo
from codeevolve.ingest.github import github_owner_repo
from codeevolve.ingest.github_api import SelectionPressure, fetch_selection_pressure
from codeevolve.metrics import MetricBundle, change_rate_timeline, compute_metrics
from codeevolve.metrics_stability import StabilityBundle, compute_stability_v2
from codeevolve.models.hardware import HardwareProfile, assess_hardware, recommend_execution
from codeevolve.models.hf_qwen import ensure_hf_qwen
from codeevolve.models.tiers import apply_tier_env, resolve_tier, tier_spec
from codeevolve.phylogeny import PhylogenyReport, analyze_phylogeny
from codeevolve.psychology import CognitiveLoadReport, FatigueReport, analyze_cognitive_load, analyze_fatigue
from codeevolve.refactor import RefactorPlan, build_refactor_plan
from codeevolve.report import RepoReportDoc, TrendReport, write_repo_report, write_trend_report
from codeevolve.risk import RiskReport, analyze_risk
from codeevolve.risk.blast_radius import blast_radius_table
from codeevolve.semantics import SemanticReport, analyze_semantics
from codeevolve.taxonomy import TaxonomyReport, build_taxonomy
from codeevolve.taxonomy.symbols import SymbolReport, extract_symbols


@dataclass
class EvolveReport:
    repo: str
    local_path: str
    metrics: MetricBundle
    semantics: SemanticReport
    phylogeny: PhylogenyReport
    debt: DebtReport
    taxonomy: TaxonomyReport
    genetics: GeneticsReport
    ecology: EcologyReport
    risk: RiskReport
    symbols: Optional[SymbolReport] = None
    selection: Optional[SelectionPressure] = None
    fatigue: Optional[FatigueReport] = None
    cognitive_load: Optional[CognitiveLoadReport] = None
    drift: Optional[DriftReport] = None
    stability: Optional[StabilityBundle] = None
    model_tier: str = "slm"
    blast_radius: list[dict[str, Any]] = field(default_factory=list)
    change_timeline: list[dict[str, Any]] = field(default_factory=list)
    trend: Optional[TrendReport] = None
    repo_report: Optional[RepoReportDoc] = None
    refactor_plan: Optional[RefactorPlan] = None
    hardware: Optional[dict[str, Any]] = None
    commit_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "local_path": self.local_path,
            "commit_count": self.commit_count,
            "model_tier": self.model_tier,
            "metrics": self.metrics.to_dict(),
            "stability": self.stability.to_dict() if self.stability else None,
            "semantics": self.semantics.to_dict(),
            "phylogeny": self.phylogeny.to_dict(),
            "taxonomy": self.taxonomy.to_dict(),
            "symbols": self.symbols.to_dict() if self.symbols else None,
            "genetics": self.genetics.to_dict(),
            "drift": self.drift.to_dict() if self.drift else None,
            "ecology": self.ecology.to_dict(),
            "debt": self.debt.to_dict(),
            "risk": self.risk.to_dict(),
            "selection": self.selection.to_dict() if self.selection else None,
            "fatigue": self.fatigue.to_dict() if self.fatigue else None,
            "cognitive_load": self.cognitive_load.to_dict() if self.cognitive_load else None,
            "blast_radius": list(self.blast_radius),
            "change_timeline": list(self.change_timeline),
            "trend": self.trend.to_dict() if self.trend else None,
            "repo_report": self.repo_report.to_dict() if self.repo_report else None,
            "refactor_plan": self.refactor_plan.to_dict() if self.refactor_plan else None,
            "hardware": self.hardware,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


class CodeEvolve:
    """Analyze a git repository's evolutionary dynamics (local path or GitHub URL)."""

    def __init__(
        self,
        repo: Path | str = ".",
        *,
        clone_depth: int = 200,
        full_history: bool = False,
        model_tier: str = "slm",
        model: str | None = None,
    ) -> None:
        self._spec = str(repo)
        self._clone_depth = clone_depth
        self.model_tier = resolve_tier(model_tier)
        self.model_override = model
        apply_tier_env(self.model_tier, model_override=model)
        path, display = resolve_repo(repo, depth=clone_depth, full_history=full_history)
        self.repo = path
        self.display = display
        self._gh = github_owner_repo(self._spec) or github_owner_repo(display)

    def analyze(
        self,
        *,
        max_commits: int = 400,
        since: str | None = None,
        write_report: bool = True,
        use_llm: Union[bool, str, None] = None,
        scan_debt_files: int = 300,
        include_repo_report: bool = True,
        include_refactor: bool = True,
        include_hardware: bool = True,
        include_symbols: bool = True,
        include_selection: bool = True,
        max_symbol_files: int = 400,
        guide_taxonomy: bool = True,
    ) -> EvolveReport:
        apply_tier_env(self.model_tier, model_override=self.model_override)
        # Default narrative polish follows tier (SLM) unless explicitly disabled
        if use_llm is None:
            use_llm = self.model_tier  # slm|standard|large|frontier → backends via name or auto

        commits = load_commits(self.repo, max_commits=max_commits, since=since)
        metrics = compute_metrics(commits)
        semantics = analyze_semantics(commits)
        phylogeny = analyze_phylogeny(commits, metrics)
        taxonomy = build_taxonomy(
            self.repo,
            commits,
            model_tier=self.model_tier,
            model_override=self.model_override,
            guide=guide_taxonomy,
        )
        genetics = analyze_genetics(commits, taxonomy)
        ecology = analyze_ecology(commits, metrics, taxonomy)
        drift = analyze_drift(commits, taxonomy)
        fatigue = analyze_fatigue(commits)
        load = analyze_cognitive_load(commits, taxonomy)
        stability = compute_stability_v2(commits, metrics, taxonomy, fatigue, load)
        debt = analyze_debt(
            self.repo,
            commits,
            hot_files=metrics.hot_files,
            max_files=scan_debt_files,
        )

        selection = None
        if include_selection and self._gh is not None:
            selection = fetch_selection_pressure(self._gh[0], self._gh[1])

        risk = analyze_risk(
            commits,
            metrics,
            taxonomy,
            genetics,
            debt,
            selection=selection,
            fatigue=fatigue,
            cognitive_load=load,
        )
        symbols = extract_symbols(self.repo, max_files=max_symbol_files) if include_symbols else None
        blast = blast_radius_table(commits)
        timeline = change_rate_timeline(commits)

        ctx = {
            "repo": self.display,
            "model_tier": self.model_tier,
            "tier": tier_spec(self.model_tier).to_dict(),
            "metrics": metrics.to_dict(),
            "stability": stability.to_dict(),
            "semantics": semantics.to_dict(),
            "phylogeny": phylogeny.to_dict(),
            "taxonomy": taxonomy.to_dict(),
            "symbols": symbols.to_dict() if symbols else None,
            "genetics": genetics.to_dict(),
            "drift": drift.to_dict(),
            "ecology": ecology.to_dict(),
            "debt": debt.to_dict(),
            "risk": risk.to_dict(),
            "selection": selection.to_dict() if selection else None,
            "fatigue": fatigue.to_dict(),
            "cognitive_load": load.to_dict(),
            "blast_radius": blast,
        }

        llm_flag: Union[bool, str] = use_llm if use_llm is not False else False
        if use_llm is False:
            llm_flag = False
        elif isinstance(use_llm, str) and use_llm in {"slm", "standard", "large", "frontier"}:
            # map tier name to backend preference
            llm_flag = "hf-qwen" if use_llm in {"slm", "standard"} else "auto"

        trend = write_trend_report(ctx, use_llm=bool(llm_flag)) if write_report else None
        repo_doc = write_repo_report(ctx, llm=llm_flag if llm_flag else False) if include_repo_report else None
        refactor = build_refactor_plan(risk, debt) if include_refactor else None

        hw = None
        if include_hardware:
            profile = assess_hardware()
            hw = {
                "profile": profile.to_dict(),
                "recommendation": recommend_execution(profile),
                "hf_qwen": ensure_hf_qwen(profile.recommended_model),
                "tier": tier_spec(self.model_tier).to_dict(),
            }

        return EvolveReport(
            repo=self.display,
            local_path=str(self.repo),
            metrics=metrics,
            semantics=semantics,
            phylogeny=phylogeny,
            debt=debt,
            taxonomy=taxonomy,
            genetics=genetics,
            ecology=ecology,
            risk=risk,
            symbols=symbols,
            selection=selection,
            fatigue=fatigue,
            cognitive_load=load,
            drift=drift,
            stability=stability,
            model_tier=self.model_tier,
            blast_radius=blast,
            change_timeline=timeline,
            trend=trend,
            repo_report=repo_doc,
            refactor_plan=refactor,
            hardware=hw,
            commit_count=len(commits),
        )

    def commits(self, *, max_commits: int = 100, since: str | None = None) -> list[CommitRecord]:
        return load_commits(self.repo, max_commits=max_commits, since=since)

    @staticmethod
    def hardware() -> HardwareProfile:
        return assess_hardware()
