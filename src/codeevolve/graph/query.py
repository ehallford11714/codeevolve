"""Query helper for CLI / MCP / agent tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codeevolve.graph.delta import delta_detect, proactive_surface
from codeevolve.graph.families import at_pivot, family_slice, pivot_join
from codeevolve.graph.parse import parse_context
from codeevolve.graph.precedent import precedent_search
from codeevolve.graph.search import agentic_flow, search_graph
from codeevolve.graph.traverse import pivot_expand, resolve_traverse, steiner_join


def query_context(
    *,
    report: dict[str, Any] | None = None,
    agent: dict[str, Any] | None = None,
    cognition: dict[str, Any] | None = None,
    agent_dir: Path | str | None = None,
    previous: dict[str, Any] | None = None,
    search: str | None = None,
    flow: bool | str = False,
    kernel: str | None = None,
    kinds: list[str] | None = None,
    family: str | None = None,
    pivot: str | None = None,
    precedent: bool | str = False,
    delta: bool = False,
    surface: bool = False,
    traverse: bool | str = True,
    depth: int = 2,
    limit: int = 20,
) -> dict[str, Any]:
    graph = parse_context(
        report=report,
        agent=agent,
        cognition=cognition,
        agent_dir=agent_dir,
        source=str(agent_dir or "inline"),
    )
    payload: dict[str, Any] = {
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "kinds": graph.kinds(),
        "families": graph.families(),
    }
    flow_query: str | None = None
    if isinstance(flow, str) and flow and flow.lower() not in {"1", "true", "yes"}:
        flow_query = flow
        want_flow = True
    else:
        want_flow = bool(flow)
    mode = resolve_traverse(traverse)
    if search:
        payload["hits"] = search_graph(
            graph,
            search,
            kinds=kinds,
            family=family,
            limit=limit,
            traverse=mode,
            depth=depth,
        )
        if payload["hits"] and mode != "off":
            payload["connected"] = steiner_join(graph, [h["id"] for h in payload["hits"][:8]], max_nodes=40)
    if want_flow or kernel:
        payload["flow"] = agentic_flow(graph, query=flow_query or search, kernel=kernel, limit=max(limit, 40))
    if family and not search:
        sl = family_slice(graph, family, max_nodes=max(limit * 8, 80))
        payload["family"] = {
            "name": family,
            "node_count": len(sl.nodes),
            "kinds": sl.kinds(),
            "graph": sl.to_dict(max_nodes=limit * 4),
        }
    if pivot:
        if pivot in graph.nodes and graph.nodes[pivot].kind == "pivot":
            payload["pivot"] = pivot_join(graph, pivot)
            payload["pivot_expand"] = pivot_expand(graph, pivot, max_nodes=max(limit * 3, 24), depth=depth)
        else:
            rows = at_pivot(graph, pivot, limit=limit)
            payload["at_pivot"] = rows
            payload["insufficient"] = not rows
    if precedent:
        q: Any = search if isinstance(precedent, bool) else precedent
        if not q and payload.get("hits"):
            q = payload["hits"][0]
        payload["precedent"] = precedent_search(graph, q, limit=limit)
    if delta or previous is not None:
        events = delta_detect(previous, report if report is not None else graph, into=graph)
        payload["delta"] = events
        if surface or delta:
            payload["surface"] = proactive_surface(graph, limit=min(limit, 8))
    elif surface:
        payload["surface"] = proactive_surface(graph, limit=min(limit, 8))
    if not search and not want_flow and not kernel and not family and not pivot and not precedent and not delta and not surface:
        payload["graph"] = graph.to_dict()
    return payload
