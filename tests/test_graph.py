"""Context graph parse + agentic-flow search."""

from __future__ import annotations

from codeevolve.graph import parse_context, query_context, search_graph
from codeevolve.provenance.schema import MCP_TOOLS, dispatch_mcp_tool


def _mini_report() -> dict:
    return {
        "repo": "demo",
        "phylogeny": {
            "roots": ["aaa"],
            "nodes": [
                {"sha": "aaa", "subject": "init", "parent_shas": [], "generation": 0},
                {"sha": "bbb", "subject": "feat api", "parent_shas": ["aaa"], "generation": 1},
            ],
        },
        "taxonomy": {
            "clades": [{"id": "clade:core", "label": "core", "type_path": ["architecture", "api"], "files": ["a.py"]}],
            "allocations": [
                {"sha": "aaa", "path": "a.py", "clade_id": "clade:core", "insertions": 2, "deletions": 0},
                {"sha": "bbb", "path": "a.py", "clade_id": "clade:core", "insertions": 1, "deletions": 0},
            ],
            "keyword_taxonomy": {
                "path_types": {
                    "a.py": {"type_path": ["architecture", "api"], "type_key": "architecture/api"},
                }
            },
        },
        "provenance": {
            "frames": [
                {
                    "id": "frame:basin",
                    "claim": "growth basin",
                    "stance": "support",
                    "evidence": [{"record_id": "trajectory:global", "kind": "trajectory", "role": "measures"}],
                    "context_clades": ["clade:core"],
                }
            ]
        },
        "genetics": {"gene_flow": []},
    }


def _mini_run() -> dict:
    return {
        "objective": {"kind": "reduce_debt"},
        "repo": "demo",
        "status": "ok",
        "summary": "dry-run",
        "rounds": [
            {
                "index": 0,
                "step_id": "R1",
                "accepted": False,
                "applied": False,
                "proposal": {
                    "stance": "support",
                    "summary": "pay down TODO in a.py",
                    "frame_ids": ["frame:basin"],
                    "edit_previews": [{"path": "a.py"}],
                },
                "score_after": {"improved": False, "summary": "dry-run"},
                "cognition": {
                    "reflection": {
                        "stance": "spawn",
                        "insights": ["need investigate"],
                        "next_focus": "a.py",
                        "spawn_kernels": ["investigate"],
                    },
                    "actions": {
                        "plan": {"actions": [{"kind": "tool", "name": "rag_query", "rationale": "ground"}]},
                        "results": [
                            {
                                "result": {
                                    "ok": True,
                                    "name": "rag_query",
                                    "output": [{"path": "a.py", "chunk_id": "c1", "text": "TODO remove"}],
                                }
                            },
                            {"result": {"ok": True, "name": "graph_search", "output": {"hits": []}}},
                        ],
                    },
                    "kernels": [{"name": "investigate", "description": "gather evidence"}],
                    "subagents": [
                        {
                            "id": "sub1",
                            "kernel": {"name": "investigate", "description": "gather evidence"},
                            "status": "ok",
                            "findings": ["TODO in a.py"],
                            "reflection": {"stance": "continue", "next_focus": "a.py"},
                            "tool_outputs": [{"name": "grep", "ok": True, "output": "TODO"}],
                        }
                    ],
                    "morphemes": {"morpheme_count": 3, "summary": "api/handler"},
                },
            }
        ],
    }


def test_parse_report_and_search_type() -> None:
    g = parse_context(report=_mini_report())
    assert g.by_kind("commit")
    assert g.by_kind("type")
    assert any(n.id == "type:architecture/api" for n in g.by_kind("type"))
    hits = search_graph(g, "architecture api", kinds=["type", "path"])
    assert hits
    assert hits[0]["id"].startswith("type:") or "a.py" in hits[0]["id"]


def test_agentic_flow_from_run() -> None:
    payload = query_context(report=_mini_report(), agent=_mini_run(), search="investigate", flow=True)
    assert payload["node_count"] > 5
    flow = payload["flow"]
    assert flow["count"] >= 3
    kinds = {s["kind"] for s in flow["steps"]}
    assert "kernel" in kinds or "subagent" in kinds
    assert "tool" in kinds
    stages = set(flow["stages"])
    assert "sense" in stages or "act" in stages or "deliberate" in stages
    hits = payload["hits"]
    assert any("investigate" in (h.get("label") or "").lower() or "investigate" in h.get("id", "") for h in hits)


