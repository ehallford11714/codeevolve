"""Analyze a repository (defaults to this repo's parent git root or CWD)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codeevolve import CodeEvolve


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else str(Path.cwd())
    report = CodeEvolve(repo).analyze(max_commits=300, use_llm=False)
    print(report.trend.markdown if report.trend else report.to_json())
    print("\n# JSON summary")
    print(
        {
            "stability": report.metrics.code_stability,
            "revert_rate": report.metrics.revert_rate,
            "dependency_rate": report.metrics.dependency_rate,
            "momentum": report.metrics.momentum,
            "stage": report.phylogeny.current_stage,
            "debt": report.debt.score,
            "themes": report.semantics.theme_distribution,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
