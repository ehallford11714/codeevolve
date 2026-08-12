"""Agent eval scores objective delta / clean rollback, not artifact presence."""

from __future__ import annotations

from pathlib import Path

from codeevolve.eval.agent_eval import (
    AgentEvalCase,
    _score_run,
    benchmark_cases_from_agent_report,
    classify_run_outcome,
)
from codeevolve.eval.runner import _combine


def _apply_run(*, improved: bool, accepted: bool, notes: list[str], applied: bool = True) -> dict:
    return {
        "status": "ok",
        "session": {"last_report_path": "x"},
        "rounds": [
            {
                "accepted": accepted,
                "applied": applied,
                "notes": notes,
                "proposal": {
                    "falsifier": "debt rises",
                    "measure": "re-analyze",
                    "frame_ids": ["frame:basin"],
                },
                "score_before": {"value": 0.5, "improved": False},
                "score_after": {
                    "value": 0.2 if improved else 0.5,
                    "previous": 0.5,
                    "delta": -0.3 if improved else 0.0,
                    "improved": improved,
                },
            }
        ],
        "final_score": {"value": 0.2 if improved else 0.5, "improved": improved, "delta": -0.3 if improved else 0.0},
    }


def test_apply_improved_passes(tmp_path: Path) -> None:
    case = AgentEvalCase("apply_debt", "reduce_debt", apply=True)
    result = _score_run(case, _apply_run(improved=True, accepted=True, notes=["accepted — objective progress kept"]), tmp_path)
    assert result.details["outcome"] == "improved"
    assert result.passed
    assert result.score >= 0.7
    assert "objective_improved" in result.details["checks"]


def test_apply_rollback_passes(tmp_path: Path) -> None:
    case = AgentEvalCase("apply_debt", "reduce_debt", apply=True)
    run = _apply_run(improved=False, accepted=False, notes=["rejected — rolled back (objective/constraints/ci)"], applied=False)
    result = _score_run(case, run, tmp_path)
    assert result.details["outcome"] == "rolled_back"
    assert result.passed
    assert "rolled_back_cleanly" in result.details["checks"]


def test_apply_accepted_no_delta_fails(tmp_path: Path) -> None:
    case = AgentEvalCase("apply_debt", "reduce_debt", apply=True)
    run = _apply_run(
        improved=False,
        accepted=True,
        notes=["accepted heuristic artifact with no worsened signals"],
    )
    result = _score_run(case, run, tmp_path)
    assert result.details["outcome"] == "accepted_no_delta"
    assert not result.passed
    assert result.score < 0.55


def test_dry_run_delta_ready(tmp_path: Path) -> None:
    case = AgentEvalCase("dry_run_debt", "reduce_debt", apply=False)
    run = {
        "status": "ok",
        "session": {},
        "rounds": [
            {
                "accepted": False,
                "applied": False,
                "notes": [],
                "proposal": {
                    "falsifier": "If next run does not improve debt.score, reject.",
                    "measure": "Re-analyze with --previous",
                    "frame_ids": ["frame:basin"],
                },
                "score_before": {"value": 0.4, "improved": False},
                "score_after": None,
            }
        ],
    }
    result = _score_run(case, run, tmp_path)
    assert classify_run_outcome(run, apply=False) == "delta_ready"
    assert result.passed
    assert "baseline_score" in result.details["checks"]
    assert "measurable_proposal" in result.details["checks"]


def test_empty_run_fails(tmp_path: Path) -> None:
    case = AgentEvalCase("empty", "follow_refactor", apply=True)
    result = _score_run(case, {"status": "error", "rounds": []}, tmp_path)
    assert not result.passed
    assert result.details["outcome"] == "none"


def test_combine_includes_agent() -> None:
    without = _combine(0.8, 0.8, 0.8, 0.8, 0.8, None)
    with_agent = _combine(0.8, 0.8, 0.8, 0.8, 0.8, 0.2)
    assert with_agent < without
    only_agent = _combine(None, None, None, None, None, 0.6)
    assert abs(only_agent - 0.6) < 1e-9


def test_runner_suite_agent_uses_outcome_score(tmp_path: Path, monkeypatch) -> None:
    from codeevolve.eval.runner import run_evaluation

    def _stub_agent_eval(*_a, **_k):
        return {
            "suite": "agent",
            "overall_score": 0.62,
            "passed_cases": 1,
            "total_cases": 2,
            "outcome_counts": {"improved": 1, "accepted_no_delta": 1},
            "cases": [
                {
                    "name": "apply_ok",
                    "score": 0.9,
                    "passed": True,
                    "details": {"outcome": "improved", "delta": -0.2, "checks": ["objective_improved"]},
                },
                {
                    "name": "apply_sidecar",
                    "score": 0.35,
                    "passed": False,
                    "details": {"outcome": "accepted_no_delta", "delta": 0.0, "checks": ["accepted_no_delta"]},
                },
            ],
        }

    monkeypatch.setattr("codeevolve.eval.agent_eval.run_agent_eval", _stub_agent_eval)
    ev = run_evaluation(tmp_path / "eval_work", suite="agent")
    assert ev.suite == "agent"
    assert ev.agent_score == 0.62
    assert ev.overall_score == 0.62
    assert ev.synthetic_score is None
    assert "Agent objective outcomes" in ev.markdown
    assert "accepted_no_delta=1" in ev.markdown


def test_benchmark_projection_carries_outcome() -> None:
    report = {
        "cases": [
            {
                "name": "apply_debt",
                "score": 0.8,
                "passed": True,
                "details": {"outcome": "improved", "delta": -0.1, "checks": ["objective_improved"]},
            }
        ]
    }
    cases = benchmark_cases_from_agent_report(report)
    assert cases[0].name == "apply_debt"
    assert any(c.name == "outcome:improved" and c.ok for c in cases[0].checks)
