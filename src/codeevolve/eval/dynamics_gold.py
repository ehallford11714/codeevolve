"""Eval suite for dynamical provenance + deliberation packs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from codeevolve.eval.benchmarks import BenchmarkCase, CheckResult
from codeevolve.gitlog import CommitRecord
from codeevolve.provenance.dynamics import build_dynamics, build_state_trajectory, compute_impulse_responses
from codeevolve.provenance.ledger import build_provenance_ledger
from codeevolve.provenance.schema import validate_deliberation_pack


def _planted_commits() -> list[CommitRecord]:
    commits: list[CommitRecord] = []
    base = datetime(2023, 1, 10, tzinfo=timezone.utc)
    sha = 0
    for month in range(18):
        n = 3 if month < 4 else (14 if month < 10 else (8 if month < 13 else 4))
        reverts = 3 if 10 <= month <= 12 else 0
        for j in range(n):
            sha += 1
            commits.append(
                CommitRecord(
                    sha=f"{sha:040d}",
                    parents=[f"{sha-1:040d}"] if sha > 1 else [],
                    author=f"dev{j % 3}",
                    email=f"dev{j % 3}@ex.com",
                    timestamp=base + timedelta(days=30 * month + j),
                    subject=("Revert x" if j < reverts else f"feat {month}-{j}"),
                    is_revert=j < reverts,
                    files=[f"src/mod{month % 2}.py", "src/shared.py"][: 2 if j % 2 == 0 else 1],
                    insertions=20 + month,
                    deletions=5,
                )
            )
    return commits


def score_state_trajectory() -> BenchmarkCase:
    commits = _planted_commits()
    samples = build_state_trajectory(commits)
    checks = [
        CheckResult("enough_months", len(samples) >= 12, f"n={len(samples)}"),
        CheckResult(
            "has_coords",
            all(hasattr(s, "activity") and hasattr(s, "instability") for s in samples[:3]),
            "activity/instability present",
        ),
        CheckResult(
            "zscored_spread",
            max(abs(s.activity) for s in samples) > 0.1,
            f"max|activity|={max(abs(s.activity) for s in samples):.3f}",
        ),
    ]
    passed = sum(1 for c in checks if c.ok)
    return BenchmarkCase(
        name="dynamics_state_trajectory",
        passed=passed,
        failed=len(checks) - passed,
        checks=checks,
        score=round(passed / max(1, len(checks)), 4),
    )


def score_impulse_and_basins() -> BenchmarkCase:
    commits = _planted_commits()
    samples = build_state_trajectory(commits)
    events = [
        {
            "kind": "major_release",
            "label": "v2.0.0",
            "when": "2023-07-01T00:00:00+00:00",
            "stage_hint": "growth",
        },
        {
            "kind": "revert_storm",
            "label": "storm",
            "when": "2023-11-01T00:00:00+00:00",
            "stage_hint": "disturbance",
        },
    ]
    impulses = compute_impulse_responses(samples, events, horizon=3)
    report = {
        "repo": "planted",
        "fatigue": {"weekly": []},
        "selection": {"pressure_score": 0.4},
        "hierarchy_trends": {"branch_trends": []},
        "ecology": {
            "global_stage": "growth",
            "calibration": {
                "events": {"events": events},
                "segments": [
                    {
                        "stage": "growth",
                        "start": "2023-01-01T00:00:00+00:00",
                        "end": "2023-10-01T00:00:00+00:00",
                        "source": "test",
                        "confidence": 0.7,
                    },
                    {
                        "stage": "disturbance",
                        "start": "2023-10-01T00:00:00+00:00",
                        "end": "2023-12-01T00:00:00+00:00",
                        "source": "test",
                        "confidence": 0.6,
                    },
                ],
                "changepoints": {"months": [], "points": []},
            },
        },
        "taxonomy": {"clades": [], "allocations": []},
    }
    dyn = build_dynamics(report, commits)
    checks = [
        CheckResult("impulse_count", len(impulses) >= 1, f"impulses={len(impulses)}"),
        CheckResult("basins", len(dyn.basins) >= 1, f"basins={len(dyn.basins)}"),
        CheckResult("samples", len(dyn.samples) >= 12, f"samples={len(dyn.samples)}"),
    ]
    passed = sum(1 for c in checks if c.ok)
    return BenchmarkCase(
        name="dynamics_impulse_basins",
        passed=passed,
        failed=len(checks) - passed,
        checks=checks,
        score=round(passed / max(1, len(checks)), 4),
        report_summary={"impulses": len(impulses), "basins": len(dyn.basins)},
    )


def score_ledger_and_schema() -> BenchmarkCase:
    commits = _planted_commits()
    tiny = {
        "repo": "planted",
        "taxonomy": {
            "clades": [
                {
                    "id": "clade_00",
                    "label": "core",
                    "layer": "core",
                    "files": ["src/shared.py"],
                    "file_count": 1,
                    "churn": 10,
                }
            ],
            "allocations": [
                {
                    "sha": c.sha,
                    "path": c.files[0],
                    "clade_id": "clade_00",
                    "insertions": c.insertions,
                    "deletions": c.deletions,
                }
                for c in commits[:30]
            ],
        },
        "genetics": {"lineages": [], "gene_flow": [], "hgt_suspects": []},
        "ecology": {
            "global_stage": "growth",
            "calibration": {
                "confidence": 0.6,
                "events": {
                    "events": [
                        {
                            "kind": "major_release",
                            "label": "v1",
                            "when": "2023-06-01T00:00:00+00:00",
                            "stage_hint": "growth",
                        }
                    ]
                },
                "changepoints": {"months": [], "points": []},
                "segments": [
                    {
                        "stage": "growth",
                        "start": "2023-01-01T00:00:00+00:00",
                        "end": "2023-12-01T00:00:00+00:00",
                        "confidence": 0.6,
                    }
                ],
                "anchors": [],
            },
        },
        "blast_radius": [
            {"path": "src/shared.py", "co_changers": 12, "blast_score": 0.3},
        ],
        "symbols": {
            "symbols": [
                {"qualname": "src/shared.py::run", "kind": "function", "path": "src/shared.py", "line": 1}
            ]
        },
        "cst_evolution": {
            "deltas": [{"path": "src/shared.py", "node": "function", "delta": 2, "window": "late"}],
            "windows": [{"label": "late", "counts": {"function": 3}}],
        },
        "selection": {"pressure_score": 0.2, "recent_issues": [], "recent_prs": []},
        "diff": {},
        "hypothesis_panel": {"claims": []},
        "hierarchy_trends": {"branch_trends": [], "next_experiments": []},
        "risk": {
            "failure_points": [
                {
                    "id": "fp_shared",
                    "title": "shared hotspot",
                    "path": "src/shared.py",
                    "clade_id": "clade_00",
                    "severity": "high",
                    "kind": "hotspot",
                }
            ]
        },
        "drift": {"clade_drift": []},
        "signal_confidence": {},
    }
    dyn = build_dynamics(tiny, commits)
    tiny["dynamics"] = dyn.to_dict()
    ledger = build_provenance_ledger(tiny)
    kinds = {r.kind for r in ledger.records}
    pack = ledger.deliberation_pack()
    errors = validate_deliberation_pack(pack)
    risk_frame = ledger.expand_frame("frame:risk:fp_shared")
    has_blast_link = False
    if risk_frame:
        has_blast_link = any(
            e.get("kind") == "blast_radius" or "blast" in str(e.get("record_id") or "")
            for e in risk_frame.get("evidence_records") or []
        ) or any(
            e.kind == "blast_radius" or "blast" in e.record_id
            for f in ledger.frames
            if f.id == "frame:risk:fp_shared"
            for e in f.evidence
        )
    checks = [
        CheckResult("state_or_trajectory", bool(kinds & {"state_sample", "trajectory"}), f"kinds={sorted(kinds)[:12]}"),
        CheckResult("blast_radius", "blast_radius" in kinds, "blast records"),
        CheckResult("symbol", "symbol" in kinds, "symbol records"),
        CheckResult("cst_delta", "cst_delta" in kinds, "cst records"),
        CheckResult("schema_valid", len(errors) == 0, f"errors={errors[:3]}"),
        CheckResult("frames", len(ledger.frames) >= 1, f"frames={len(ledger.frames)}"),
        CheckResult("blast_on_risk", has_blast_link, "risk frame measures blast"),
    ]
    passed = sum(1 for c in checks if c.ok)
    return BenchmarkCase(
        name="dynamics_ledger_schema",
        passed=passed,
        failed=len(checks) - passed,
        checks=checks,
        score=round(passed / max(1, len(checks)), 4),
    )


def run_dynamics_eval(work_dir: Path | None = None) -> list[BenchmarkCase]:
    _ = work_dir
    return [
        score_state_trajectory(),
        score_impulse_and_basins(),
        score_ledger_and_schema(),
    ]
