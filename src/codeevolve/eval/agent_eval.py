"""Agent evaluation suite — fixture repos with planted debt/hotspots."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.eval.fixtures import build_coupled_hotspot


@dataclass
class AgentEvalCase:
    name: str
    objective: str
    expect_proposal: bool = True
    expect_cognition: bool = True
    min_memory: int = 1
    apply: bool = False
    expect_pr_pack: bool = False
    expect_blast: bool = False
    expect_rollback_or_accept: bool = False
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "objective": self.objective,
            "expect_proposal": self.expect_proposal,
            "expect_cognition": self.expect_cognition,
            "min_memory": self.min_memory,
            "apply": self.apply,
            "expect_pr_pack": self.expect_pr_pack,
            "expect_blast": self.expect_blast,
            "expect_rollback_or_accept": self.expect_rollback_or_accept,
            "tags": list(self.tags),
        }


@dataclass
class AgentEvalResult:
    name: str
    score: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "passed": self.passed,
            "details": dict(self.details),
        }


CASES: list[AgentEvalCase] = [
    AgentEvalCase("dry_run_refactor", "follow_refactor", tags=["dry"], expect_pr_pack=True),
    AgentEvalCase("dry_run_debt", "reduce_debt", tags=["dry", "debt"], expect_pr_pack=True),
    AgentEvalCase("cognition_spawn", "reduce_risk", tags=["cognition"]),
    AgentEvalCase(
        "apply_debt_artifact",
        "reduce_debt",
        apply=True,
        expect_pr_pack=True,
        expect_blast=True,
        expect_rollback_or_accept=True,
        tags=["apply"],
    ),
    AgentEvalCase(
        "apply_pass_tests",
        "pass_tests",
        apply=True,
        expect_rollback_or_accept=True,
        tags=["apply", "tests"],
    ),
]


_APPLY_OUTCOME_RANK = {
    "improved": 4,
    "rolled_back": 3,
    "accepted_no_delta": 2,
    "no_apply": 1,
    "none": 0,
}

_PASS_FLOOR = 0.55


def _notes_text(rnd: dict[str, Any]) -> str:
    return " ".join(str(x) for x in (rnd.get("notes") or [])).lower()


def _score_blob(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def classify_round_outcome(rnd: dict[str, Any]) -> str:
    """Classify one agent round: improved | rolled_back | accepted_no_delta | no_apply | none."""
    after = _score_blob(rnd.get("score_after"))
    notes = _notes_text(rnd)
    accepted = bool(rnd.get("accepted"))
    improved = bool(after.get("improved"))
    if accepted and improved:
        return "improved"
    if "rolled back" in notes:
        return "rolled_back"
    if accepted and not improved:
        return "accepted_no_delta"
    if rnd.get("proposal") and not rnd.get("applied"):
        return "no_apply"
    return "none"


def classify_run_outcome(run: dict[str, Any], *, apply: bool) -> str:
    """Best outcome across rounds. Apply runs prefer objective delta; dry-run is delta_ready."""
    rounds = [r for r in (run.get("rounds") or []) if isinstance(r, dict)]
    if not apply:
        before = _score_blob((rounds[0].get("score_before") if rounds else None) or run.get("final_score"))
        if before.get("value") is not None:
            return "delta_ready"
        return "none"
    best = "none"
    best_rank = -1
    for rnd in rounds:
        label = classify_round_outcome(rnd)
        rank = _APPLY_OUTCOME_RANK.get(label, 0)
        if rank > best_rank:
            best, best_rank = label, rank
    final = _score_blob(run.get("final_score"))
    if final.get("improved") and best_rank < _APPLY_OUTCOME_RANK["improved"]:
        return "improved"
    return best


def _delta_from_run(run: dict[str, Any]) -> float | None:
    for rnd in reversed(run.get("rounds") or []):
        if not isinstance(rnd, dict):
            continue
        after = _score_blob(rnd.get("score_after"))
        if after.get("delta") is not None:
            try:
                return float(after["delta"])
            except (TypeError, ValueError):
                pass
    final = _score_blob(run.get("final_score"))
    if final.get("delta") is not None:
        try:
            return float(final["delta"])
        except (TypeError, ValueError):
            return None
    return None


def _score_run(case: AgentEvalCase, run: dict[str, Any], work_dir: Path) -> AgentEvalResult:
    """Score objective delta (apply) or delta-readiness (dry-run), not artifact presence."""
    checks: list[str] = []
    score = 0.0
    rounds = [r for r in (run.get("rounds") or []) if isinstance(r, dict)]
    outcome = classify_run_outcome(run, apply=case.apply)
    delta = _delta_from_run(run)
    prop = (rounds[0].get("proposal") if rounds else None) or {}
    if not isinstance(prop, dict):
        prop = {}

    if case.apply:
        if outcome == "improved":
            score += 0.70
            checks.append("objective_improved")
        elif outcome == "rolled_back":
            score += 0.55
            checks.append("rolled_back_cleanly")
        elif outcome == "accepted_no_delta":
            score += 0.15
            checks.append("accepted_no_delta")
        elif outcome == "no_apply":
            checks.append("apply_requested_no_write")
        else:
            checks.append("no_outcome")
        if rounds:
            score += 0.10
            checks.append("has_rounds")
        if run.get("status") in {"ok", "exhausted", "target_reached", "budget_stop"}:
            score += 0.10
            checks.append("status_ok")
        if (work_dir / "session.json").is_file() or run.get("session"):
            score += 0.10
            checks.append("session")
    else:
        before = _score_blob((rounds[0].get("score_before") if rounds else None) or run.get("final_score"))
        if before.get("value") is not None:
            score += 0.35
            checks.append("baseline_score")
        if prop.get("falsifier") and prop.get("measure"):
            score += 0.25
            checks.append("measurable_proposal")
        if prop.get("frame_ids"):
            score += 0.15
            checks.append("framed_proposal")
        if run.get("status") in {"ok", "exhausted", "target_reached", "budget_stop"}:
            score += 0.15
            checks.append("status_ok")
        if (work_dir / "session.json").is_file() or run.get("session"):
            score += 0.10
            checks.append("session")
        if outcome == "delta_ready":
            checks.append("delta_ready")

    score = min(score, 1.0)
    passed = score >= _PASS_FLOOR
    return AgentEvalResult(
        name=case.name,
        score=round(score, 3),
        passed=passed,
        details={
            "checks": checks,
            "status": run.get("status"),
            "objective": case.objective,
            "outcome": outcome,
            "delta": delta,
            "apply": case.apply,
        },
    )


def benchmark_cases_from_agent_report(report: dict[str, Any]) -> list[Any]:
    """Project agent eval cases into BenchmarkCase for the combined runner."""
    from codeevolve.eval.benchmarks import BenchmarkCase, CheckResult

    cases: list[BenchmarkCase] = []
    for row in report.get("cases") or []:
        if not isinstance(row, dict):
            continue
        details = row.get("details") or {}
        checks: list[CheckResult] = []
        for name in details.get("checks") or []:
            checks.append(CheckResult(str(name), True, "ok"))
        outcome = str(details.get("outcome") or "none")
        passed_case = bool(row.get("passed"))
        checks.append(
            CheckResult(
                f"outcome:{outcome}",
                passed_case,
                f"delta={details.get('delta')}",
            )
        )
        n_ok = sum(1 for c in checks if c.ok)
        n_fail = sum(1 for c in checks if not c.ok)
        cases.append(
            BenchmarkCase(
                name=str(row.get("name") or "agent"),
                passed=n_ok,
                failed=n_fail,
                checks=checks,
                score=float(row.get("score") or 0.0),
                report_summary=dict(details) if isinstance(details, dict) else {},
            )
        )
    return cases


def _ensure_fixture(root: Path) -> Path:
    try:
        spec = build_coupled_hotspot(root)
        return root / spec.name
    except Exception:
        tiny = root / "tiny_agent_fixture"
        if tiny.exists():
            return tiny
        tiny.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=tiny, check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tiny), "config", "user.email", "t@e.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tiny), "config", "user.name", "t"],
            check=True,
            capture_output=True,
        )
        (tiny / "src").mkdir(exist_ok=True)
        (tiny / "src" / "app.py").write_text(
            "def main():\n    return 1  # TODO debt\n",
            encoding="utf-8",
        )
        (tiny / "tests").mkdir(exist_ok=True)
        (tiny / "tests" / "test_app.py").write_text(
            "def test_ok():\n    assert True\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(tiny), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tiny), "commit", "-m", "init"],
            check=True,
            capture_output=True,
        )
        return tiny


def _ensure_apply_fixture(root: Path) -> Path:
    """Fixture with TODO debt + initially failing test that can be fixed by artifact."""
    path = root / "apply_fixture"
    if path.exists():
        return path
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    for k, v in (("user.email", "t@e.com"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(path), "config", k, v], check=True, capture_output=True)
    (path / "src").mkdir(exist_ok=True)
    (path / "src" / "core.py").write_text(
        "def process(x):\n    # TODO: simplify\n    # FIXME: brittle\n    return x\n",
        encoding="utf-8",
    )
    (path / "src" / "api.py").write_text(
        "from src.core import process\n\ndef handle(x):\n    return process(x)\n",
        encoding="utf-8",
    )
    (path / "tests").mkdir(exist_ok=True)
    (path / "tests" / "test_core.py").write_text(
        "from src.core import process\n\ndef test_process():\n    assert process(1) == 1\n",
        encoding="utf-8",
    )
    (path / "pyproject.toml").write_text(
        '[project]\nname="af"\nversion="0"\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], check=True, capture_output=True)
    # plant co-change history
    for i in range(4):
        (path / "src" / "core.py").write_text(
            f"def process(x):\n    # TODO: simplify {i}\n    # FIXME: brittle\n    return x\n",
            encoding="utf-8",
        )
        (path / "src" / "api.py").write_text(
            f"from src.core import process\n\ndef handle(x):\n    return process(x)  # churn {i}\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(path), "commit", "-m", f"churn {i}"],
            check=True,
            capture_output=True,
        )
    return path


def run_agent_eval(
    work_dir: Path | str | None = None,
    *,
    cases: list[AgentEvalCase] | None = None,
    include_apply: bool = True,
) -> dict[str, Any]:
    """Build a fixture repo and run the agent for each case (dry + optional apply)."""
    from codeevolve.agent import run_agent

    root = Path(work_dir or Path.cwd() / ".codeevolve_eval" / "agent")
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("CODEEVOLVE_DISABLE_WEB", "1")
    os.environ.setdefault("CODEEVOLVE_SKIP_HF", "1")
    os.environ.setdefault("CODEEVOLVE_SKIP_EMBED", "1")
    os.environ.setdefault("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")

    dry_fixture = _ensure_fixture(root)
    apply_fixture = _ensure_apply_fixture(root) if include_apply else dry_fixture

    selected = cases or CASES
    if not include_apply:
        selected = [c for c in selected if not c.apply]

    results: list[AgentEvalResult] = []
    for case in selected:
        fixture_path = apply_fixture if case.apply else dry_fixture
        case_dir = root / "runs" / case.name
        case_dir.mkdir(parents=True, exist_ok=True)
        run = run_agent(
            fixture_path,
            case.objective,
            max_rounds=1,
            apply=case.apply,
            llm="heuristic",
            max_commits=80,
            cognition=True,
            spawn_subagents=True,
            allow_web=False,
            max_subagents=1,
            use_worktree=False,
            auto_approve=True,
            run_tests_on_apply=case.apply and case.objective == "pass_tests",
            resume=False,
            write_pr_review=True,
        )
        # copy artifacts into case_dir for scoring
        agent_dir = Path(fixture_path) / ".codeevolve" / "agent"
        payload = run.to_dict()
        (case_dir / "run.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        results.append(_score_run(case, payload, agent_dir if agent_dir.is_dir() else case_dir))

    overall = sum(r.score for r in results) / max(1, len(results))
    outcome_counts: dict[str, int] = {}
    for r in results:
        key = str((r.details or {}).get("outcome") or "none")
        outcome_counts[key] = outcome_counts.get(key, 0) + 1
    report = {
        "suite": "agent",
        "overall_score": round(overall, 3),
        "passed_cases": sum(1 for r in results if r.passed),
        "total_cases": len(results),
        "pass_floor": _PASS_FLOOR,
        "outcome_counts": outcome_counts,
        "fixture": str(dry_fixture),
        "apply_fixture": str(apply_fixture),
        "cases": [r.to_dict() for r in results],
    }
    (root / "agent_eval.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
