"""Top-level evaluation runner + markdown report."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.eval.benchmarks import BenchmarkCase, run_benchmark_suite


@dataclass
class EvaluationReport:
    cases: list[BenchmarkCase] = field(default_factory=list)
    overall_score: float = 0.0
    passed_cases: int = 0
    total_cases: int = 0
    markdown: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "passed_cases": self.passed_cases,
            "total_cases": self.total_cases,
            "summary": self.summary,
            "cases": [c.to_dict() for c in self.cases],
            "markdown": self.markdown,
        }


def _md(cases: list[BenchmarkCase], overall: float, passed: int) -> str:
    lines = [
        "# CodeEvolve Evaluation Report",
        "",
        "_Synthetic fixtures with planted ground truth. Scores measure detection "
        "agreement, not absolute truth about real repositories._",
        "",
        f"**Overall score:** {overall:.1%} · **Cases fully clean:** {passed}/{len(cases)}",
        "",
        "| Case | Score | Passed | Failed |",
        "|------|------:|-------:|-------:|",
    ]
    for c in cases:
        lines.append(f"| `{c.name}` | {c.score:.0%} | {c.passed} | {c.failed} |")
    lines.append("")
    for c in cases:
        lines.append(f"## {c.name}")
        lines.append("")
        for ch in c.checks:
            mark = "PASS" if ch.ok else "FAIL"
            lines.append(f"- [{mark}] `{ch.name}` — {ch.detail}")
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "- Hero signals under test: change coupling, churn×complexity hotspots, offboarding.",
            "- Lehman/ecology appear as hypothesis panels with confidence — not grades.",
            "- Before/after decouple case checks that coupling moves in the expected direction.",
            "",
        ]
    )
    return "\n".join(lines)


def run_evaluation(work_dir: Path | str | None = None) -> EvaluationReport:
    work = Path(work_dir) if work_dir else Path.cwd() / ".codeevolve_eval"
    work.mkdir(parents=True, exist_ok=True)
    cases = run_benchmark_suite(work)
    if not cases:
        return EvaluationReport(summary="No cases")
    overall = sum(c.score for c in cases) / len(cases)
    passed = sum(1 for c in cases if c.failed == 0)
    md = _md(cases, overall, passed)
    return EvaluationReport(
        cases=cases,
        overall_score=round(overall, 4),
        passed_cases=passed,
        total_cases=len(cases),
        markdown=md,
        summary=f"Eval overall {overall:.1%} across {len(cases)} cases ({passed} clean)",
    )
