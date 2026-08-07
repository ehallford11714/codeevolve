"""Top-level evaluation runner: synthetic fixtures + public-repo scorecard."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from codeevolve.eval.benchmarks import BenchmarkCase, run_benchmark_suite

Suite = Literal["synthetic", "public", "all"]


@dataclass
class EvaluationReport:
    cases: list[BenchmarkCase] = field(default_factory=list)
    overall_score: float = 0.0
    passed_cases: int = 0
    total_cases: int = 0
    markdown: str = ""
    summary: str = ""
    synthetic_score: float | None = None
    public_score: float | None = None
    public_skipped: list[dict[str, Any]] = field(default_factory=list)
    suite: str = "synthetic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "overall_score": self.overall_score,
            "synthetic_score": self.synthetic_score,
            "public_score": self.public_score,
            "passed_cases": self.passed_cases,
            "total_cases": self.total_cases,
            "summary": self.summary,
            "public_skipped": list(self.public_skipped),
            "cases": [c.to_dict() for c in self.cases],
            "markdown": self.markdown,
        }


def _md_synthetic(cases: list[BenchmarkCase], overall: float, passed: int) -> str:
    lines = [
        "# Synthetic fixture evaluation",
        "",
        "_Planted ground truth. Scores measure detection agreement, not absolute truth._",
        "",
        f"**Synthetic score:** {overall:.1%} · **Clean cases:** {passed}/{len(cases)}",
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
    return "\n".join(lines)


def run_evaluation(
    work_dir: Path | str | None = None,
    *,
    suite: Suite = "all",
    offline: bool = False,
    public_case_ids: list[str] | None = None,
) -> EvaluationReport:
    work = Path(work_dir) if work_dir else Path.cwd() / ".codeevolve_eval"
    work.mkdir(parents=True, exist_ok=True)

    synth_cases: list[BenchmarkCase] = []
    synth_score = None
    if suite in {"synthetic", "all"}:
        synth_cases = run_benchmark_suite(work)
        synth_score = sum(c.score for c in synth_cases) / max(1, len(synth_cases))

    public_cases: list[BenchmarkCase] = []
    public_score = None
    public_skipped: list[dict[str, Any]] = []
    public_md = ""
    if suite in {"public", "all"}:
        from codeevolve.eval.scorecard import run_public_scorecard

        sc = run_public_scorecard(offline=offline, case_ids=public_case_ids)
        public_cases = sc.cases
        public_skipped = sc.skipped
        public_score = sc.overall_score if sc.cases else None
        public_md = sc.markdown

    # Combine
    if suite == "synthetic":
        cases = synth_cases
        overall = float(synth_score or 0.0)
    elif suite == "public":
        cases = public_cases
        overall = float(public_score or 0.0)
    else:
        cases = [*synth_cases, *public_cases]
        if synth_score is not None and public_score is not None:
            overall = 0.45 * synth_score + 0.55 * public_score
        elif synth_score is not None:
            overall = synth_score
        else:
            overall = float(public_score or 0.0)

    passed = sum(1 for c in cases if c.failed == 0)
    parts = [
        "# CodeEvolve Evaluation Report",
        "",
        f"Suite: **{suite}**",
        "",
    ]
    if synth_score is not None:
        parts.append(_md_synthetic(synth_cases, synth_score, sum(1 for c in synth_cases if c.failed == 0)))
        parts.append("")
    if public_md:
        parts.append(public_md)
        parts.append("")
    parts.extend(
        [
            "## Combined interpretation",
            "",
            f"- Synthetic score: {synth_score if synth_score is not None else 'n/a'}",
            f"- Public scorecard: {public_score if public_score is not None else 'n/a'} "
            f"({len(public_skipped)} skipped)",
            f"- Combined overall: {overall:.1%}"
            + (" (0.45·synthetic + 0.55·public)" if synth_score is not None and public_score is not None else ""),
            "",
            "- Synthetic fixtures prove detectors fire on planted patterns.",
            "- Public scorecard proves the tool runs on real tags and before/after "
            "moves stay within calibrated tolerances.",
            "- Skipped public cases (offline / clone failure) do not count as failures.",
            "",
        ]
    )
    md = "\n".join(parts)
    summary = (
        f"Eval[{suite}] overall {overall:.1%} "
        f"(synthetic={synth_score if synth_score is not None else 'n/a'}, "
        f"public={public_score if public_score is not None else 'n/a'}, "
        f"skipped_public={len(public_skipped)})"
    )
    return EvaluationReport(
        cases=cases,
        overall_score=round(overall, 4),
        passed_cases=passed,
        total_cases=len(cases),
        markdown=md,
        summary=summary,
        synthetic_score=round(synth_score, 4) if synth_score is not None else None,
        public_score=round(public_score, 4) if public_score is not None else None,
        public_skipped=public_skipped,
        suite=suite,
    )
