"""Search a context graph and extract agentic flow walks."""

from __future__ import annotations

from typing import Any, Iterable

from codeevolve.graph.families import FLOW_KINDS, FLOW_RELS, family_of
from codeevolve.graph.model import ContextGraph, GraphNode
from codeevolve.graph.traverse import (
    STAGE_ORDER,
    bfs_expand,
    flow_walk,
    pivot_expand,
    resolve_traverse,
    spreading_rank,
    tokenize,
    wavefront,
)


def search_graph(
    graph: ContextGraph,
    query: str,
    *,
    kinds: Iterable[str] | None = None,
    stage: str | None = None,
    family: str | None = None,
    limit: int = 20,
    expand: int = 1,
    traverse: bool | str = True,
    depth: int = 2,
) -> list[dict[str, Any]]:
    """Ranked node hits. Default traverse=wave expands from token seeds."""
    tokens = tokenize(query)
    allow = {str(k) for k in kinds} if kinds else None
    token_scores: dict[str, float] = {}
    scored: list[tuple[float, GraphNode]] = []
    for n in graph.nodes.values():
        if allow and n.kind not in allow:
            continue
        if stage and n.stage != stage:
            continue
        if family and (n.family or family_of(n.kind)) != family:
            continue
        blob = n.blob()
        if not tokens:
            score = 0.15
        else:
            hits = sum(1 for t in tokens if t in blob)
            if not hits:
                continue
            score = hits / len(tokens)
            if n.kind in FLOW_KINDS:
                score += 0.08
            if any(t == n.kind or t == n.stage or t == n.family or t in n.label.lower() for t in tokens):
                score += 0.2
        scored.append((score, n))
        token_scores[n.id] = score
    scored.sort(key=lambda x: (-x[0], x[1].seq, x[1].id))
    mode = resolve_traverse(traverse)
    extra: dict[str, dict[str, Any]] = {}
    seeds = [n.id for _s, n in scored[:16]]
    if mode == "wave" and seeds:
        for row in wavefront(graph, seeds, budget=max(limit * 4, 40), token_scores=token_scores, max_depth=max(1, depth)):
            extra[row["id"]] = row
    elif mode == "bfs" and seeds:
        exp = bfs_expand(graph, seeds, depth=max(1, depth), kinds=allow, family=family, max_nodes=max(limit * 4, 40))
        for row in exp["nodes"]:
            extra[row["id"]] = row
    elif mode == "flow" and seeds:
        walk = flow_walk(graph, seeds, limit=max(limit * 3, 40))
        for i, step in enumerate(walk["steps"]):
            extra[step["id"]] = {**step, "hops": i, "path": [s["id"] for s in walk["steps"][: i + 1]]}
    elif mode == "pivot":
        pivots = [n.id for n in graph.by_kind("pivot")[:8]]
        if query:
            pivots = [n.id for _s, n in scored if n.kind == "pivot"][:8] or pivots
        for pid in pivots[:4]:
            exp = pivot_expand(graph, pid, max_nodes=max(limit * 3, 24), depth=max(1, depth))
            for row in exp.get("nodes") or []:
                extra[row["id"]] = row
    elif mode == "rw" and token_scores:
        ranks = spreading_rank(graph, token_scores, iterations=4, decay=0.5, max_nodes=200)
        for nid, sc in ranks.items():
            if nid in graph.nodes:
                extra[nid] = {"id": nid, "score": sc, "hops": 0 if nid in token_scores else 1}

    merged: dict[str, tuple[float, GraphNode, dict[str, Any]]] = {}
    for score, n in scored:
        merged[n.id] = (score, n, extra.get(n.id) or {})
    if mode != "off":
        for nid, row in extra.items():
            if nid in merged or nid not in graph.nodes:
                continue
            n = graph.nodes[nid]
            if allow and n.kind not in allow:
                continue
            if family and (n.family or family_of(n.kind)) != family:
                continue
            hops = int(row.get("hops") or 1)
            score = float(row.get("score") or token_scores.get(nid) or (0.2 / (1 + hops)))
            merged[nid] = (score, n, row)
    ranked = sorted(merged.values(), key=lambda x: (-x[0], x[1].seq, x[1].id))
    out: list[dict[str, Any]] = []
    for score, n, aux in ranked[: max(1, limit)]:
        row = n.to_dict()
        row["score"] = round(float(score), 4)
        if aux.get("hops") is not None:
            row["hops"] = aux["hops"]
        if aux.get("path"):
            row["path"] = aux["path"]
        elif aux.get("seed"):
            row["seed"] = aux["seed"]
        if expand:
            neigh = graph.neighbors(n.id, depth=expand, rels=None)
            row["neighbors"] = [
                {"id": m.id, "kind": m.kind, "label": m.label, "stage": m.stage, "family": m.family}
                for m in neigh[:8]
            ]
        out.append(row)
    return out


