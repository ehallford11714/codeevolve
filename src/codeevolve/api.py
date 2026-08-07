"""Public CodeEvolve facade."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from codeevolve.debt import DebtReport, analyze_debt
from codeevolve.ecology import EcologyReport, analyze_ecology
from codeevolve.genetics import GeneticsReport, analyze_genetics
from codeevolve.gitlog import CommitRecord, load_commits
from codeevolve.ingest import resolve_repo
from codeevolve.metrics import MetricBundle, change_rate_timeline, compute_metrics
from codeevolve.models.hardware import HardwareProfile, assess_hardware, recommend_execution
from codeevolve.phylogeny import PhylogenyReport, analyze_phylogeny
from codeevolve.refactor import RefactorPlan, build_refactor_plan
from codeevolve.report import RepoReportDoc, TrendReport, write_repo_report, write_trend_report
from codeevolve.risk import RiskReport, analyze_risk
from codeevolve.semantics import SemanticReport, analyze_semantics
from codeevolve.taxonomy import TaxonomyReport, build_taxonomy


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
            "metrics": self.metrics.to_dict(),
            "semantics": self.semantics.to_dict(),
            "phylogeny": self.phylogeny.to_dict(),
            "taxonomy": self.taxonomy.to_dict(),
            "genetics": self.genetics.to_dict(),
            "ecology": self.ecology.to_dict(),
            "debt": self.debt.to_dict(),
            "risk": self.risk.to_dict(),
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

    def __init__(self, repo: Path | str = ".", *, clone_depth: int = 200) -> None:
        self.display, self._clone_depth = str(repo), clone_depth
        path, display = resolve_repo(repo, depth=clone_depth)
        self.repo = path
        self.display = display

    def analyze(
        self,
        *,
        max_commits: int = 400,
        since: str | None = None,
        write_report: bool = True,
        use_llm: Union[bool, str] = False,
        scan_debt_files: int = 300,
        include_repo_report: bool = True,
        include_refactor: bool = True,
        include_hardware: bool = True,
    ) -> EvolveReport:
        commits = load_commits(self.repo, max_commits=max_commits, since=since)
        metrics = compute_metrics(commits)
        semantics = analyze_semantics(commits)
        phylogeny = analyze_phylogeny(commits, metrics)
        taxonomy = build_taxonomy(self.repo, commits)
        genetics = analyze_genetics(commits, taxonomy)
        ecology = analyze_ecology(commits, metrics, taxonomy)
        debt = analyze_debt(
            self.repo,
            commits,
            hot_files=metrics.hot_files,
            max_files=scan_debt_files,
        )
        risk = analyze_risk(commits, metrics, taxonomy, genetics, debt)
        timeline = change_rate_timeline(commits)

        ctx = {
            "repo": self.display,
            "metrics": metrics.to_dict(),
            "semantics": semantics.to_dict(),
            "phylogeny": phylogeny.to_dict(),
            "taxonomy": taxonomy.to_dict(),
            "genetics": genetics.to_dict(),
            "ecology": ecology.to_dict(),
            "debt": debt.to_dict(),
            "risk": risk.to_dict(),
        }

        trend = write_trend_report(ctx, use_llm=bool(use_llm) and use_llm is not False) if write_report else None
        # Prefer richer llm flag for repo report
        llm_flag: Union[bool, str] = use_llm
        repo_doc = write_repo_report(ctx, llm=llm_flag) if include_repo_report else None
        refactor = build_refactor_plan(risk, debt) if include_refactor else None

        hw = None
        if include_hardware:
            profile = assess_hardware()
            hw = {"profile": profile.to_dict(), "recommendation": recommend_execution(profile)}

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
