from pathlib import Path

from codeevolve import CodeEvolve
from codeevolve.models.hardware import assess_hardware, recommend_execution
from codeevolve.models.router import resolve_backend_name
from codeevolve.refactor import build_refactor_plan


def test_full_analyze_deep(sample_repo: Path) -> None:
    report = CodeEvolve(sample_repo).analyze(
        max_commits=50,
        write_report=True,
        use_llm=False,
        include_repo_report=True,
        include_refactor=True,
        include_hardware=True,
    )
    assert report.taxonomy.clades
    assert report.taxonomy.allocations
    assert report.genetics.lineages
    assert report.ecology.lehman.continuing_change >= 0
    assert report.ecology.clade_stages
    assert report.risk.failure_points
    assert report.repo_report and "Repository Report" in report.repo_report.markdown
    assert report.refactor_plan and report.refactor_plan.steps
    for step in report.refactor_plan.steps:
        assert step.evidence_refs, "every refactor step needs evidence"
    assert report.hardware and "recommendation" in report.hardware


def test_refactor_evidence_links(sample_repo: Path) -> None:
    report = CodeEvolve(sample_repo).analyze(
        max_commits=50,
        write_report=False,
        include_repo_report=False,
        include_refactor=True,
        include_hardware=False,
    )
    plan = report.refactor_plan or build_refactor_plan(report.risk, report.debt)
    weak_ids = {w.id for w in report.risk.failure_points}
    assert any(any(e in weak_ids or e.startswith("DEB-") for e in s.evidence_refs) for s in plan.steps)


def test_hardware_and_router() -> None:
    hw = assess_hardware(prefer_small=True)
    assert "Qwen" in hw.recommended_model
    rec = recommend_execution(hw)
    assert rec["backend"] in {"hf-qwen", "openai", "anthropic", "heuristic"}
    assert resolve_backend_name(False) == "heuristic"
    assert resolve_backend_name("openai") == "openai_compatible"


def test_cli_report_refactor(sample_repo: Path, tmp_path: Path) -> None:
    from codeevolve.cli import main

    rr = tmp_path / "repo_report.md"
    rp = tmp_path / "refactor_plan.md"
    code = main(
        [
            "--repo",
            str(sample_repo),
            "analyze",
            "--report-out",
            str(rr),
            "--refactor-out",
            str(rp),
            "--out",
            str(tmp_path / "full.json"),
        ]
    )
    assert code == 0
    assert rr.exists() and "Executive summary" in rr.read_text(encoding="utf-8")
    assert rp.exists() and "Refactor Plan" in rp.read_text(encoding="utf-8")
