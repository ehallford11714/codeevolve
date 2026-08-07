"""Analyze a repository (local path or GitHub URL)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codeevolve import CodeEvolve


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else str(Path.cwd())
    report = CodeEvolve(repo).analyze(max_commits=300, use_llm=False)
    if report.repo_report:
        print(report.repo_report.markdown)
    if report.refactor_plan:
        print("\n---\n")
        print(report.refactor_plan.markdown)
    print(
        {
            "stability": report.metrics.code_stability,
            "revert_rate": report.metrics.revert_rate,
            "stage": report.ecology.global_stage,
            "debt": report.debt.score,
            "failures": len(report.risk.failure_points),
            "refactor_steps": len(report.refactor_plan.steps) if report.refactor_plan else 0,
            "clades": len(report.taxonomy.clades),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
