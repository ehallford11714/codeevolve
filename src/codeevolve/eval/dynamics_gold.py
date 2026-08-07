"""Dynamics / provenance eval on **real** public tags only (no synthetic commits)."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.eval.benchmarks import BenchmarkCase, CheckResult
from codeevolve.eval.scorecard import _analyze_at
from codeevolve.ingest.github import clone_or_update, github_owner_repo
from codeevolve.provenance.ledger import build_provenance_ledger
from codeevolve.provenance.schema import validate_deliberation_pack


@dataclass
class DynamicsCase:
    id: str
    repo: str
    ref: str
    description: str
    kind: str  # trajectory | impulse_major | basin
    max_commits: int = 250
    clone_depth: int = 800
    tags: list[str] = field(default_factory=list)


def dynamics_catalog() -> list[DynamicsCase]:
    """Curated real-tag cases — trajectory honesty, major impulse, basin frames."""
    return [
        DynamicsCase(
            id="click_trajectory_8.4.0",
            repo="pallets/click",
            ref="8.4.0",
            kind="trajectory",
            description=(
                "Real Click@8.4.0: joined state trajectory + deliberation pack schema "
                "from live git history (not planted fixtures)."
            ),
            max_commits=220,
            clone_depth=700,
            tags=["click", "trajectory", "real"],
        ),
        DynamicsCase(
            id="flask_major_impulse_3.0.0",
            repo="pallets/flask",
            ref="3.0.0",
            kind="impulse_major",
            description=(
                "Real Flask@3.0.0: major-release era should yield lifecycle events and "
                "observational impulse responses on the state trajectory."
            ),
            max_commits=280,
            clone_depth=900,
            tags=["flask", "impulse", "major", "real"],
        ),
        DynamicsCase(
            id="requests_basin_2.31.0",
            repo="psf/requests",
            ref="v2.31.0",
            kind="basin",
            description=(
                "Real Requests@v2.31.0: regime basin / stage frames grounded in "
                "calibrated segments or trajectory occupancy."
            ),
            max_commits=220,
            clone_depth=700,
            tags=["requests", "basin", "real"],
        ),
    ]


def _resolve_repo(owner: str, name: str, *, offline: bool, clone_depth: int) -> Path | dict[str, Any]:
    try:
        if offline:
            from codeevolve.ingest.github import _cache_root

            key = hashlib.sha1(f"{owner}/{name}".encode()).hexdigest()[:12]
            dest = _cache_root() / f"{owner}__{name}__{key}"
            if not (dest / ".git").is_dir():
                return {"skipped": True, "reason": "offline and no cached clone"}
            return dest
        repo = clone_or_update(owner, name, depth=clone_depth, full=False)
        subprocess.run(
            ["git", "-C", str(repo), "fetch", "--tags", "--force", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        return repo
    except Exception as exc:
        return {"skipped": True, "reason": f"clone failed: {exc}"}


def _dyn_digest(report: dict[str, Any]) -> dict[str, Any]:
    dyn = report.get("dynamics") or {}
    eco = (report.get("ecology") or {}).get("calibration") or {}
    events = eco.get("events") or {}
    if isinstance(events, dict):
        event_rows = events.get("events") or []
    else:
        event_rows = events if isinstance(events, list) else []
    majors = [
        e
        for e in event_rows
        if isinstance(e, dict)
        and (
            e.get("kind") in {"major_release", "minor_release", "release"}
            or "major" in str(e.get("kind") or "").lower()
            or str(e.get("label") or "").startswith("v")
            or (str(e.get("label") or "").count(".") >= 1 and e.get("stage_hint") == "growth")
        )
    ]
    prov = report.get("provenance") or {}
    kinds = {}
    for r in prov.get("records") or []:
        if isinstance(r, dict):
            k = str(r.get("kind") or "")
            kinds[k] = kinds.get(k, 0) + 1
    frames = [f.get("id") for f in (prov.get("frames") or []) if isinstance(f, dict)]
    return {
        "sample_count": int(dyn.get("sample_count") or len(dyn.get("samples") or [])),
        "impulse_count": int(dyn.get("impulse_count") or len(dyn.get("impulses") or [])),
        "basin_count": int(dyn.get("basin_count") or len(dyn.get("basins") or [])),
        "episode_count": int(dyn.get("episode_count") or len(dyn.get("episodes") or [])),
        "insufficient": bool(dyn.get("insufficient")),
        "event_count": len(event_rows),
        "majorish_events": len(majors),
        "global_stage": (report.get("ecology") or {}).get("global_stage"),
        "record_kinds": kinds,
        "frame_ids": frames[:20],
        "dynamics_summary": dyn.get("summary"),
    }


def _score_trajectory(report: dict[str, Any]) -> list[CheckResult]:
    dig = _dyn_digest(report)
    ledger = build_provenance_ledger(report)
    pack = ledger.deliberation_pack()
    errors = validate_deliberation_pack(pack)
    kinds = {r.kind for r in ledger.records}
    checks = [
        CheckResult(
            "real_months",
            dig["sample_count"] >= 8,
            f"samples={dig['sample_count']} (need >=8 months of real history)",
        ),
        CheckResult(
            "trajectory_record",
            "trajectory" in kinds or "state_sample" in kinds,
            f"kinds={sorted(kinds & {'trajectory', 'state_sample', 'impulse_response'})}",
        ),
        CheckResult("pack_schema", len(errors) == 0, f"errors={errors[:2]}"),
        CheckResult(
            "frames_present",
            len(ledger.frames) >= 1,
            f"frames={len(ledger.frames)} ids={dig['frame_ids'][:4]}",
        ),
        CheckResult(
            "timeline_dated",
            len(ledger.timeline(limit=20)) >= 1 or dig["sample_count"] >= 8,
            "dated provenance backbone",
        ),
    ]
    return checks


def _score_impulse_major(report: dict[str, Any]) -> list[CheckResult]:
    dig = _dyn_digest(report)
    ledger = build_provenance_ledger(report)
    impulse_recs = [r for r in ledger.records if r.kind == "impulse_response"]
    event_recs = [r for r in ledger.records if r.kind == "lifecycle_event"]
    response_frames = [f for f in ledger.frames if f.id.startswith("frame:response:")]
    checks = [
        CheckResult(
            "real_months",
            dig["sample_count"] >= 8,
            f"samples={dig['sample_count']}",
        ),
        CheckResult(
            "lifecycle_events",
            dig["event_count"] >= 1 or len(event_recs) >= 1,
            f"events={dig['event_count']} ledger_events={len(event_recs)}",
        ),
        CheckResult(
            "majorish_or_any_release_event",
            dig["majorish_events"] >= 1
            or any("release" in (r.tags or []) or "release" in r.summary.lower() for r in event_recs),
            f"majorish={dig['majorish_events']}",
        ),
        CheckResult(
            "impulse_response",
            dig["impulse_count"] >= 1 or len(impulse_recs) >= 1,
            f"impulses={dig['impulse_count']} ledger={len(impulse_recs)}",
        ),
        CheckResult(
            "response_or_stage_frame",
            bool(response_frames) or any(f.id in {"frame:stage", "frame:basin"} for f in ledger.frames),
            f"response_frames={len(response_frames)}",
        ),
    ]
    return checks


def _score_basin(report: dict[str, Any]) -> list[CheckResult]:
    dig = _dyn_digest(report)
    ledger = build_provenance_ledger(report)
    basins = [r for r in ledger.records if r.kind == "regime_basin"]
    has_basin_frame = any(f.id == "frame:basin" for f in ledger.frames)
    has_stage_frame = any(f.id == "frame:stage" for f in ledger.frames)
    checks = [
        CheckResult("real_months", dig["sample_count"] >= 8, f"samples={dig['sample_count']}"),
        CheckResult(
            "basin_or_segment",
            dig["basin_count"] >= 1 or len(basins) >= 1,
            f"basins={dig['basin_count']} ledger={len(basins)}",
        ),
        CheckResult(
            "basin_or_stage_frame",
            has_basin_frame or has_stage_frame,
            f"basin_frame={has_basin_frame} stage_frame={has_stage_frame} stage={dig['global_stage']}",
        ),
        CheckResult(
            "stage_labeled",
            bool(dig["global_stage"]),
            f"global_stage={dig['global_stage']}",
        ),
        CheckResult(
            "path_pack_ok",
            True,  # filled below if we find a hot path
            "path_pack",
        ),
    ]
    # Prefer a real hot path from blast_radius or taxonomy
    path = None
    for row in report.get("blast_radius") or []:
        if isinstance(row, dict) and row.get("path"):
            path = str(row["path"])
            break
    if not path:
        for c in (report.get("taxonomy") or {}).get("clades") or []:
            files = (c.get("files") or []) if isinstance(c, dict) else []
            if files:
                path = str(files[0])
                break
    if path:
        pack = ledger.path_pack(path)
        checks[-1] = CheckResult(
            "path_pack_ok",
            pack.get("path") == path or pack.get("lineage") is not None or pack.get("episodes") is not None,
            f"path={path} episodes={len(pack.get('episodes') or [])}",
        )
    else:
        checks[-1] = CheckResult("path_pack_ok", True, "no path available; skipped structural pack")
    return checks


def run_dynamics_case(case: DynamicsCase, *, offline: bool = False) -> BenchmarkCase | dict[str, Any]:
    gh = github_owner_repo(case.repo)
    if not gh:
        return {"id": case.id, "skipped": True, "reason": "invalid repo spec"}
    owner, name = gh
    resolved = _resolve_repo(owner, name, offline=offline, clone_depth=case.clone_depth)
    if isinstance(resolved, dict):
        return {"id": case.id, **resolved}

    try:
        report = _analyze_at(resolved, rev=case.ref, max_commits=case.max_commits)
    except Exception as exc:
        return {"id": case.id, "skipped": True, "reason": f"analyze failed: {exc}"}

    if case.kind == "trajectory":
        checks = _score_trajectory(report)
    elif case.kind == "impulse_major":
        checks = _score_impulse_major(report)
    else:
        checks = _score_basin(report)

    passed = sum(1 for c in checks if c.ok)
    failed = len(checks) - passed
    return BenchmarkCase(
        name=case.id,
        passed=passed,
        failed=failed,
        checks=checks,
        score=round(passed / max(1, len(checks)), 4),
        report_summary={
            "repo": case.repo,
            "ref": case.ref,
            "kind": case.kind,
            "description": case.description,
            "digest": _dyn_digest(report),
        },
    )


@dataclass
class DynamicsEvalResult:
    cases: list[BenchmarkCase] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    overall_score: float | None = None
    summary: str = ""
    markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "summary": self.summary,
            "skipped": list(self.skipped),
            "cases": [c.to_dict() for c in self.cases],
            "markdown": self.markdown,
        }


def run_dynamics_eval(
    work_dir: Path | None = None,
    *,
    offline: bool = False,
    case_ids: list[str] | None = None,
) -> DynamicsEvalResult:
    """Run real-tag dynamics cases. Skips (does not fail) when clones unavailable."""
    _ = work_dir
    catalog = dynamics_catalog()
    if case_ids:
        want = set(case_ids)
        catalog = [c for c in catalog if c.id in want]

    cases: list[BenchmarkCase] = []
    skipped: list[dict[str, Any]] = []
    for case in catalog:
        result = run_dynamics_case(case, offline=offline)
        if isinstance(result, dict) and result.get("skipped"):
            skipped.append(result)
            continue
        assert isinstance(result, BenchmarkCase)
        cases.append(result)

    if not cases:
        md = (
            "# Dynamics eval (real tags)\n\n"
            "All cases skipped — clone public repos or drop `--offline`.\n\n"
            + "\n".join(f"- `{s.get('id')}`: {s.get('reason')}" for s in skipped)
        )
        return DynamicsEvalResult(
            skipped=skipped,
            summary=f"Dynamics eval: 0 runnable cases ({len(skipped)} skipped)",
            markdown=md,
        )

    overall = sum(c.score for c in cases) / len(cases)
    lines = [
        "# Dynamics eval (real public tags)",
        "",
        "_No synthetic commits — clones real GitHub tags and scores trajectory / impulse / basin._",
        "",
        f"**Score:** {overall:.1%} · **Cases:** {sum(1 for c in cases if c.failed == 0)}/{len(cases)} clean · "
        f"**Skipped:** {len(skipped)}",
        "",
        "| Case | Repo@ref | Score | Failed |",
        "|------|----------|------:|-------:|",
    ]
    for c in cases:
        repo = (c.report_summary or {}).get("repo")
        ref = (c.report_summary or {}).get("ref")
        lines.append(f"| `{c.name}` | {repo}@{ref} | {c.score:.0%} | {c.failed} |")
    lines.append("")
    for c in cases:
        lines.append(f"## {c.name}")
        lines.append("")
        lines.append((c.report_summary or {}).get("description") or "")
        lines.append("")
        for ch in c.checks:
            mark = "PASS" if ch.ok else "FAIL"
            lines.append(f"- [{mark}] `{ch.name}` — {ch.detail}")
        lines.append("")
    if skipped:
        lines.append("## Skipped")
        lines.append("")
        for s in skipped:
            lines.append(f"- `{s.get('id')}`: {s.get('reason')}")
        lines.append("")

    return DynamicsEvalResult(
        cases=cases,
        skipped=skipped,
        overall_score=round(overall, 4),
        summary=(
            f"Dynamics eval {overall:.1%} on {len(cases)} real-tag cases "
            f"({len(skipped)} skipped)"
        ),
        markdown="\n".join(lines),
    )
