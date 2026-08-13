"""Graph traversal algorithms that aid search (no NetworkX). Caps keep MCP packs small."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any, Iterable

from codeevolve.graph.families import FAMILY_KINDS, FAMILY_RELS, FLOW_RELS, family_of
from codeevolve.graph.model import ContextGraph

STAGE_ORDER = ("sense", "deliberate", "act", "verify")
_SPLIT = re.compile(r"[^a-z0-9:/_.-]+")


def tokenize(query: str) -> list[str]:
    return [t for t in _SPLIT.split((query or "").lower()) if len(t) >= 2]


def _ok_node(
    graph: ContextGraph,
    nid: str,
    *,
    kinds: set[str] | None,
    family: str | None,
) -> bool:
    n = graph.nodes.get(nid)
    if n is None:
        return False
    if kinds is not None and n.kind not in kinds:
        return False
    if family and (n.family or family_of(n.kind)) != family:
        return False
    return True


def _incident(graph: ContextGraph, nid: str, *, rels: set[str] | None, directed: bool) -> list[tuple[str, str]]:
    """(other_id, rel) pairs. directed=True follows out-edges only."""
    out: list[tuple[str, str]] = []
    for e in graph.out_edges(nid):
        if rels is not None and e.rel not in rels:
            continue
        out.append((e.target, e.rel))
    if not directed:
        for e in graph.in_edges(nid):
            if rels is not None and e.rel not in rels:
                continue
            out.append((e.source, e.rel))
    return out


def bfs_expand(
    graph: ContextGraph,
    seeds: Iterable[str],
    *,
    depth: int = 2,
    rels: Iterable[str] | None = None,
    kinds: Iterable[str] | None = None,
    family: str | None = None,
    max_nodes: int = 80,
    directed: bool = False,
) -> dict[str, Any]:
    """Bounded-depth neighborhood expansion from seeds."""
    allow_rel = set(rels) if rels is not None else None
    allow_kind = set(kinds) if kinds is not None else None
    start = [s for s in dict.fromkeys(seeds) if s in graph.nodes][:32]
    hops: dict[str, int] = {s: 0 for s in start}
    parent: dict[str, str | None] = {s: None for s in start}
    via: dict[str, str] = {}
    q: deque[str] = deque(start)
    while q and len(hops) < max_nodes:
        cur = q.popleft()
        if hops[cur] >= max(0, depth):
            continue
        for other, rel in _incident(graph, cur, rels=allow_rel, directed=directed):
            if other in hops:
                continue
            if not _ok_node(graph, other, kinds=allow_kind, family=family) and other not in start:
                continue
            hops[other] = hops[cur] + 1
            parent[other] = cur
            via[other] = rel
            q.append(other)
            if len(hops) >= max_nodes:
                break
    nodes = [graph.nodes[i].to_dict() | {"hops": hops[i], "via": via.get(i, "")} for i in hops if i in graph.nodes]
    nodes.sort(key=lambda r: (r["hops"], r.get("seq") or 0, r["id"]))
    return {"seeds": start, "count": len(nodes), "nodes": nodes, "hops": hops, "parent": parent}


def dfs_expand(
    graph: ContextGraph,
    seeds: Iterable[str],
    *,
    depth: int = 3,
    rels: Iterable[str] | None = None,
    kinds: Iterable[str] | None = None,
    family: str | None = None,
    max_nodes: int = 80,
    directed: bool = False,
) -> dict[str, Any]:
    allow_rel = set(rels) if rels is not None else None
    allow_kind = set(kinds) if kinds is not None else None
    start = [s for s in dict.fromkeys(seeds) if s in graph.nodes][:16]
    seen: dict[str, int] = {}
    order: list[str] = []

    def walk(nid: str, d: int) -> None:
        if nid in seen or len(seen) >= max_nodes or d > depth:
            return
        if not _ok_node(graph, nid, kinds=allow_kind, family=family) and nid not in start:
            return
        seen[nid] = d
        order.append(nid)
        for other, _rel in _incident(graph, nid, rels=allow_rel, directed=directed):
            walk(other, d + 1)

    for s in start:
        walk(s, 0)
    nodes = [graph.nodes[i].to_dict() | {"hops": seen[i]} for i in order if i in graph.nodes]
    return {"seeds": start, "count": len(nodes), "nodes": nodes}


def shortest_path(
    graph: ContextGraph,
    src: str,
    dst: str,
    *,
    rels: Iterable[str] | None = None,
    max_depth: int = 12,
    directed: bool = False,
) -> list[str] | None:
    """Unweighted geodesic (BFS). Cycle-safe."""
    if src not in graph.nodes or dst not in graph.nodes:
        return None
    if src == dst:
        return [src]
    allow_rel = set(rels) if rels is not None else None
    parent: dict[str, str | None] = {src: None}
    q: deque[str] = deque([src])
    hops = {src: 0}
    while q:
        cur = q.popleft()
        if hops[cur] >= max_depth:
            continue
        for other, _rel in _incident(graph, cur, rels=allow_rel, directed=directed):
            if other in parent:
                continue
            parent[other] = cur
            hops[other] = hops[cur] + 1
            if other == dst:
                path = [dst]
                while path[-1] != src:
                    prev = parent[path[-1]]
                    if prev is None:
                        return None
                    path.append(prev)
                path.reverse()
                return path
            q.append(other)
    return None


def wavefront(
    graph: ContextGraph,
    seeds: Iterable[str],
    *,
    budget: int = 80,
    token_scores: dict[str, float] | None = None,
    rels: Iterable[str] | None = None,
    max_depth: int = 4,
) -> list[dict[str, Any]]:
    """Multi-source BFS: rank by hop distance + token score."""
    scores = token_scores or {}
    start = [s for s in dict.fromkeys(seeds) if s in graph.nodes][:40]
    if not start:
        return []
    allow_rel = set(rels) if rels is not None else None
    hops: dict[str, int] = {s: 0 for s in start}
    seed_of: dict[str, str] = {s: s for s in start}
    q: deque[str] = deque(start)
    while q and len(hops) < budget:
        cur = q.popleft()
        if hops[cur] >= max_depth:
            continue
        for other, _rel in _incident(graph, cur, rels=allow_rel, directed=False):
            if other in hops or other not in graph.nodes:
                continue
            hops[other] = hops[cur] + 1
            seed_of[other] = seed_of[cur]
            q.append(other)
            if len(hops) >= budget:
                break
    ranked: list[tuple[float, int, str]] = []
    for nid, h in hops.items():
        tok = float(scores.get(nid) or 0.0)
        score = tok + (0.4 / (1.0 + h))
        ranked.append((score, h, nid))
    ranked.sort(key=lambda x: (-x[0], x[1], x[2]))
    out: list[dict[str, Any]] = []
    for score, h, nid in ranked:
        n = graph.nodes[nid]
        row = n.to_dict()
        row["score"] = round(score, 4)
        row["hops"] = h
        row["seed"] = seed_of.get(nid, "")
        path = shortest_path(graph, seed_of.get(nid, nid), nid, rels=rels, max_depth=max_depth + 1)
        row["path"] = path or [nid]
        out.append(row)
    return out


def flow_walk(
    graph: ContextGraph,
    seeds: Iterable[str] | None = None,
    *,
    limit: int = 80,
    rels: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Follow FLOW_RELS / next_pivot; order by sense→deliberate→act→verify then seq."""
    allow = set(rels) if rels is not None else set(FLOW_RELS)
    start = [s for s in dict.fromkeys(seeds or []) if s in graph.nodes]
    if not start:
        start = [n.id for n in graph.by_kind("run")][:4]
    if not start:
        start = [n.id for n in graph.by_kind("pivot")][:4]
    seen: set[str] = set()
    q: deque[str] = deque(start)
    while q and len(seen) < limit:
        cur = q.popleft()
        if cur in seen or cur not in graph.nodes:
            continue
        seen.add(cur)
        for other, _rel in _incident(graph, cur, rels=allow, directed=False):
            if other not in seen:
                q.append(other)
    steps = [
        n
        for n in sorted(
            graph.nodes.values(),
            key=lambda x: (STAGE_ORDER.index(x.stage) if x.stage in STAGE_ORDER else 9, x.seq, x.id),
        )
        if n.id in seen
    ][:limit]
    return {
        "seeds": start[:12],
        "count": len(steps),
        "steps": [
            {"id": n.id, "kind": n.kind, "stage": n.stage, "family": n.family, "label": n.label, "seq": n.seq}
            for n in steps
        ],
    }


