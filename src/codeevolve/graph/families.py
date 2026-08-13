"""Graph families, typed primitives, and pivot-join helpers."""

from __future__ import annotations

from typing import Any, Iterable

from codeevolve.graph.model import ContextGraph, GraphNode

FLOW_RELS = (
    "next",
    "spawned",
    "invoked",
    "proposed",
    "scored",
    "retrieved",
    "reflects",
    "focuses",
    "next_pivot",
    "pivots",
)

FLOW_KINDS = (
    "run",
    "round",
    "reflection",
    "kernel",
    "subagent",
    "tool",
    "rag",
    "morpheme",
    "memory",
    "proposal",
    "patch",
    "score",
    "test",
    "frame",
    "pivot",
    "decision",
    "policy",
)

PIVOT_TYPES = (
    "sense",
    "deliberate",
    "act",
    "verify",
    "choose_path",
    "propose",
    "apply_or_dry_run",
    "score",
    "spawn",
    "rollback",
)

FAMILY_KINDS: dict[str, frozenset[str]] = {
    "taxon": frozenset({"commit", "type", "clade", "niche", "path"}),
    "context": frozenset({"context", "window", "focus", "fence", "blast", "delta"}),
    "knowledge": frozenset({"frame", "record", "policy", "authority", "claim"}),
    "decision": frozenset({"decision", "proposal", "score", "reflection"}),
    "pivot": frozenset({"pivot"}),
    "flow": frozenset(
        {"run", "round", "kernel", "subagent", "tool", "rag", "morpheme", "memory", "patch", "test"}
    ),
}

FAMILY_RELS: dict[str, frozenset[str]] = {
    "taxon": frozenset(
        {"parent_of", "typed_as", "in_clade", "in_niche", "contains", "touches", "gene_flow"}
    ),
    "context": frozenset({"focuses", "in_window", "fenced_by", "blast_of"}),
    "knowledge": frozenset({"cites", "allowed_by", "constrained_by", "falsified_by"}),
    "decision": frozenset({"allowed_because", "overridden", "refused", "precedes", "scored", "proposed"}),
    "pivot": frozenset({"pivots", "joins", "next_pivot"}),
    "flow": frozenset(FLOW_RELS),
}

KIND_FAMILY: dict[str, str] = {}
for _fam, _kinds in FAMILY_KINDS.items():
    for _k in _kinds:
        KIND_FAMILY.setdefault(_k, _fam)

# Overlaps: reflection/proposal/score live in decision; path is taxon.
KIND_FAMILY["reflection"] = "decision"
KIND_FAMILY["proposal"] = "decision"
KIND_FAMILY["score"] = "decision"
KIND_FAMILY["path"] = "taxon"
KIND_FAMILY["frame"] = "knowledge"


def family_of(kind: str) -> str:
    return KIND_FAMILY.get(kind, "")


def family_slice(graph: ContextGraph, family: str, *, max_nodes: int = 200) -> ContextGraph:
    """Subgraph of one family (kinds + family-tagged nodes)."""
    kinds = FAMILY_KINDS.get(family, frozenset())
    rels = FAMILY_RELS.get(family, frozenset())
    ids = [
        n.id
        for n in sorted(graph.nodes.values(), key=lambda x: (x.seq, x.id))
        if n.family == family or n.kind in kinds
    ][:max_nodes]
    keep = set(ids)
    g = graph.subgraph(keep, source=f"{graph.source}:{family}")
    extra = [
        e
        for e in graph.edges
        if e.rel in rels and e.source in graph.nodes and e.target in graph.nodes
        and (e.source in keep or e.target in keep)
    ]
    for e in extra[: max_nodes * 2]:
        if e.source not in g.nodes and e.source in graph.nodes:
            n = graph.nodes[e.source]
            g.add_node(
                n.id,
                n.kind,
                label=n.label,
                stage=n.stage,
                family=n.family,
                text=n.text,
                seq=n.seq,
                source=n.source,
                confidence=n.confidence,
                authority=n.authority,
                valid_from=n.valid_from,
                valid_to=n.valid_to,
                meta=dict(n.meta),
            )
        if e.target not in g.nodes and e.target in graph.nodes:
            n = graph.nodes[e.target]
            g.add_node(
                n.id,
                n.kind,
                label=n.label,
                stage=n.stage,
                family=n.family,
                text=n.text,
                seq=n.seq,
                source=n.source,
                confidence=n.confidence,
                authority=n.authority,
                valid_from=n.valid_from,
                valid_to=n.valid_to,
                meta=dict(n.meta),
            )
        g.add_edge(e.source, e.target, e.rel, weight=e.weight, meta=dict(e.meta))
    return g


def pivot_join(graph: ContextGraph, pivot_id: str, *, max_nodes: int = 80) -> dict[str, Any]:
    """All family neighborhoods attached to a pivot via joins/pivots."""
    if pivot_id not in graph.nodes:
        return {"pivot": pivot_id, "insufficient": True, "families": {}, "nodes": []}
    pivot = graph.nodes[pivot_id]
    joined: list[GraphNode] = []
    seen = {pivot_id}
    for e in list(graph.out_edges(pivot_id, "joins")) + list(graph.in_edges(pivot_id, "joins")):
        other = e.target if e.source == pivot_id else e.source
        if other in seen or other not in graph.nodes:
            continue
        seen.add(other)
        joined.append(graph.nodes[other])
    for e in list(graph.in_edges(pivot_id, "pivots")) + list(graph.out_edges(pivot_id, "pivots")):
        other = e.target if e.source == pivot_id else e.source
        if other in seen or other not in graph.nodes:
            continue
        seen.add(other)
        joined.append(graph.nodes[other])
    joined = joined[:max_nodes]
    families: dict[str, list[dict[str, Any]]] = {}
    for n in joined:
        fam = n.family or family_of(n.kind) or "unknown"
        families.setdefault(fam, []).append({"id": n.id, "kind": n.kind, "label": n.label, "stage": n.stage})
    return {
        "pivot": pivot.to_dict(),
        "insufficient": False,
        "count": len(joined),
        "families": {k: v[:16] for k, v in families.items()},
        "nodes": [n.to_dict() for n in joined],
    }


def at_pivot(graph: ContextGraph, kind: str, *, limit: int = 40) -> list[dict[str, Any]]:
    """Nodes used at a pivot type (choose_path, propose, sense, …)."""
    want = str(kind or "")
    out: list[dict[str, Any]] = []
    for n in sorted(graph.by_kind("pivot"), key=lambda x: (x.seq, x.id)):
        ptype = str(n.meta.get("pivot_type") or n.label)
        if want and want not in ptype and ptype != want:
            continue
        row = pivot_join(graph, n.id, max_nodes=24)
        row["pivot_type"] = ptype
        out.append(row)
        if len(out) >= limit:
            break
    return out


def join_families(graph: ContextGraph, pivot_id: str, node_ids: Iterable[str], *, rel: str = "joins") -> int:
    """Attach family nodes to a pivot. Returns edges added."""
    added = 0
    for nid in node_ids:
        if nid == pivot_id or nid not in graph.nodes:
            continue
        if graph.add_edge(pivot_id, nid, rel):
            added += 1
    return added
