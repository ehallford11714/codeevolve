"""Precedent search over past decisions and pivots (token overlap; not FastRP)."""

from __future__ import annotations

import re
from typing import Any

from codeevolve.graph.model import ContextGraph
from codeevolve.graph.traverse import shortest_path, spreading_rank, tokenize, wavefront

_SPLIT = re.compile(r"[^a-z0-9:/_.-]+")

PRECEDENT_KINDS = ("decision", "pivot", "proposal", "frame", "reflection", "score")


def precedent_search(
    graph: ContextGraph,
    query: str | dict[str, Any] | None,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Similar past decisions/pivots. Silent graphs return insufficient (empty)."""
    if isinstance(query, dict):
        blob = " ".join(
            str(query.get(k) or "")
            for k in ("text", "label", "stance", "outcome", "summary", "id")
        )
        tokens = tokenize(blob)
        seed_id = str(query.get("id") or "")
    else:
        tokens = tokenize(str(query or ""))
        seed_id = ""
    if not tokens and not seed_id:
        return []
    scored: list[tuple[float, str]] = []
    seed_scores: dict[str, float] = {}
    from codeevolve.graph.control import window_open

    for n in graph.nodes.values():
        if n.kind not in PRECEDENT_KINDS:
            continue
        if not window_open(n):
            continue
        blob = n.blob()
        hits = sum(1 for t in tokens if t in blob) if tokens else 0
        if seed_id and n.id == seed_id:
            hits += 2
        if not hits:
            continue
        extra = 0.15 if n.kind == "decision" else 0.08 if n.kind == "pivot" else 0.0
        score = hits / max(1, len(tokens) or 1) + extra
        scored.append((score, n.id))
        seed_scores[n.id] = score
    if not scored:
        return []
    spread = spreading_rank(graph, seed_scores, iterations=3, decay=0.45, max_nodes=120)
    ranked = sorted(
        ((max(s, spread.get(nid, 0.0)), nid) for s, nid in scored),
        key=lambda x: -x[0],
    )
    seeds = [nid for _s, nid in ranked[:8]]
    wave = {row["id"]: row for row in wavefront(graph, seeds, budget=40, token_scores=seed_scores, max_depth=2)}
    out: list[dict[str, Any]] = []
    for score, nid in ranked[: max(1, limit)]:
        n = graph.nodes[nid]
        row = n.to_dict()
        row["score"] = round(float(score), 4)
        w = wave.get(nid)
        if w:
            row["hops"] = w.get("hops", 0)
            row["path"] = w.get("path")
        if seed_id and seed_id in graph.nodes and seed_id != nid:
            row["geodesic"] = shortest_path(graph, seed_id, nid, max_depth=8)
        out.append(row)
    return out