def test_mcp_context_graph_and_cli(tmp_path) -> None:
    assert "context_graph" in {t["name"] for t in MCP_TOOLS}
    report = tmp_path / "report.json"
    report.write_text(__import__("json").dumps(_mini_report()), encoding="utf-8")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "run.json").write_text(__import__("json").dumps(_mini_run()), encoding="utf-8")
    out = dispatch_mcp_tool(
        "context_graph",
        {"from_report": str(report), "from_agent": str(agent_dir), "search": "grep", "flow": True},
    )
    assert out.get("node_count")
    assert out.get("flow", {}).get("count")
    from codeevolve.cli import main

    json_out = tmp_path / "g.json"
    assert main(["graph", "--from-report", str(report), "--from-agent", str(agent_dir), "--flow", "--search", "investigate", "--out", str(json_out)]) == 0
    assert json_out.is_file()


def test_families_policies_and_pivots() -> None:
    from codeevolve.graph.families import at_pivot, family_slice, pivot_join

    g = parse_context(report=_mini_report(), agent=_mini_run())
    assert g.by_kind("policy")
    assert any(n.id == "policy:insufficient-if-silent" for n in g.by_kind("policy"))
    assert g.by_kind("authority")
    assert g.by_kind("decision")
    assert g.by_kind("pivot")
    know = family_slice(g, "knowledge")
    assert know.by_kind("policy")
    assert know.by_kind("frame")
    taxon = family_slice(g, "taxon")
    assert taxon.by_kind("commit")
    pivots = at_pivot(g, "propose")
    assert pivots
    joined = pivot_join(g, pivots[0]["pivot"]["id"])
    assert joined.get("count", 0) >= 1
    fams = joined.get("families") or {}
    assert fams


def test_write_back_precedent_and_delta(tmp_path) -> None:
    from codeevolve.graph import delta_detect, parse_context, precedent_search, write_round_traces

    rnd = _mini_run()["rounds"][0]
    written = write_round_traces(rnd, out_dir=tmp_path / "agent", report=_mini_report())
    assert written
    graph_dir = tmp_path / "graph"
    assert (graph_dir / "decisions.jsonl").is_file()
    assert (graph_dir / "pivots.jsonl").is_file()
    g = parse_context(report=_mini_report(), agent=_mini_run(), agent_dir=tmp_path / "agent")
    assert g.by_kind("decision")
    hits = precedent_search(g, "TODO dry-run propose")
    assert hits
    prev = _mini_report()
    cur = dict(prev)
    cur["ecology"] = {"global_stage": "growth", "stage_rationale": "churn"}
    prev["ecology"] = {"global_stage": "pioneer", "stage_rationale": "sparse"}
    cur["debt"] = {"score": 0.4, "summary": "up"}
    prev["debt"] = {"score": 0.1, "summary": "low"}
    events = delta_detect(prev, cur)
    assert any(e["kind"] in {"stage_changed", "debt_crossed"} for e in events)
    payload = query_context(report=cur, previous=prev, delta=True, surface=True)
    assert payload.get("delta")
    assert payload.get("surface") is not None


def test_traversal_algorithms() -> None:
    from codeevolve.graph.model import ContextGraph
    from codeevolve.graph.traverse import (
        ancestors,
        bfs_expand,
        family_walk,
        flow_walk,
        pivot_expand,
        shortest_path,
        spreading_rank,
        wavefront,
    )

    g = parse_context(report=_mini_report(), agent=_mini_run())
    bbb = "commit:bbb"
    aaa = "commit:aaa"
    path = shortest_path(g, bbb, aaa)
    assert path
    assert aaa in path and bbb in path
    neigh = bfs_expand(g, [bbb], depth=2, max_nodes=40)
    assert any(n["id"] == aaa for n in neigh["nodes"])
    hits = search_graph(g, "feat", traverse="wave", limit=30)
    ids = {h["id"] for h in hits}
    assert aaa in ids
    hop_row = next(h for h in hits if h["id"] == aaa)
    assert hop_row.get("hops", 0) >= 1
    off = search_graph(g, "feat", traverse="off", kinds=["commit"], limit=10)
    assert all(h["id"] != aaa or "feat" in (h.get("text") or "").lower() for h in off)
    walk = flow_walk(g, ["run:latest"], limit=40)
    assert walk["count"] >= 1
    fam = family_walk(g, ["path:a.py"], "taxon", depth=2, bridge="knowledge")
    assert fam["count"] >= 1
    piv = next(n.id for n in g.by_kind("pivot"))
    exp = pivot_expand(g, piv, max_nodes=24)
    assert exp["count"] >= 1
    up = ancestors(g, bbb)
    assert aaa in up

    cyc = ContextGraph()
    cyc.add_node("a", "commit", label="a")
    cyc.add_node("b", "commit", label="b")
    cyc.add_edge("a", "b", "parent_of")
    cyc.add_edge("b", "a", "parent_of")
    looped = ancestors(cyc, "a", max_depth=20, max_nodes=20)
    assert len(looped) <= 2
    assert shortest_path(cyc, "a", "b") == ["a", "b"]
    ranks = spreading_rank(g, {bbb: 1.0}, iterations=3)
    assert ranks
    assert bbb in ranks or aaa in ranks

