"""Context graph: typed nodes + directed edges for phylogeny, provenance, and agent flow."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable


def node_id(*parts: object) -> str:
    body = ":".join(str(p) for p in parts if p is not None and p != "")
    return body[:180]


@dataclass
class GraphNode:
    id: str
    kind: str
    label: str = ""
    stage: str = ""  # sense | deliberate | act | verify | taxon | context
    family: str = ""
    text: str = ""
    seq: int = 0
    source: str = ""
    confidence: float | None = None
    authority: str = ""
    valid_from: str = ""
    valid_to: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def blob(self) -> str:
        bits = [self.id, self.kind, self.family, self.label, self.stage, self.text, self.source, self.authority]
        if self.confidence is not None:
            bits.append(f"conf:{self.confidence}")
        for k, v in self.meta.items():
            if isinstance(v, (str, int, float)):
                bits.append(f"{k}:{v}")
            elif isinstance(v, list):
                bits.extend(str(x) for x in v[:8])
        return " ".join(str(b) for b in bits if b).lower()

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "family": self.family,
            "label": self.label,
            "stage": self.stage,
            "text": self.text[:400],
            "seq": self.seq,
            "meta": dict(self.meta),
        }
        if self.source:
            row["source"] = self.source
        if self.confidence is not None:
            row["confidence"] = self.confidence
        if self.authority:
            row["authority"] = self.authority
        if self.valid_from:
            row["valid_from"] = self.valid_from
        if self.valid_to:
            row["valid_to"] = self.valid_to
        return row


@dataclass
class GraphEdge:
    source: str
    target: str
    rel: str
    weight: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "rel": self.rel,
            "weight": self.weight,
            "meta": dict(self.meta),
        }


class ContextGraph:
    """Directed multigraph with kind indexes. Caps keep packs small."""

    def __init__(self, *, source: str = "") -> None:
        self.source = source
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._edge_keys: set[tuple[str, str, str]] = set()
        self._out: dict[str, list[GraphEdge]] = defaultdict(list)
        self._in: dict[str, list[GraphEdge]] = defaultdict(list)
        self._seq = 0

    def add_node(
        self,
        nid: str,
        kind: str,
        *,
        label: str = "",
        stage: str = "",
        family: str = "",
        text: str = "",
        seq: int | None = None,
        source: str = "",
        confidence: float | None = None,
        authority: str = "",
        valid_from: str = "",
        valid_to: str = "",
        meta: dict[str, Any] | None = None,
    ) -> GraphNode:
        from codeevolve.graph.families import family_of

        fam = family or family_of(kind)
        if nid in self.nodes:
            n = self.nodes[nid]
            if label and not n.label:
                n.label = label
            if text and len(text) > len(n.text):
                n.text = text
            if stage and not n.stage:
                n.stage = stage
            if fam and not n.family:
                n.family = fam
            if source and not n.source:
                n.source = source
            if confidence is not None and n.confidence is None:
                n.confidence = confidence
            if authority and not n.authority:
                n.authority = authority
            if valid_from and not n.valid_from:
                n.valid_from = valid_from
            if valid_to and not n.valid_to:
                n.valid_to = valid_to
            if meta:
                n.meta.update(meta)
            return n
        if seq is None:
            self._seq += 1
            seq = self._seq
        node = GraphNode(
            id=nid,
            kind=kind,
            label=label or nid,
            stage=stage,
            family=fam,
            text=text[:800],
            seq=seq,
            source=source,
            confidence=confidence,
            authority=authority,
            valid_from=valid_from,
            valid_to=valid_to,
            meta=dict(meta or {}),
        )
        self.nodes[nid] = node
        return node

    def add_edge(
        self,
        source: str,
        target: str,
        rel: str,
        *,
        weight: float = 1.0,
        meta: dict[str, Any] | None = None,
    ) -> GraphEdge | None:
        if source not in self.nodes or target not in self.nodes:
            return None
        key = (source, target, rel)
        if key in self._edge_keys:
            return None
        self._edge_keys.add(key)
        edge = GraphEdge(source=source, target=target, rel=rel, weight=weight, meta=dict(meta or {}))
        self.edges.append(edge)
        self._out[source].append(edge)
        self._in[target].append(edge)
        return edge

    def out_edges(self, nid: str, rel: str | None = None) -> list[GraphEdge]:
        rows = self._out.get(nid) or []
        if rel:
            return [e for e in rows if e.rel == rel]
        return list(rows)

    def in_edges(self, nid: str, rel: str | None = None) -> list[GraphEdge]:
        rows = self._in.get(nid) or []
        if rel:
            return [e for e in rows if e.rel == rel]
        return list(rows)

    def by_kind(self, kind: str) -> list[GraphNode]:
        return [n for n in self.nodes.values() if n.kind == kind]

    def by_family(self, family: str) -> list[GraphNode]:
        return [n for n in self.nodes.values() if n.family == family]

    def kinds(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            counts[n.kind] += 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    def families(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            counts[n.family or "unknown"] += 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    def neighbors(self, nid: str, *, depth: int = 1, rels: Iterable[str] | None = None) -> list[GraphNode]:
        allow = set(rels) if rels else None
        seen = {nid}
        frontier = [nid]
        found: list[GraphNode] = []
        for _ in range(max(1, depth)):
            nxt: list[str] = []
            for cur in frontier:
                for e in list(self._out.get(cur) or []) + list(self._in.get(cur) or []):
                    if allow is not None and e.rel not in allow:
                        continue
                    other = e.target if e.source == cur else e.source
                    if other in seen or other not in self.nodes:
                        continue
                    seen.add(other)
                    found.append(self.nodes[other])
                    nxt.append(other)
            frontier = nxt
            if not frontier:
                break
        return found

    def subgraph(self, ids: Iterable[str], *, source: str = "") -> ContextGraph:
        keep = {i for i in ids if i in self.nodes}
        g = ContextGraph(source=source or self.source)
        for nid in keep:
            n = self.nodes[nid]
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
        for e in self.edges:
            if e.source in keep and e.target in keep:
                g.add_edge(e.source, e.target, e.rel, weight=e.weight, meta=dict(e.meta))
        return g

    def to_dict(self, *, max_nodes: int = 400, max_edges: int = 800) -> dict[str, Any]:
        nodes = sorted(self.nodes.values(), key=lambda n: (n.seq, n.id))[:max_nodes]
        keep = {n.id for n in nodes}
        edges = [e for e in self.edges if e.source in keep and e.target in keep][:max_edges]
        return {
            "source": self.source,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "kinds": self.kinds(),
            "families": self.families(),
            "truncated": len(self.nodes) > len(nodes) or len(self.edges) > len(edges),
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
        }
