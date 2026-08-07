"""Public CodeEvolve facade."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from codeevolve.debt import DebtReport, analyze_debt
from codeevolve.gitlog import CommitRecord, assert_git_repo, load_commits
from codeevolve.metrics import MetricBundle, change_rate_timeline, compute_metrics
from codeevolve.phylogeny import PhylogenyReport, analyze_phylogeny
from codeevolve.report import TrendReport, write_trend_report
from codeevolve.semantics import SemanticReport, analyze_semantics


@dataclass
class EvolveReport:
    repo: str
    metrics: MetricBundle
    semantics: SemanticReport
    phylogeny: PhylogenyReport
    debt: DebtReport
    change_timeline: list[dict[str, Any]] = field(default_factory=list)
    trend: Optional[TrendReport] = None
    commit_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "commit_count": self.commit_count,
            "metrics": self.metrics.to_dict(),
            "semantics": self.semantics.to_dict(),
            "phylogeny": self.phylogeny.to_dict(),
            "debt": self.debt.to_dict(),
            "change_timeline": list(self.change_timeline),
            "trend": self.trend.to_dict() if self.trend else None,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


class CodeEvolve:
    """Analyze a git repository's evolutionary dynamics."""

    def __init__(self, repo: Path | str = ".") -> None:
        self.repo = assert_git_repo(Path(repo))

    def analyze(
        self,
        *,
        max_commits: int = 400,
        since: str | None = None,
        write_report: bool = True,
        use_llm: bool = False,
        scan_debt_files: int = 300,
    ) -> EvolveReport:
        commits = load_commits(self.repo, max_commits=max_commits, since=since)
        metrics = compute_metrics(commits)
        semantics = analyze_semantics(commits)
        phylogeny = analyze_phylogeny(commits, metrics)
        debt = analyze_debt(
            self.repo,
            commits,
            hot_files=metrics.hot_files,
            max_files=scan_debt_files,
        )
        timeline = change_rate_timeline(commits)
        trend = None
        if write_report:
            ctx = {
                "repo": str(self.repo),
                "metrics": metrics.to_dict(),
                "semantics": semantics.to_dict(),
                "phylogeny": phylogeny.to_dict(),
                "debt": debt.to_dict(),
            }
            trend = write_trend_report(ctx, use_llm=use_llm)
        return EvolveReport(
            repo=str(self.repo),
            metrics=metrics,
            semantics=semantics,
            phylogeny=phylogeny,
            debt=debt,
            change_timeline=timeline,
            trend=trend,
            commit_count=len(commits),
        )

    def commits(self, *, max_commits: int = 100, since: str | None = None) -> list[CommitRecord]:
        return load_commits(self.repo, max_commits=max_commits, since=since)