def agentic_flow(
    graph: ContextGraph,
    *,
    query: str | None = None,
    kernel: str | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    """Ordered sense → deliberate → act → verify walk for agent traces."""
    seeds: list[str] = []
    if kernel:
        kid = f"kernel:{kernel}"
        if kid in graph.nodes:
            seeds.append(kid)
        seeds.extend(n.id for n in graph.nodes.values() if n.kind == "kernel" and kernel in n.label)
    if query:
        hits = search_graph(graph, query, kinds=FLOW_KINDS, limit=12, expand=0, traverse="flow")
        seeds.extend(h["id"] for h in hits)
    if not seeds:
        seeds = [n.id for n in graph.by_kind("run")]
        if not seeds:
            seeds = [n.id for n in graph.by_kind("pivot")][:4]
        if not seeds:
            seeds = [n.id for n in sorted(graph.nodes.values(), key=lambda x: x.seq) if n.kind in FLOW_KINDS][:4]

    walk = flow_walk(graph, seeds, limit=limit)
    keep = {s["id"] for s in walk["steps"]}
    for s in list(keep):
        for m in graph.neighbors(s, depth=2, rels=FLOW_RELS + ("kernel_of", "cites", "joins", "pivots")):
            keep.add(m.id)

    steps = [
        n
        for n in sorted(
            graph.nodes.values(),
            key=lambda x: (STAGE_ORDER.index(x.stage) if x.stage in STAGE_ORDER else 9, x.seq, x.id),
        )
        if n.id in keep and (n.kind in FLOW_KINDS or n.stage in STAGE_ORDER)
    ][:limit]

    walk_rows: list[dict[str, Any]] = []
    for n in steps:
        walk_rows.append(
            {
                "id": n.id,
                "kind": n.kind,
                "stage": n.stage or _stage_for(n.kind),
                "family": n.family,
                "label": n.label,
                "text": n.text[:240],
                "seq": n.seq,
            }
        )

    stages: dict[str, int] = {}
    for s in walk_rows:
        st = s.get("stage") or "context"
        stages[st] = stages.get(st, 0) + 1

    summary = _flow_summary(walk_rows, graph)
    return {
        "summary": summary,
        "count": len(walk_rows),
        "stages": stages,
        "seeds": list(dict.fromkeys(seeds))[:12],
        "steps": walk_rows,
        "insufficient": len(walk_rows) == 0,
    }


def _stage_for(kind: str) -> str:
    return {
        "rag": "sense",
        "memory": "sense",
        "morpheme": "sense",
        "focus": "sense",
        "reflection": "deliberate",
        "frame": "deliberate",
        "kernel": "deliberate",
        "policy": "deliberate",
        "decision": "deliberate",
        "claim": "deliberate",
        "tool": "act",
        "proposal": "act",
        "patch": "act",
        "subagent": "act",
        "round": "act",
        "run": "act",
        "pivot": "act",
        "score": "verify",
        "test": "verify",
    }.get(kind, "context")


def _flow_summary(walk: list[dict[str, Any]], graph: ContextGraph) -> str:
    if not walk:
        return "No agentic flow in this graph — parse an agent run/cognition dir or search a different query."
    tools = [s["label"] for s in walk if s["kind"] == "tool"]
    kernels = [s["label"] for s in walk if s["kind"] == "kernel"]
    stances = [s["label"] for s in walk if s["kind"] == "reflection"]
    pivots = [s["label"] for s in walk if s["kind"] == "pivot"]
    bits = [f"{len(walk)} flow nodes"]
    if kernels:
        bits.append("kernels " + ",".join(dict.fromkeys(kernels)))
    if tools:
        bits.append("tools " + ",".join(list(dict.fromkeys(tools))[:8]))
    if stances:
        bits.append("reflect " + ",".join(dict.fromkeys(stances)))
    if pivots:
        bits.append("pivots " + ",".join(list(dict.fromkeys(pivots))[:8]))
    runs = graph.by_kind("run")
    if runs:
        bits.append(runs[0].label)
    return "; ".join(bits)
