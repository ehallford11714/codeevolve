"""Tests for 0.6 literature takeaways G1–G10."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from codeevolve.api import CodeEvolve
from codeevolve.complexity import enrich_hotspots, heuristic_complexity
from codeevolve.ecology.trends import analyze_lehman_trends, mann_kendall
from codeevolve.genetics.clones import analyze_clone_genealogy
from codeevolve.gitlog import CommitRecord
from codeevolve.ingest.fork_lineage import analyze_fork_lineage
from codeevolve.metrics import compute_metrics
from codeevolve.psychology.offboarding import simulate_offboarding
from codeevolve.refactor.effort import estimate_effort, estimate_person_days
from codeevolve.risk.coupling import analyze_coupling
from codeevolve.risk.dependencies import analyze_dependency_fragility
from codeevolve.taxonomy.cst import analyze_cst_evolution


def _c(
    sha: str,
    files: list[str],
    *,
    author: str = "Dev",
    subject: str = "feat",
    ins: int = 10,
    dels: int = 2,
    day: int = 1,
) -> CommitRecord:
    return CommitRecord(
        sha=sha,
        parents=[],
        author=author,
        email=f"{author}@ex.com",
        timestamp=datetime(2024, 1, day, tzinfo=timezone.utc),
        subject=subject,
        files=files,
        insertions=ins,
        deletions=dels,
    )


def test_mann_kendall_increasing():
    t = mann_kendall([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    assert t.trend == "increasing"
    assert t.tau > 0


def test_coupling_filters_large_and_tickets():
    commits = [
        _c("a1", ["src/a.py", "src/b.py"], subject="fix #42", day=1),
        _c("a2", ["src/a.py", "src/b.py"], subject="fix #42 again", day=2),
        _c("a3", ["src/a.py", "src/b.py", "src/c.py"], subject="JIRA-7 polish", day=3),
        _c("big", [f"f{i}.py" for i in range(40)], subject="chore: reformat", ins=5000, day=4),
    ]
    r = analyze_coupling(commits, max_files_per_commit=12, min_weight=2)
    assert r.filtered_large_commits >= 1
    assert any(e.a.endswith("a.py") and e.b.endswith("b.py") for e in r.edges)
    assert r.ticket_groups


def test_hotspot_complexity_enrichment(sample_repo):
    assert heuristic_complexity("def f():\n    if x:\n        for y in z:\n            pass\n") >= 3
    metrics = compute_metrics(CodeEvolve(sample_repo).commits())
    hot = enrich_hotspots(sample_repo, metrics.hot_files)
    assert hot
    assert "hotspot_score" in hot[0]
    assert "complexity" in hot[0]


def test_clone_genealogy_and_cst(sample_repo):
    ce = CodeEvolve(sample_repo)
    commits = ce.commits()
    # seed a clone pair
    (sample_repo / "src" / "dup.py").write_text(
        "def helper():\n    pass\n", encoding="utf-8"
    )
    clones = analyze_clone_genealogy(sample_repo, commits, windows=2, max_paths=20)
    assert "summary" in clones.to_dict()
    cst = analyze_cst_evolution(sample_repo, commits, windows=2, max_paths=20)
    assert cst.windows
    assert cst.engine in {"regex", "tree_sitter+regex"}


def test_dependencies_and_offboarding(sample_repo):
    commits = CodeEvolve(sample_repo).commits()
    deps = analyze_dependency_fragility(sample_repo, commits)
    assert "requirements.txt" in deps.manifests or deps.package_count >= 0
    metrics = compute_metrics(commits)
    # multi-author synthetic overlay
    more = commits + [
        _c("x1", ["src/app.py"], author="Alice", day=10),
        _c("x2", ["src/app.py"], author="Alice", day=11),
        _c("x3", ["src/utils.py"], author="Bob", day=12),
    ]
    off = simulate_offboarding(more, metrics)
    assert off.scenarios
    assert 0.0 <= off.mastery_drop_top1 <= 1.0


def test_lehman_trends_and_effort():
    commits = [_c(f"s{i}", ["a.py"], day=i + 1, ins=5 + i * 3) for i in range(12)]
    metrics = compute_metrics(commits)
    trends = analyze_lehman_trends(commits, metrics)
    assert trends.tests
    assert "self_regulation" in trends.law_support or "continuing_change" in trends.law_support
    assert estimate_person_days(0.8, 0.5) >= estimate_person_days(0.2, 0.0)
    assert estimate_effort(0.95, 0.9, 40) == "L"
    assert estimate_effort(0.3, 0.0) == "S"


def test_fork_lineage_intra(sample_repo):
    # duplicate content paths
    text = "shared blob\n"
    (sample_repo / "src" / "copy_a.py").write_text(text, encoding="utf-8")
    (sample_repo / "src" / "copy_b.py").write_text(text, encoding="utf-8")
    import subprocess

    subprocess.run(["git", "-C", str(sample_repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(sample_repo), "commit", "-m", "dup blobs"],
        check=True,
        capture_output=True,
    )
    fl = analyze_fork_lineage(sample_repo)
    assert fl.duplicate_ratio >= 0.0
    assert any("copy_" in p for d in fl.duplicate_blobs for p in d["paths"]) or fl.summary


def test_full_analyze_includes_g_fields(sample_repo, monkeypatch):
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
    assert d["coupling"] is not None
    assert d["dependencies"] is not None
    assert d["offboarding"] is not None
    assert d["clones"] is not None
    assert d["reticulation"] is not None
    assert d["cst_evolution"] is not None
    assert d["fork_lineage"] is not None
    assert d["ecology"]["lehman"].get("self_regulation") is not None
    assert d["ecology"]["lehman_trends"] is not None
    assert report.metrics.hot_files and "hotspot_score" in report.metrics.hot_files[0]
    assert report.refactor_plan
    assert any(s.estimated_person_days > 0 for s in report.refactor_plan.steps) or report.refactor_plan.steps == []
