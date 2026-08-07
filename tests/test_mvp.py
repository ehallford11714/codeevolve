from pathlib import Path

from codeevolve import CodeEvolve
from codeevolve.embeddings import cosine, embed_text
from codeevolve.metrics import compute_metrics
from codeevolve.report import top_down_plan, write_trend_report


def test_embeddings_cosine() -> None:
    a = embed_text("fix bug crash error")
    b = embed_text("fix bug patch resolve")
    c = embed_text("completely unrelated documentation only")
    assert cosine(a, b) > cosine(a, c)


def test_analyze_sample_repo(sample_repo: Path) -> None:
    ce = CodeEvolve(sample_repo)
    report = ce.analyze(max_commits=50, write_report=True, use_llm=False)
    assert report.commit_count >= 5
    assert 0.0 <= report.metrics.revert_rate <= 1.0
    assert report.metrics.revert_count >= 1
    assert 0.0 <= report.metrics.code_stability <= 1.0
    assert report.metrics.dependency_change_commits >= 1
    assert report.semantics.theme_distribution
    assert report.phylogeny.current_stage
    assert report.phylogeny.stages
    assert report.debt.summary
    assert report.trend and "CodeEvolve Trend Report" in report.trend.markdown
    assert report.change_timeline


def test_cli_analyze(sample_repo: Path, tmp_path: Path) -> None:
    from codeevolve.cli import main

    out = tmp_path / "report.json"
    md = tmp_path / "trend.md"
    code = main(
        [
            "--repo",
            str(sample_repo),
            "analyze",
            "--out",
            str(out),
            "--md-out",
            str(md),
        ]
    )
    assert code == 0
    assert out.exists() and md.exists()
    assert "Ecological" in md.read_text(encoding="utf-8") or "ecological" in md.read_text(encoding="utf-8").lower() or "stage" in md.read_text(encoding="utf-8").lower()


def test_planner_priorities() -> None:
    outline = top_down_plan(
        {
            "metrics": {"revert_rate": 0.2, "dependency_rate": 0.2, "momentum": 1.0},
            "debt": {"score": 0.5},
            "phylogeny": {"current_stage": "disturbance"},
            "semantics": {"semantic_drift": 0.5},
        }
    )
    assert outline.priorities
    assert any("revert" in p.lower() or "Stabilize" in p for p in outline.priorities)


def test_metrics_empty() -> None:
    m = compute_metrics([])
    assert m.commit_count == 0
