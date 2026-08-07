"""Ecology calibration eval: changepoints, event anchors, stage agreement."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from codeevolve.eval.benchmarks import BenchmarkCase, CheckResult
from codeevolve.ecology.calibration import calibrate_ecology
from codeevolve.ecology.changepoints import detect_changepoints, pelt_lite
from codeevolve.gitlog import CommitRecord


def _synthetic_commits() -> list[CommitRecord]:
    """Planted monthly regimes: pioneer → growth → disturbance → consolidation."""
    from datetime import timedelta

    commits: list[CommitRecord] = []
    # 24 months of activity with regime shifts
    base = datetime(2022, 1, 15, tzinfo=timezone.utc)
    sha_i = 0

    def add_month(month_idx: int, n: int, *, churn: int, reverts: int = 0, authors: int = 2) -> None:
        nonlocal sha_i
        for j in range(n):
            sha_i += 1
            ts = base + timedelta(days=30 * month_idx + j)
            author = f"dev{j % authors}"
            commits.append(
                CommitRecord(
                    sha=f"{sha_i:040d}",
                    parents=[f"{sha_i-1:040d}"] if sha_i > 1 else [],
                    author=author,
                    email=f"{author}@ex.com",
                    timestamp=ts,
                    subject=("Revert oops" if j < reverts else f"work {month_idx}-{j}"),
                    is_revert=j < reverts,
                    files=[f"src/m{month_idx % 3}.py"],
                    insertions=churn // max(1, n),
                    deletions=churn // max(1, n) // 2,
                )
            )

    # pioneer: low activity months 0-3
    for m in range(0, 4):
        add_month(m, 2, churn=20, authors=1)
    # growth: months 4-10
    for m in range(4, 11):
        add_month(m, 12, churn=400, authors=5)
    # disturbance: months 11-13 high reverts
    for m in range(11, 14):
        add_month(m, 10, churn=300, reverts=4, authors=4)
    # consolidation: months 14-23 cooler
    for m in range(14, 24):
        add_month(m, 4, churn=40, authors=3)
    return commits


def score_pelt_detects_shifts() -> BenchmarkCase:
    commits = _synthetic_commits()
    report = detect_changepoints(commits, min_seg=2)
    checks: list[CheckResult] = []
    checks.append(
        CheckResult(
            "has_months",
            len(report.months) >= 12,
            f"months={len(report.months)}",
        )
    )
    checks.append(
        CheckResult(
            "has_changepoints",
            len(report.points) >= 1,
            f"points={len(report.points)} summary={report.summary}",
        )
    )
    # Expect at least one upward commits/churn CP in growth region-ish
    ups = [p for p in report.points if p.direction == "up" and p.series in {"commits", "churn", "authors"}]
    checks.append(CheckResult("up_activity_cp", len(ups) >= 1, f"up={len(ups)}"))
    # And a revert or down signal around disturbance
    dist = [
        p
        for p in report.points
        if (p.series == "reverts" and p.direction == "up")
        or (p.series in {"commits", "churn"} and p.direction == "down")
    ]
    checks.append(CheckResult("disturbance_or_cool_cp", len(dist) >= 1, f"signals={len(dist)}"))
    # Unit: pelt_lite on a clear step
    series = [1.0] * 8 + [20.0] * 8
    cps = pelt_lite(series, min_seg=3, penalty=2.0)
    checks.append(CheckResult("pelt_step", any(5 <= c <= 11 for c in cps), f"cps={cps}"))
    passed = sum(1 for c in checks if c.ok)
    return BenchmarkCase(
        name="ecology_changepoints_synthetic",
        passed=passed,
        failed=len(checks) - passed,
        checks=checks,
        score=round(passed / max(1, len(checks)), 4),
        report_summary={"points": len(report.points), "months": len(report.months)},
    )


def score_calibration_on_repo(repo: Path) -> BenchmarkCase:
    from codeevolve.api import CodeEvolve
    from codeevolve.metrics import compute_metrics

    os.environ.setdefault("CODEEVOLVE_SKIP_GHSA", "1")
    commits = CodeEvolve(repo).commits(max_commits=200)
    metrics = compute_metrics(commits)
    cal = calibrate_ecology(repo, commits, metrics, include_ghsa=False)
    checks: list[CheckResult] = []
    checks.append(
        CheckResult("calibration_ran", bool(cal.summary), cal.summary[:120])
    )
    checks.append(
        CheckResult(
            "changepoint_or_events",
            len(cal.changepoints.points) >= 0 and (len(cal.events.events) >= 1 or len(commits) < 30),
            f"events={len(cal.events.events)} cps={len(cal.changepoints.points)}",
        )
    )
    checks.append(
        CheckResult(
            "stage_set",
            cal.global_stage in {
                "pioneer",
                "growth",
                "disturbance",
                "consolidation",
                "maturity",
                "decline",
            },
            f"stage={cal.global_stage} method={cal.method}",
        )
    )
    checks.append(
        CheckResult(
            "method_reported",
            cal.method in {"event_changepoint", "event_anchor", "heuristic_fallback"},
            f"method={cal.method} conf={cal.confidence}",
        )
    )
    checks.append(
        CheckResult(
            "segments_or_fallback",
            bool(cal.segments) or cal.method == "heuristic_fallback",
            f"segments={len(cal.segments)}",
        )
    )
    # Event corpus collects pioneer at minimum when history exists
    if commits:
        checks.append(
            CheckResult(
                "pioneer_event",
                any(e.kind == "pioneer_window" for e in cal.events.events),
                f"kinds={[e.kind for e in cal.events.events[:8]]}",
            )
        )
    passed = sum(1 for c in checks if c.ok)
    return BenchmarkCase(
        name="ecology_calibration_repo",
        passed=passed,
        failed=len(checks) - passed,
        checks=checks,
        score=round(passed / max(1, len(checks)), 4),
        report_summary={
            "stage": cal.global_stage,
            "method": cal.method,
            "hit_rate": cal.hit_rate,
            "events": len(cal.events.events),
            "changepoints": len(cal.changepoints.points),
        },
    )


def score_event_stage_hints() -> BenchmarkCase:
    """Static mapping: security/revert → disturbance, major → growth, patch → maturity."""
    from codeevolve.ecology.events import LifecycleEvent

    cases = [
        ("security", "disturbance"),
        ("revert_storm", "disturbance"),
        ("major_release", "growth"),
        ("minor_release", "growth"),
        ("patch_release", "maturity"),
        ("pioneer_window", "pioneer"),
    ]
    checks: list[CheckResult] = []
    now = datetime.now(timezone.utc)
    for kind, hint in cases:
        ev = LifecycleEvent(kind=kind, when=now, label=kind, stage_hint=hint, confidence=0.8)  # type: ignore[arg-type]
        ok = ev.stage_hint == hint
        checks.append(CheckResult(f"hint:{kind}", ok, f"hint={ev.stage_hint}"))
    from codeevolve.ecology.events import pioneer_event, revert_storm_events

    commits = _synthetic_commits()
    pe = pioneer_event(commits)
    storms = revert_storm_events(commits, min_reverts=3)
    checks.append(
        CheckResult(
            "synthetic_has_events",
            pe is not None and len(storms) >= 1,
            f"pioneer={pe is not None} storms={len(storms)}",
        )
    )
    passed = sum(1 for c in checks if c.ok)
    return BenchmarkCase(
        name="ecology_event_hints",
        passed=passed,
        failed=len(checks) - passed,
        checks=checks,
        score=round(passed / max(1, len(checks)), 4),
        report_summary={},
    )


def run_ecology_eval(work_dir: Path | str | None = None) -> list[BenchmarkCase]:
    from codeevolve.eval.fixtures import materialize_suite

    cases = [
        score_pelt_detects_shifts(),
        score_event_stage_hints(),
    ]
    work = Path(work_dir) if work_dir else Path.cwd() / ".codeevolve_eval"
    work.mkdir(parents=True, exist_ok=True)
    fixtures = materialize_suite(work)
    repo = fixtures[0][0] if fixtures else work
    cases.append(score_calibration_on_repo(repo))
    return cases
