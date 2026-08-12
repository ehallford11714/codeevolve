"""Public scorecard scoring (offline unit tests; network optional)."""

from __future__ import annotations

import pytest

from codeevolve.eval.public_cases import MetricExpect, public_catalog
from codeevolve.eval.runner import run_evaluation
from codeevolve.eval.scorecard import (
    check_direction,
    digest_report,
    score_delta_expectations,
    score_field_presence,
)


def test_public_catalog_has_smoke_and_before_after():
    cat = public_catalog()
    kinds = {c.kind for c in cat}
    assert "smoke" in kinds and "before_after" in kinds
    assert any(c.repo == "pallets/click" for c in cat)


def test_digest_and_field_presence():
    report = {
        "metrics": {"code_stability": 0.7, "revert_rate": 0.1, "commit_count": 40},
        "coupling": {"edges": [{"a": "x", "b": "y"}], "edge_count": 1},
        "risk": {"count": 3, "failure_points": [{}, {}, {}]},
        "hypothesis_panel": {"claims": [{"id": "H1"}], "counts": {"weak": 1}},
        "signal_confidence": {"hero_ranking": ["change_coupling", "offboarding_risk"]},
    }
    dig = digest_report(report)
    assert dig["coupling"]["edge_count"] == 1
    assert dig["signal_confidence"]["hero_count"] == 2
    checks = score_field_presence(
        dig,
        ["metrics.code_stability", "coupling.edge_count", "signal_confidence.hero_ranking"],
    )
    assert all(c.ok for c in checks)


def test_direction_checks():
    assert check_direction(10, 8, MetricExpect("x", "down")).ok
    assert check_direction(10, 10, MetricExpect("x", "down_or_flat", tol=0)).ok
    assert check_direction(0.5, 0.55, MetricExpect("x", "up_or_flat", tol=0.1)).ok
    assert not check_direction(0.5, 0.3, MetricExpect("x", "up_or_flat", tol=0.05)).ok
    assert check_direction(0, 2, MetricExpect("x", "nonzero")).ok

    before = {"metrics": {"code_stability": 0.5}, "coupling": {"edge_count": 12}}
    after = {"metrics": {"code_stability": 0.55}, "coupling": {"edge_count": 9}}
    checks = score_delta_expectations(
        before,
        after,
        [
            MetricExpect("metrics.code_stability", "up_or_flat", tol=0.02),
            MetricExpect("coupling.edge_count", "down_or_flat", tol=1),
        ],
    )
    assert all(c.ok for c in checks)


def test_evaluate_all_offline_skips_public(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")

    def _stub_agent_eval(*_a, **_k):
        return {
            "suite": "agent",
            "overall_score": 0.8,
            "passed_cases": 1,
            "total_cases": 1,
            "outcome_counts": {"improved": 1},
            "cases": [
                {
                    "name": "stub_improved",
                    "score": 0.8,
                    "passed": True,
                    "details": {"outcome": "improved", "delta": -0.1, "checks": ["objective_improved"]},
                }
            ],
        }

    monkeypatch.setattr("codeevolve.eval.agent_eval.run_agent_eval", _stub_agent_eval)
    ev = run_evaluation(tmp_path / "eval_work", suite="all", offline=True)
    assert ev.synthetic_score is not None and ev.synthetic_score >= 0.7
    # public should skip without cache
    assert ev.public_score is None or ev.public_skipped
    assert "Public" in ev.markdown or "public" in ev.summary.lower()
    assert ev.agent_score == 0.8
    assert "agent=0.8" in ev.summary
    assert any(c.name == "stub_improved" for c in ev.cases)


@pytest.mark.integration
def test_public_click_smoke_live():
    """Optional live smoke — skipped unless CODEVOLVE_LIVE_EVAL=1."""
    import os

    if os.environ.get("CODEEVOLVE_LIVE_EVAL", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("set CODEVOLVE_LIVE_EVAL=1 to run live public scorecard")
    from codeevolve.eval.scorecard import run_public_scorecard

    sc = run_public_scorecard(offline=False, case_ids=["click_smoke_8.4.0"])
    if sc.skipped and not sc.cases:
        pytest.skip(f"clone unavailable: {sc.skipped}")
    assert sc.cases
    assert sc.cases[0].score >= 0.6