def family_walk(
    graph: ContextGraph,
    seeds: Iterable[str],
    family: str,
    *,
    depth: int = 3,
    bridge: str | None = None,
    max_nodes: int = 80,
) -> dict[str, Any]:
    """BFS that only crosses one family's edges/nodes; optional pivot-join bridge."""
    rels = FAMILY_RELS.get(family)
    kinds = FAMILY_KINDS.get(family)
    core = bfs_expand(
        graph,
        seeds,
        depth=depth,
        rels=rels,
        kinds=kinds,
        family=family,
        max_nodes=max_nodes,
        directed=False,
    )
    bridged: list[dict[str, Any]] = []
    if bridge:
        pivot_ids = [n["id"] for n in core["nodes"] if graph.nodes[n["id"]].kind == "pivot"]
        if not pivot_ids:
            pivot_ids = [n.id for n in graph.by_kind("pivot")[:12]]
        for pid in pivot_ids[:8]:
            for e in list(graph.out_edges(pid, "joins")) + list(graph.in_edges(pid, "joins")):
                other = e.target if e.source == pid else e.source
                n = graph.nodes.get(other)
                if not n:
                    continue
                fam = n.family or family_of(n.kind)
                if fam != bridge:
                    continue
                bridged.append({"id": n.id, "kind": n.kind, "family": fam, "via_pivot": pid})
                if len(bridged) >= 24:
                    break
    core["bridge"] = bridge
    core["bridged"] = bridged
    return core


