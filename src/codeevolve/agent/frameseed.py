"""Seed / re-rank agent steps from provenance frames (basin, delta, path packs)."""

from __future__ import annotations

from typing import Any

from codeevolve.agent.objective import Objective, ranks_steps_for_objective


def _frame_paths(frame: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for p in frame.get("context_paths") or []:
        if p:
            paths.append(str(p))
    for ev in frame.get("evidence") or []:
        note = str(ev.get("note") or "")
        # soft: evidence notes sometimes embed paths
        if "/" in note and "." in note:
            token = note.split()[0] if note.split() else ""
            if "/" in token:
                paths.append(token.strip("`,"))
    return paths


def frames_of_interest(pack: dict[str, Any] | None) -> list[dict[str, Any]]:
    frames = list((pack or {}).get("frames") or [])
    prefer_ids = ("frame:basin", "frame:delta:report", "frame:hotspot", "frame:risk")
    ranked: list[dict[str, Any]] = []
    for pref in prefer_ids:
        for f in frames:
            fid = str(f.get("id") or "")
            if fid == pref or fid.startswith(pref):
                ranked.append(f)
    # also high-confidence insufficient/assert frames with paths
    for f in frames:
        if f in ranked:
            continue
        stance = str(f.get("stance") or "")
        if stance in {"assert", "insufficient"} and (_frame_paths(f) or f.get("context_paths")):
            ranked.append(f)
    return ranked or frames[:8]


def steps_from_frames(
    objective: Objective,
    pack: dict[str, Any] | None,
    *,
    risk: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Synthesize refactor-like steps from deliberation frames."""
    steps: list[dict[str, Any]] = []
    for i, frame in enumerate(frames_of_interest(pack)):
        fid = str(frame.get("id") or f"frame:{i}")
        paths = _frame_paths(frame)
        if objective.path and objective.path not in paths:
            paths = [objective.path] + paths
        wave = "stabilize"
        if "basin" in fid or "delta" in fid:
            wave = "contain" if "delta" in fid else "stabilize"
        if objective.kind == "reduce_debt":
            wave = "pay_down"
        elif objective.kind == "pass_tests":
            wave = "stabilize"
        steps.append(
            {
                "id": f"FR-{fid.replace('frame:', '').replace(':', '-')}",
                "title": (frame.get("claim") or fid)[:120],
                "wave": wave,
                "paths": paths[:6],
                "problem_kind": "frame_seed",
                "evidence_refs": [fid]
                + [str(e.get("record_id")) for e in (frame.get("evidence") or [])[:4] if e.get("record_id")],
                "actions": [
                    f"Address frame {fid} under falsifier: {frame.get('falsifier') or 'n/a'}",
                    f"Measure: {frame.get('measure') or 're-analyze'}",
                ],
                "acceptance_criteria": [
                    f"Falsifier not triggered: {frame.get('falsifier') or 're-analyze improves signals'}",
                ],
                "priority": "P0" if "basin" in fid or "delta" in fid else "P1",
                "frame_ids": [fid],
                "falsifier": frame.get("falsifier"),
                "measure": frame.get("measure"),
                "stance": frame.get("stance"),
            }
        )
    if not steps and risk:
        return ranks_steps_for_objective(objective, None, risk)
    return steps


def ranks_steps_with_frames(
    objective: Objective,
    refactor_plan: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    pack: dict[str, Any] | None,
    *,
    prefer_frames: bool = True,
) -> list[dict[str, Any]]:
    """Merge frame-seeded steps ahead of refactor-plan ranking when frames exist."""
    plan_steps = ranks_steps_for_objective(objective, refactor_plan, risk)
    frame_steps = steps_from_frames(objective, pack, risk=risk)
    if not prefer_frames or not frame_steps:
        return plan_steps

    # Prefer basin/delta frame steps; then plan steps that share paths
    frame_paths = {p for s in frame_steps for p in (s.get("paths") or [])}
    boosted = [
        s
        for s in plan_steps
        if any(p in frame_paths or any(fp in str(p) for fp in frame_paths) for p in (s.get("paths") or []))
    ]
    rest = [s for s in plan_steps if s not in boosted]

    # Put high-signal frame steps first (basin / delta), then overlapping plan, then rest
    head = [s for s in frame_steps if "basin" in str(s.get("id")) or "delta" in str(s.get("id"))]
    if not head:
        head = frame_steps[:2]
    # Avoid duplicate path work: keep unique step ids
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in head + boosted + frame_steps + rest:
        sid = str(s.get("id"))
        if sid in seen:
            continue
        seen.add(sid)
        out.append(s)
    return out
