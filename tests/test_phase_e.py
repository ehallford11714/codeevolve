from pathlib import Path
from unittest.mock import patch

from codeevolve import CodeEvolve
from codeevolve.ingest.github_api import SelectionPressure, fetch_selection_pressure
from codeevolve.taxonomy.symbols import extract_symbols


def test_symbols_extracted(sample_repo: Path) -> None:
    report = extract_symbols(sample_repo)
    assert report.symbol_count >= 2
    names = {s.qualname for s in report.symbols}
    assert any("main" in n for n in names)


def test_analyze_includes_symbols_and_niches(sample_repo: Path) -> None:
    r = CodeEvolve(sample_repo).analyze(
        max_commits=50,
        include_selection=False,
        include_hardware=False,
        use_llm=False,
    )
    assert r.symbols and r.symbols.symbol_count >= 1
    assert "niches" in r.ecology.to_dict()
    assert r.blast_radius is not None
    assert r.genetics.rename_events >= 0


def test_selection_pressure_mocked() -> None:
    fake_issues = [
        {"title": "bug crash", "state": "open", "body": "", "labels": [{"name": "bug"}]},
        {"title": "feat", "state": "closed", "body": "reopen later", "labels": []},
        {"title": "pr-like", "state": "open", "pull_request": {}, "labels": []},
    ]
    fake_prs = [
        {"merged_at": "2024-01-01T00:00:00Z"},
        {"merged_at": None},
    ]
    with patch("codeevolve.ingest.github_api._gh_get", side_effect=[fake_issues, fake_prs]):
        sp = fetch_selection_pressure("acme", "demo", token="x")
    assert sp.issues_sampled == 2
    assert sp.bug_label_rate > 0
    assert sp.prs_sampled == 2
    assert 0 <= sp.pressure_score <= 1


def test_risk_uses_selection(sample_repo: Path) -> None:
    from codeevolve.debt import analyze_debt
    from codeevolve.genetics import analyze_genetics
    from codeevolve.gitlog import load_commits
    from codeevolve.metrics import compute_metrics
    from codeevolve.risk import analyze_risk
    from codeevolve.taxonomy import build_taxonomy

    commits = load_commits(sample_repo, max_commits=50)
    metrics = compute_metrics(commits)
    tax = build_taxonomy(sample_repo, commits)
    gen = analyze_genetics(commits, tax)
    debt = analyze_debt(sample_repo, commits, hot_files=metrics.hot_files)
    sel = SelectionPressure(
        owner="a",
        repo="b",
        issues_sampled=10,
        open_issues=6,
        bug_label_rate=0.5,
        reopened_like=2,
        pressure_score=0.6,
    )
    risk = analyze_risk(commits, metrics, tax, gen, debt, selection=sel)
    assert any(p.kind == "selection_pressure" for p in risk.failure_points)


def test_cli_symbols(sample_repo: Path) -> None:
    from codeevolve.cli import main

    assert main(["--repo", str(sample_repo), "symbols"]) == 0