def pivot_expand(graph: ContextGraph, pivot_id: str, *, max_nodes: int = 80, depth: int = 2) -> dict[str, Any]:
    """Start at a pivot, fan out to joined family neighborhoods."""
    if pivot_id not in graph.nodes:
        return {"pivot": pivot_id, "insufficient": True, "nodes": []}
    seeds = [pivot_id]
    for e in list(graph.out_edges(pivot_id, "joins")) + list(graph.in_edges(pivot_id, "joins")):
        other = e.target if e.source == pivot_id else e.source
        if other in graph.nodes:
            seeds.append(other)
    exp = bfs_expand(graph, seeds, depth=depth, max_nodes=max_nodes)
    families: dict[str, int] = defaultdict(int)
    for row in exp["nodes"]:
        families[str(row.get("family") or family_of(str(row.get("kind") or "")))] += 1
    return {
        "pivot": pivot_id,
        "insufficient": False,
        "families": dict(families),
        **exp,
    }


def bidirectional(
    graph: ContextGraph,
    seeds: Iterable[str],
    target_kind: str,
    *,
    max_depth: int = 6,
    max_nodes: int = 80,
    rels: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Meet-in-the-middle from query seeds and all nodes of a target kind."""
    left = [s for s in dict.fromkeys(seeds) if s in graph.nodes][:16]
    right = [n.id for n in graph.by_kind(target_kind)][:40]
    if not left or not right:
        return {"insufficient": True, "paths": [], "meets": []}
    allow = set(rels) if rels is not None else None

    def _wave(start: list[str]) -> tuple[dict[str, int], dict[str, str | None]]:
        hops = {s: 0 for s in start}
        parent: dict[str, str | None] = {s: None for s in start}
        q: deque[str] = deque(start)
        while q and len(hops) < max_nodes:
            cur = q.popleft()
            if hops[cur] >= max_depth:
                continue
            for other, _rel in _incident(graph, cur, rels=allow, directed=False):
                if other in hops:
                    continue
                hops[other] = hops[cur] + 1
                parent[other] = cur
                q.append(other)
        return hops, parent

    lh, lp = _wave(left)
    rh, rp = _wave(right)
    meets = [nid for nid in lh if nid in rh]
    meets.sort(key=lambda n: lh[n] + rh[n])
    paths: list[list[str]] = []
    for mid in meets[:8]:
        def _rebuild(end: str, parent: dict[str, str | None], roots: set[str]) -> list[str]:
            path = [end]
            guard = 0
            while path[-1] not in roots and guard < 64:
                prev = parent.get(path[-1])
                if prev is None:
                    break
                path.append(prev)
                guard += 1
            path.reverse()
            return path

        a = _rebuild(mid, lp, set(left))
        b = _rebuild(mid, rp, set(right))
        b.reverse()
        if b and b[0] == mid:
            b = b[1:]
        paths.append(a + b)
    return {"insufficient": not paths, "meets": meets[:12], "paths": paths, "target_kind": target_kind}


def ancestors(
    graph: ContextGraph,
    nid: str,
    *,
    rel: str = "parent_of",
    max_depth: int = 20,
    max_nodes: int = 80,
) -> list[str]:
    """Cycle-safe walk toward parents (incoming parent_of)."""
    if nid not in graph.nodes:
        return []
    seen = {nid}
    out: list[str] = []
    frontier = [nid]
    depth = 0
    while frontier and depth < max_depth and len(out) < max_nodes:
        nxt: list[str] = []
        for cur in frontier:
            for e in graph.in_edges(cur, rel):
                other = e.source
                if other in seen or other not in graph.nodes:
                    continue
                seen.add(other)
                out.append(other)
                nxt.append(other)
        frontier = nxt
        depth += 1
    return out


def descendants(
    graph: ContextGraph,
    nid: str,
    *,
    rel: str = "parent_of",
    max_depth: int = 20,
    max_nodes: int = 80,
) -> list[str]:
    if nid not in graph.nodes:
        return []
    seen = {nid}
    out: list[str] = []
    frontier = [nid]
    depth = 0
    while frontier and depth < max_depth and len(out) < max_nodes:
        nxt: list[str] = []
        for cur in frontier:
            for e in graph.out_edges(cur, rel):
                other = e.target
                if other in seen or other not in graph.nodes:
                    continue
                seen.add(other)
                out.append(other)
                nxt.append(other)
        frontier = nxt
        depth += 1
    return out


def phylogeny_walk(
    graph: ContextGraph,
    nid: str,
    *,
    direction: str = "ancestors",
    max_depth: int = 20,
) -> dict[str, Any]:
    """parent_of / gene_flow walks with visited-set."""
    up = ancestors(graph, nid, rel="parent_of", max_depth=max_depth)
    down = descendants(graph, nid, rel="parent_of", max_depth=max_depth)
    flow = bfs_expand(graph, [nid], depth=2, rels=("gene_flow",), max_nodes=24)
    ids = up if direction != "descendants" else down
    return {
        "id": nid,
        "ancestors": up,
        "descendants": down,
        "gene_flow": [n["id"] for n in flow["nodes"] if n["id"] != nid],
        "walk": ids,
    }


def steiner_join(
    graph: ContextGraph,
    hits: Iterable[str],
    *,
    max_paths: int = 8,
    max_nodes: int = 60,
    rels: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Connect k hits through union of shortest paths to a median seed."""
    ids = [h for h in dict.fromkeys(hits) if h in graph.nodes][:max_paths]
    if len(ids) <= 1:
        return {"seed": ids[0] if ids else "", "nodes": ids, "paths": [], "count": len(ids)}
    seed = ids[0]
    keep: set[str] = set(ids)
    paths: list[list[str]] = []
    for hid in ids[1:]:
        path = shortest_path(graph, seed, hid, rels=rels, max_depth=10)
        if path:
            paths.append(path)
            keep.update(path)
        if len(keep) >= max_nodes:
            break
    nodes = [i for i in keep if i in graph.nodes][:max_nodes]
    return {"seed": seed, "nodes": nodes, "paths": paths[:max_paths], "count": len(nodes)}


def spreading_rank(
    graph: ContextGraph,
    seed_scores: dict[str, float],
    *,
    iterations: int = 4,
    decay: float = 0.5,
    max_nodes: int = 200,
) -> dict[str, float]:
    """Personalized visit scores: spread to neighbors with decay (PageRank-style, no numpy)."""
    scores = {nid: float(v) for nid, v in seed_scores.items() if nid in graph.nodes}
    if not scores:
        return {}
    nodes = list(graph.nodes.keys())[: max(max_nodes, len(scores))]
    for _ in range(max(1, iterations)):
        nxt: dict[str, float] = defaultdict(float)
        for nid in nodes:
            val = scores.get(nid, 0.0)
            if val == 0.0:
                continue
            nxt[nid] += val * (1.0 - decay)
            neighbors = list(graph.out_edges(nid)) + list(graph.in_edges(nid))
            deg = max(1, len(neighbors))
            share = (val * decay) / deg
            for e in neighbors:
                other = e.target if e.source == nid else e.source
                if other in graph.nodes:
                    nxt[other] += share
        scores = dict(nxt)
    return dict(sorted(scores.items(), key=lambda x: -x[1])[:max_nodes])


def resolve_traverse(mode: bool | str | None) -> str:
    if mode is False or mode in {None, "", "off", "false", "0"}:
        return "off"
    if mode is True or str(mode).lower() in {"1", "true", "yes", "wave"}:
        return "wave"
    m = str(mode).lower()
    if m in {"bfs", "wave", "flow", "pivot", "rw", "dfs", "family"}:
        return m
    return "wave"
