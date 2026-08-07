"""Rigor & evaluation suite tests."""

from __future__ import annotations

from datetime import datetime, timezone

from codeevolve.api import CodeEvolve
from codeevolve.ecology.lehman import compute_lehman
from codeevolve.ecology.trends import analyze_lehman_trends
from codeevolve.eval.confidence import score_signal_confidence
from codeevolve.eval.fixtures import materialize_suite
from codeevolve.eval.hypothesis import build_hypothesis_panel
from codeevolve.eval.runner import run_evaluation
from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import compute_metrics
from codeevolve.psychology.offboarding import simulate_offboarding
from codeevolve.risk.coupling import analyze_coupling


def _c(sha: str, files: list[str], *, day: int = 1, author: str = "Dev") -> CommitRecord:
    return CommitRecord(
        sha=sha,
        parents=[],
        author=author,
        email="d@e.com",
        timestamp=datetime(2024, 1, day, tzinfo=timezone.utc),
        subject="feat",
        files=files,
        insertions=5,
        deletions=1,
    )


def test_hypothesis_panel_insufficient_on_tiny_sample():
    commits = [_c(f"s{i}", ["a.py"], day=i + 1) for i in range(6)]
    metrics = compute_metrics(commits)
    lehman = compute_lehman(commits, metrics)
    trends = analyze_lehman_trends(commits, metrics)
    panel = build_hypothesis_panel(commits, metrics, lehman, trends, stage="growth", stage_rationale="test")
    assert panel.claims
    assert "not laws" in panel.disclaimer.lower() or "hypothes" in panel.disclaimer.lower()
    assert any(c.verdict == "insufficient" for c in panel.claims)
    assert panel.stage_hypothesis is not None
    assert panel.stage_hypothesis.verdict in {"weak", "insufficient"}


def test_signal_confidence_hero_ranking():
    commits = [
        _c("a", ["src/a.py", "src/b.py"], day=1),
        _c("b", ["src/a.py", "src/b.py"], day=2),
        _c("c", ["src/a.py", "src/b.py"], day=3),
        _c("d", ["src/a.py"], day=4, author="Solo"),
        _c("e", ["src/a.py"], day=5, author="Solo"),
    ]
    for i in range(10):
        commits.append(_c(f"x{i}", ["src/a.py", "src/b.py"], day=6 + i, author="Solo"))
    metrics = compute_metrics(commits)
    metrics.hot_files = [
        {"path": "src/a.py", "touches": 12, "complexity": 20, "hotspot_score": 0.7},
        {"path": "src/b.py", "touches": 10, "complexity": 5, "hotspot_score": 0.4},
    ]
    coupling = analyze_coupling(commits, min_weight=2)
    off = simulate_offboarding(commits, metrics)
    conf = score_signal_confidence(commits, metrics, coupling, off)
    assert "change_coupling" in conf.hero_ranking or "hotspot_churn_complexity" in conf.hero_ranking
    assert conf.signals


def test_analyze_emits_rigor_fields(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    report = CodeEvolve(sample_repo).analyze(
        use_llm=False,
        ensure_slm=False,
        include_selection=False,
        write_report=False,
        include_repo_report=False,
        include_hardware=False,
    )
    d = report.to_dict()
    assert d["hypothesis_panel"]["claims"]
    assert d["signal_confidence"]["hero_ranking"] is not None
    assert report.hypothesis_panel.disclaimer


def test_benchmark_suite_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    suite = materialize_suite(tmp_path / "fx")
    assert len(suite) == 4
    ev = run_evaluation(tmp_path / "eval_work")
    assert ev.total_cases >= 5
    assert ev.overall_score > 0.0
    assert "CodeEvolve Evaluation Report" in ev.markdown
    # coupled hotspot should largely pass
    by = {c.name: c for c in ev.cases}
    assert by["coupled_hotspot"].score >= 0.5
