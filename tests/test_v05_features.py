import json
from pathlib import Path

from codeevolve import CodeEvolve
from codeevolve.ci import evaluate_ci_gate
from codeevolve.dashboard import render_dashboard
from codeevolve.genetics.alleles import analyze_allele_drift
from codeevolve.pr_comment import render_pr_comment
from codeevolve.report.diff import diff_reports
from codeevolve.taxonomy.symbols import SymbolNode, SymbolReport, extract_symbols


def test_alleles_and_diff_ci_dashboard(sample_repo: Path, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    r1 = CodeEvolve(sample_repo).analyze(
        max_commits=50,
        use_llm=False,
        include_hardware=False,
        include_selection=False,
        ensure_slm=False,
    )
    assert r1.drift and "alleles" in r1.drift.to_dict()
    assert r1.sprints is not None
    data1 = r1.to_dict()
    prev_path = tmp_path / "prev.json"
    prev_path.write_text(json.dumps(data1), encoding="utf-8")

    r2 = CodeEvolve(sample_repo).analyze(
        max_commits=50,
        use_llm=False,
        include_hardware=False,
        include_selection=False,
        ensure_slm=False,
        previous_report=prev_path,
    )
    assert r2.diff is not None

    gate = evaluate_ci_gate(r2.to_dict(), previous=data1, min_stability=0.1)
    assert gate.ok or gate.failures  # structured result

    md = render_pr_comment(r2.to_dict(), diff=r2.diff.to_dict())
    assert "CodeEvolve" in md and "Stability" in md

    html = render_dashboard(r2.to_dict())
    assert "clade" in html.lower() and "canvas" in html.lower()


def test_allele_detection_unit() -> None:
    syms = SymbolReport(
        symbols=[
            SymbolNode("a.py::parse_config", "function", "a.py", 1),
            SymbolNode("b.py::parse_config", "function", "b.py", 1),
            SymbolNode("c.py::parse_cfg", "function", "c.py", 1),
        ]
    )
    rep = analyze_allele_drift(syms)
    assert rep.pairs


def test_cli_ci_comment_dashboard(sample_repo: Path, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    from codeevolve.cli import main

    report = tmp_path / "r.json"
    assert (
        main(
            [
                "--repo",
                str(sample_repo),
                "analyze",
                "--no-ensure-slm",
                "--out",
                str(report),
                "--dashboard-out",
                str(tmp_path / "d.html"),
            ]
        )
        == 0
    )
    assert main(["ci", "--report", str(report), "--min-stability", "0.05"]) == 0
    assert main(["comment", "--report", str(report), "--out", str(tmp_path / "c.md")]) == 0
    assert (tmp_path / "c.md").read_text(encoding="utf-8")
    assert main(["dashboard", "--report", str(report), "--out", str(tmp_path / "x.html")]) == 0


def test_symbols_still_work(sample_repo: Path) -> None:
    s = extract_symbols(sample_repo)
    assert s.symbol_count >= 1
