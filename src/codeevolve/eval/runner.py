"""Top-level evaluation runner: synthetic + taxonomy gold + public scorecard."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from codeevolve.eval.benchmarks import BenchmarkCase, run_benchmark_suite

Suite = Literal["synthetic", "public", "taxonomy", "all"]


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
    taxonomy_score: float | None = None
    public_skipped: list[dict[str, Any]] = field(default_factory=list)
    suite: str = "synthetic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "overall_score": self.overall_score,
            "synthetic_score": self.synthetic_score,
            "taxonomy_score": self.taxonomy_score,
            "public_score": self.public_score,
            "passed_cases": self.passed_cases,
            "total_cases": self.total_cases,
            "summary": self.summary,
            "public_skipped": list(self.public_skipped),
            "cases": [c.to_dict() for c in self.cases],
            "markdown": self.markdown,
        }


def _md_cases(title: str, blurb: str, cases: list[BenchmarkCase], overall: float) -> str:
    lines = [
        f"# {title}",
        "",
        f"_{blurb}_",
        "",
        f"**Score:** {overall:.1%} · **Clean cases:** {sum(1 for c in cases if c.failed == 0)}/{len(cases)}",
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


def _combine(
    synth: float | None,
    tax: float | None,
    public: float | None,
) -> float:
    """Weight: taxonomy gold > public > synthetic when present."""
    parts: list[tuple[float, float]] = []
    if tax is not None:
        parts.append((0.40, tax))
    if public is not None:
        parts.append((0.35, public))
    if synth is not None:
        parts.append((0.25, synth))
    if not parts:
        return 0.0
    wsum = sum(w for w, _ in parts)
    return sum(w * s for w, s in parts) / wsum


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

    tax_cases: list[BenchmarkCase] = []
    tax_score = None
    if suite in {"taxonomy", "all"}:
        from codeevolve.eval.taxonomy_gold import run_taxonomy_eval

        tax_cases = run_taxonomy_eval(work)
        tax_score = sum(c.score for c in tax_cases) / max(1, len(tax_cases))

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

    if suite == "synthetic":
        cases = synth_cases
        overall = float(synth_score or 0.0)
    elif suite == "taxonomy":
        cases = tax_cases
        overall = float(tax_score or 0.0)
    elif suite == "public":
        cases = public_cases
        overall = float(public_score or 0.0)
    else:
        cases = [*synth_cases, *tax_cases, *public_cases]
        overall = _combine(synth_score, tax_score, public_score)

    passed = sum(1 for c in cases if c.failed == 0)
    parts = [
        "# CodeEvolve Evaluation Report",
        "",
        f"Suite: **{suite}**",
        "",
    ]
    if synth_score is not None:
        parts.append(
            _md_cases(
                "Synthetic fixture evaluation",
                "Planted ground truth. Scores measure detection agreement, not absolute truth.",
                synth_cases,
                synth_score,
            )
        )
        parts.append("")
    if tax_score is not None:
        parts.append(
            _md_cases(
                "Taxonomy gold + RAG pipeline",
                "Type-path gold prefixes + RAG index/typed clades/engine meta. "
                "Set CODEVOLVE_LIVE_SLM=1 to require hf-slm-rag.",
                tax_cases,
                tax_score,
            )
        )
        parts.append("")
    if public_md:
        parts.append(public_md)
        parts.append("")
    parts.extend(
        [
            "## Combined interpretation",
            "",
            f"- Synthetic score: {synth_score if synth_score is not None else 'n/a'}",
            f"- Taxonomy gold/RAG: {tax_score if tax_score is not None else 'n/a'}",
            f"- Public scorecard: {public_score if public_score is not None else 'n/a'} "
            f"({len(public_skipped)} skipped)",
            f"- Combined overall: {overall:.1%}"
            + (
                " (0.40·taxonomy + 0.35·public + 0.25·synthetic when all present)"
                if synth_score is not None and tax_score is not None and public_score is not None
                else ""
            ),
            "",
            "- Synthetic fixtures prove detectors fire on planted patterns.",
            "- Taxonomy gold proves keyword type paths + RAG pipeline attach evidence.",
            "- Public scorecard proves the tool runs on real tags with calibrated deltas.",
            "- Skipped public cases (offline / clone failure) do not count as failures.",
            "",
        ]
    )
    md = "\n".join(parts)
    summary = (
        f"Eval[{suite}] overall {overall:.1%} "
        f"(synthetic={synth_score if synth_score is not None else 'n/a'}, "
        f"taxonomy={tax_score if tax_score is not None else 'n/a'}, "
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
        taxonomy_score=round(tax_score, 4) if tax_score is not None else None,
        public_score=round(public_score, 4) if public_score is not None else None,
        public_skipped=public_skipped,
        suite=suite,
    )
