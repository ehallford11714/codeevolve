"""Event + changepoint ecology calibration."""

from __future__ import annotations

from datetime import datetime, timezone

from codeevolve.api import CodeEvolve
from codeevolve.ecology.changepoints import detect_changepoints, pelt_lite
from codeevolve.ecology.events import pioneer_event, revert_storm_events
from codeevolve.eval.ecology_gold import run_ecology_eval, _synthetic_commits


def test_pelt_lite_step():
    series = [1.0] * 10 + [25.0] * 10
    cps = pelt_lite(series, min_seg=3, penalty=3.0)
    assert any(6 <= c <= 14 for c in cps), cps


def test_synthetic_changepoints():
    commits = _synthetic_commits()
    report = detect_changepoints(commits, min_seg=2)
    assert len(report.months) >= 12
    assert report.points


def test_revert_storm_and_pioneer():
    commits = _synthetic_commits()
    assert pioneer_event(commits) is not None
    storms = revert_storm_events(commits, min_reverts=3)
    assert storms


def test_ecology_eval_suite(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    cases = run_ecology_eval(tmp_path)
    assert len(cases) >= 3
    by = {c.name: c for c in cases}
    assert by["ecology_changepoints_synthetic"].score >= 0.5
    assert by["ecology_event_hints"].score >= 0.8
    assert by["ecology_calibration_repo"].score >= 0.5


def test_analyze_includes_calibration(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GENSIM", "1")
    monkeypatch.setenv("CODEEVOLVE_VECTOR_BACKEND", "memory")
    report = CodeEvolve(sample_repo).analyze(
        use_llm=False,
        ensure_slm=False,
        include_selection=False,
        write_report=False,
        include_repo_report=False,
        include_hardware=False,
        include_cst=False,
        include_clones=False,
        include_reticulation=False,
        include_fork_lineage=False,
        include_semantic=False,
        include_rag=False,
        max_commits=80,
    )
    assert report.ecology.calibration is not None
    assert report.ecology.calibration.method in {
        "event_changepoint",
        "event_anchor",
        "heuristic_fallback",
    }
    assert report.ecology.global_stage == report.ecology.calibration.global_stage
    d = report.ecology.to_dict()
    assert d.get("calibration")
