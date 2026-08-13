"""Delta detection and proactive surfacing (Kumar-style; no claimed Precision@5)."""

from __future__ import annotations

from typing import Any

from codeevolve.graph.model import ContextGraph, node_id


def _metric(report: dict[str, Any] | None, *path: str) -> Any:
    cur: Any = report or {}
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def delta_detect(
    prev: ContextGraph | dict[str, Any] | None,
    current: ContextGraph | dict[str, Any] | None,
    *,
    into: ContextGraph | None = None,
) -> list[dict[str, Any]]:
    """Threshold crossings: type/stage/score/stance/debt/risk. Does not invent history."""
    from codeevolve.graph.parse import parse_context

    prev_g: ContextGraph | None
    cur_g: ContextGraph | None
    prev_r: dict[str, Any] | None = prev if isinstance(prev, dict) else None
    cur_r: dict[str, Any] | None = current if isinstance(current, dict) else None
    if isinstance(prev, ContextGraph):
        prev_g = prev
    elif isinstance(prev, dict):
        prev_g = parse_context(report=prev, source="delta:prev")
    else:
        prev_g = None
    if isinstance(current, ContextGraph):
        cur_g = current
    elif isinstance(current, dict):
        cur_g = parse_context(report=current, source="delta:cur")
    else:
        cur_g = None
    events: list[dict[str, Any]] = []
    if prev_g is None or cur_g is None:
        return events

    prev_types = {n.id: n.label for n in prev_g.by_kind("type")}
    cur_types = {n.id: n.label for n in cur_g.by_kind("type")}
    for tid, label in cur_types.items():
        if tid not in prev_types:
            events.append(_event("type_added", tid, label, urgency=0.45, family="taxon"))
        elif prev_types[tid] != label:
            events.append(_event("type_changed", tid, label, urgency=0.55, family="taxon"))
    for tid in prev_types:
        if tid not in cur_types:
            events.append(_event("type_removed", tid, prev_types[tid], urgency=0.4, family="taxon"))

    def _stances(g: ContextGraph) -> dict[str, str]:
        out: dict[str, str] = {}
        for n in list(g.by_kind("frame")) + list(g.by_kind("decision")) + list(g.by_kind("proposal")):
            st = str(n.meta.get("stance") or n.label or "")
            if st:
                out[n.id] = st
        return out

    ps, cs = _stances(prev_g), _stances(cur_g)
    for nid, st in cs.items():
        if nid in ps and ps[nid] != st:
            events.append(_event("stance_changed", nid, f"{ps[nid]}→{st}", urgency=0.7, family="decision"))

    if prev_r and cur_r:
        p_stage = str(_metric(prev_r, "ecology", "global_stage") or "")
        c_stage = str(_metric(cur_r, "ecology", "global_stage") or "")
        if p_stage and c_stage and p_stage != c_stage:
            events.append(_event("stage_changed", "window:ecology", f"{p_stage}→{c_stage}", urgency=0.8, family="context"))
        p_debt = _metric(prev_r, "debt", "score")
        c_debt = _metric(cur_r, "debt", "score")
        if isinstance(p_debt, (int, float)) and isinstance(c_debt, (int, float)) and abs(c_debt - p_debt) >= 0.05:
            urg = min(1.0, abs(c_debt - p_debt) * 4)
            events.append(_event("debt_crossed", "context:debt", f"{p_debt}→{c_debt}", urgency=urg, family="context"))
        p_risk = len((_metric(prev_r, "risk", "failure_points") or []) or [])
        c_risk = len((_metric(cur_r, "risk", "failure_points") or []) or [])
        if p_risk != c_risk:
            events.append(_event("risk_count", "context:risk", f"{p_risk}→{c_risk}", urgency=0.6, family="context"))

    added = [nid for nid in cur_g.nodes if nid not in prev_g.nodes]
    removed = [nid for nid in prev_g.nodes if nid not in cur_g.nodes]
    if len(added) >= 3:
        events.append(_event("nodes_added", "delta:nodes", f"+{len(added)}", urgency=min(0.5, len(added) / 40), family="context"))
    if len(removed) >= 3:
        events.append(_event("nodes_removed", "delta:nodes", f"-{len(removed)}", urgency=min(0.45, len(removed) / 40), family="context"))

    host = into or cur_g
    for ev in events[:40]:
        nid = str(ev["id"])
        host.add_node(
            nid,
            "delta",
            label=str(ev["kind"]),
            stage="context",
            family="context",
            text=str(ev.get("text") or ""),
            source="delta_detect",
            confidence=0.6,
            meta={"urgency": ev["urgency"], "ref": ev.get("ref")},
        )
    return events


def proactive_surface(graph: ContextGraph, *, limit: int = 8) -> list[dict[str, Any]]:
    """Rank delta nodes by urgency. Does not invent Precision@5 / MTT metrics."""
    rows: list[tuple[float, dict[str, Any]]] = []
    for n in graph.by_kind("delta"):
        urg = float(n.meta.get("urgency") or 0.3)
        conf = float(n.confidence if n.confidence is not None else 0.5)
        rank = urg * (0.5 + 0.5 * conf)
        row = n.to_dict()
        row["rank"] = round(rank, 4)
        rows.append((rank, row))
    rows.sort(key=lambda x: -x[0])
    return [r for _s, r in rows[: max(1, limit)]]


def _event(kind: str, ref: str, text: str, *, urgency: float, family: str) -> dict[str, Any]:
    return {
        "id": node_id("delta", kind, ref),
        "kind": kind,
        "ref": ref,
        "text": text,
        "urgency": round(float(urgency), 4),
        "family": family,
        "stance": "insufficient" if not text else "support",
    }
