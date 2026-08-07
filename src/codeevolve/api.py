"""Public CodeEvolve facade."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from codeevolve.ci import CiGateResult, evaluate_ci_gate
from codeevolve.complexity import enrich_hotspots
from codeevolve.dashboard import write_dashboard
from codeevolve.debt import DebtReport, analyze_debt
from codeevolve.ecology import EcologyReport, analyze_ecology
from codeevolve.eval.confidence import SignalConfidenceReport, score_signal_confidence
from codeevolve.eval.hypothesis import HypothesisPanel, build_hypothesis_panel
from codeevolve.genetics import GeneticsReport, analyze_genetics
from codeevolve.genetics.clones import CloneGenealogyReport, analyze_clone_genealogy
from codeevolve.genetics.drift import DriftReport, analyze_drift
from codeevolve.genetics.reticulation import ReticulationReport, analyze_reticulation
from codeevolve.gitlog import CommitRecord, load_commits
from codeevolve.ingest import resolve_repo
from codeevolve.ingest.fork_lineage import ForkLineageReport, analyze_fork_lineage
from codeevolve.ingest.github import github_owner_repo
from codeevolve.ingest.github_api import SelectionPressure, fetch_selection_pressure
from codeevolve.metrics import MetricBundle, change_rate_timeline, compute_metrics
from codeevolve.metrics_stability import StabilityBundle, compute_stability_v2
from codeevolve.models.hardware import HardwareProfile, assess_hardware, recommend_execution
from codeevolve.models.hf_qwen import ensure_hf_qwen
from codeevolve.models.slm import ensure_default_slm
from codeevolve.models.tiers import apply_tier_env, resolve_tier, tier_spec
from codeevolve.phylogeny import PhylogenyReport, analyze_phylogeny
from codeevolve.pr_comment import render_pr_comment
from codeevolve.psychology import CognitiveLoadReport, FatigueReport, analyze_cognitive_load, analyze_fatigue
from codeevolve.psychology.offboarding import OffboardingReport, simulate_offboarding
from codeevolve.psychology.sprints import SprintReport, analyze_sprints
from codeevolve.refactor import RefactorPlan, build_refactor_plan
from codeevolve.report import RepoReportDoc, TrendReport, write_repo_report, write_trend_report
from codeevolve.report.diff import ReportDiff, diff_reports, load_previous
from codeevolve.risk import RiskReport, analyze_risk
from codeevolve.risk.blast_radius import blast_radius_table
from codeevolve.risk.coupling import CouplingReport, analyze_coupling
from codeevolve.risk.dependencies import DependencyFragilityReport, analyze_dependency_fragility
from codeevolve.semantics import SemanticReport, analyze_semantics
from codeevolve.taxonomy import TaxonomyReport, build_taxonomy
from codeevolve.taxonomy.cst import CstEvolutionReport, analyze_cst_evolution
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
    sprints: Optional[SprintReport] = None
    diff: Optional[ReportDiff] = None
    coupling: Optional[CouplingReport] = None
    clones: Optional[CloneGenealogyReport] = None
    reticulation: Optional[ReticulationReport] = None
    cst_evolution: Optional[CstEvolutionReport] = None
    dependencies: Optional[DependencyFragilityReport] = None
    offboarding: Optional[OffboardingReport] = None
    fork_lineage: Optional[ForkLineageReport] = None
    hypothesis_panel: Optional[HypothesisPanel] = None
    signal_confidence: Optional[SignalConfidenceReport] = None
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
            "cst_evolution": self.cst_evolution.to_dict() if self.cst_evolution else None,
            "genetics": self.genetics.to_dict(),
            "clones": self.clones.to_dict() if self.clones else None,
            "reticulation": self.reticulation.to_dict() if self.reticulation else None,
            "drift": self.drift.to_dict() if self.drift else None,
            "ecology": self.ecology.to_dict(),
            "debt": self.debt.to_dict(),
            "risk": self.risk.to_dict(),
            "coupling": self.coupling.to_dict() if self.coupling else None,
            "dependencies": self.dependencies.to_dict() if self.dependencies else None,
            "offboarding": self.offboarding.to_dict() if self.offboarding else None,
            "fork_lineage": self.fork_lineage.to_dict() if self.fork_lineage else None,
            "hypothesis_panel": self.hypothesis_panel.to_dict() if self.hypothesis_panel else None,
            "signal_confidence": self.signal_confidence.to_dict() if self.signal_confidence else None,
            "selection": self.selection.to_dict() if self.selection else None,
            "fatigue": self.fatigue.to_dict() if self.fatigue else None,
            "cognitive_load": self.cognitive_load.to_dict() if self.cognitive_load else None,
            "sprints": self.sprints.to_dict() if self.sprints else None,
            "diff": self.diff.to_dict() if self.diff else None,
            "blast_radius": list(self.blast_radius),
            "change_timeline": list(self.change_timeline),
            "trend": self.trend.to_dict() if self.trend else None,
            "repo_report": self.repo_report.to_dict() if self.repo_report else None,
            "refactor_plan": self.refactor_plan.to_dict() if self.refactor_plan else None,
            "hardware": self.hardware,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def pr_comment(self) -> str:
        return render_pr_comment(self.to_dict(), diff=self.diff.to_dict() if self.diff else None)


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
        include_cst: bool = True,
        include_clones: bool = True,
        include_reticulation: bool = True,
        include_fork_lineage: bool = True,
        peer_repos: list[Path | str] | None = None,
        max_symbol_files: int = 400,
        guide_taxonomy: bool = True,
        include_semantic: bool = True,
        vector_backend: str | None = None,
        previous_report: Path | str | None = None,
        ensure_slm: bool = True,
    ) -> EvolveReport:
        apply_tier_env(self.model_tier, model_override=self.model_override)
        if ensure_slm and self.model_tier in {"slm", "standard"}:
            ensure_default_slm()

        if use_llm is None:
            use_llm = self.model_tier

        commits = load_commits(self.repo, max_commits=max_commits, since=since)
        metrics = compute_metrics(commits)
        metrics.hot_files = enrich_hotspots(self.repo, metrics.hot_files)

        semantics = analyze_semantics(commits)
        phylogeny = analyze_phylogeny(commits, metrics)
        taxonomy = build_taxonomy(
            self.repo,
            commits,
            model_tier=self.model_tier,
            model_override=self.model_override,
            guide=guide_taxonomy,
            include_semantic=include_semantic,
            vector_backend=vector_backend,
            display=self.display,
        )
        genetics = analyze_genetics(commits, taxonomy)
        ecology = analyze_ecology(commits, metrics, taxonomy)
        symbols = extract_symbols(self.repo, max_files=max_symbol_files) if include_symbols else None
        drift = analyze_drift(commits, taxonomy, symbols=symbols)
        fatigue = analyze_fatigue(commits)
        load = analyze_cognitive_load(commits, taxonomy)
        stability = compute_stability_v2(commits, metrics, taxonomy, fatigue, load)
        debt = analyze_debt(
            self.repo,
            commits,
            hot_files=metrics.hot_files,
            max_files=scan_debt_files,
        )

        coupling = analyze_coupling(commits)
        dependencies = analyze_dependency_fragility(self.repo, commits)
        offboarding = simulate_offboarding(commits, metrics)
        clones = analyze_clone_genealogy(self.repo, commits) if include_clones else None
        reticulation = analyze_reticulation(self.repo, commits) if include_reticulation else None
        cst = analyze_cst_evolution(self.repo, commits) if include_cst else None
        fork_lineage = (
            analyze_fork_lineage(self.repo, peer_repos=peer_repos) if include_fork_lineage else None
        )

        # Selection ON by default for GitHub URLs
        selection = None
        if include_selection and self._gh is not None:
            selection = fetch_selection_pressure(self._gh[0], self._gh[1])

        sprints = analyze_sprints(
            commits,
            owner=self._gh[0] if self._gh else None,
            repo=self._gh[1] if self._gh else None,
        )

        risk = analyze_risk(
            commits,
            metrics,
            taxonomy,
            genetics,
            debt,
            selection=selection,
            fatigue=fatigue,
            cognitive_load=load,
            coupling=coupling,
            dependencies=dependencies,
            offboarding=offboarding,
        )
        hypothesis_panel = build_hypothesis_panel(
            commits,
            metrics,
            ecology.lehman,
            ecology.lehman_trends,
            stage=ecology.global_stage,
            stage_rationale=ecology.stage_rationale,
        )
        signal_confidence = score_signal_confidence(commits, metrics, coupling, offboarding)
        blast = blast_radius_table(commits)
        timeline = change_rate_timeline(commits)

        prev = load_previous(previous_report) if previous_report else None
        diff = (
            diff_reports(
                {
                    "stability": stability.to_dict(),
                    "metrics": metrics.to_dict(),
                    "debt": debt.to_dict(),
                    "fatigue": fatigue.to_dict(),
                    "cognitive_load": load.to_dict(),
                    "drift": drift.to_dict(),
                    "risk": risk.to_dict(),
                    "dependencies": dependencies.to_dict(),
                    "offboarding": offboarding.to_dict(),
                    "coupling": coupling.to_dict(),
                },
                prev,
            )
            if prev
            else None
        )

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
            "cst_evolution": cst.to_dict() if cst else None,
            "genetics": genetics.to_dict(),
            "clones": clones.to_dict() if clones else None,
            "reticulation": reticulation.to_dict() if reticulation else None,
            "drift": drift.to_dict(),
            "ecology": ecology.to_dict(),
            "debt": debt.to_dict(),
            "risk": risk.to_dict(),
            "coupling": coupling.to_dict(),
            "dependencies": dependencies.to_dict(),
            "offboarding": offboarding.to_dict(),
            "fork_lineage": fork_lineage.to_dict() if fork_lineage else None,
            "hypothesis_panel": hypothesis_panel.to_dict(),
            "signal_confidence": signal_confidence.to_dict(),
            "selection": selection.to_dict() if selection else None,
            "fatigue": fatigue.to_dict(),
            "cognitive_load": load.to_dict(),
            "sprints": sprints.to_dict(),
            "diff": diff.to_dict() if diff else None,
            "blast_radius": blast,
        }

        llm_flag: Union[bool, str] = False
        if use_llm is False:
            llm_flag = False
        elif isinstance(use_llm, str) and use_llm in {"slm", "standard", "large", "frontier"}:
            llm_flag = "hf-qwen" if use_llm in {"slm", "standard"} else "auto"
        elif use_llm is None:
            llm_flag = "hf-qwen"
        else:
            llm_flag = use_llm  # type: ignore[assignment]

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
                "slm": ensure_default_slm(download=False),
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
            sprints=sprints,
            diff=diff,
            coupling=coupling,
            clones=clones,
            reticulation=reticulation,
            cst_evolution=cst,
            dependencies=dependencies,
            offboarding=offboarding,
            fork_lineage=fork_lineage,
            hypothesis_panel=hypothesis_panel,
            signal_confidence=signal_confidence,
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

    @staticmethod
    def ci_gate(report: dict[str, Any], previous: dict[str, Any] | None = None) -> CiGateResult:
        return evaluate_ci_gate(report, previous=previous)

    @staticmethod
    def write_dashboard(report: dict[str, Any], path: Path | str) -> Path:
        return write_dashboard(report, path)

    @staticmethod
    def evaluate(work_dir: Path | str | None = None):
        """Run synthetic-fixture evaluation suite (detection agreement scores)."""
        from codeevolve.eval.runner import run_evaluation

        return run_evaluation(work_dir)
