"""Context graph parse + agentic-flow search."""

from __future__ import annotations

from pathlib import Path

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
                            {"result": {"ok": True, "name": "graph_search", "output": {
                                "hits": [
                                    {"id": "path:a.py", "kind": "path", "label": "a.py", "stage": "context", "text": "a.py"},
                                    {"id": "frame:basin", "kind": "frame", "label": "frame:basin", "stage": "deliberate"},
                                ],
                                "flow": {"summary": "investigate kernel walk", "count": 2, "steps": []},
                                "precedent": [{"id": "decision:sense-r0", "kind": "decision", "label": "prior"}],
                            }}},
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
    dfs_hits = search_graph(g, "feat", traverse="dfs", limit=30)
    assert dfs_hits
    assert any(h["id"] in {aaa, bbb} or "feat" in (h.get("text") or "").lower() for h in dfs_hits)
    fam_hits = search_graph(g, "api", traverse="family", family="taxon", limit=30)
    assert fam_hits


def test_graph_search_ingest_and_loop_sense() -> None:
    from codeevolve.agent.loop import sense_graph_crossings
    from codeevolve.graph.model import ContextGraph

    g = parse_context(report=_mini_report(), agent=_mini_run())
    retrieved = [(e.source, e.target, e.rel) for e in g.edges if e.rel in {"retrieved", "cites"}]
    assert any(t == "path:a.py" and r == "retrieved" for _s, t, r in retrieved)
    assert any(t == "decision:sense-r0" and r == "cites" for _s, t, r in retrieved)
    assert any(n.label == "flow" or "investigate kernel" in (n.text or "") for n in g.nodes.values())

    empty = ContextGraph()
    cog = {
        "actions": {
            "results": [
                {
                    "result": {
                        "ok": True,
                        "name": "graph_search",
                        "output": {
                            "hits": [{"id": "type:architecture/api", "kind": "type", "label": "architecture/api", "stage": "taxon"}],
                            "flow": {"summary": "sense walk", "steps": [{"id": "kernel:investigate", "kind": "kernel", "label": "investigate", "stage": "deliberate"}]},
                            "precedent": [{"id": "decision:prior", "kind": "decision", "label": "prior"}],
                        },
                    }
                }
            ]
        }
    }
    from codeevolve.graph.parse import ingest_cognition

    ingest_cognition(empty, cog, parent=None)
    assert "type:architecture/api" in empty.nodes
    assert "kernel:investigate" in empty.nodes
    assert "decision:prior" in empty.nodes
    tool_ids = [n.id for n in empty.by_kind("tool")]
    assert tool_ids
    assert any(e.source in tool_ids and e.target == "type:architecture/api" and e.rel == "retrieved" for e in empty.edges)
    assert any(e.target == "decision:prior" and e.rel == "cites" for e in empty.edges)

    prev = _mini_report()
    cur = dict(prev)
    prev["ecology"] = {"global_stage": "pioneer", "stage_rationale": "sparse"}
    cur["ecology"] = {"global_stage": "growth", "stage_rationale": "churn"}
    prev["debt"] = {"score": 0.1, "summary": "low"}
    cur["debt"] = {"score": 0.4, "summary": "up"}
    notes = sense_graph_crossings(cur, prev)
    assert notes
    assert any("stage_changed" in n or "debt_crossed" in n for n in notes)
    assert sense_graph_crossings(cur, None) == []


def test_coalition_windows_chunks_and_propose() -> None:
    from codeevolve.agent.actor import heuristic_propose
    from codeevolve.agent.workspace import Workspace
    from codeevolve.graph.control import (
        chunk_from_traces,
        close_validity_windows,
        coalition_pack,
        window_open,
    )
    from codeevolve.graph.precedent import precedent_search

    g = parse_context(report=_mini_report(), agent=_mini_run())
    pack = coalition_pack(g, hits=[{"id": "path:a.py"}, {"id": "frame:basin"}], path="a.py", limit=12)
    assert pack["count"] >= 1
    assert pack.get("insufficient") is False
    assert "frame:basin" in pack["frame_ids"] or "frame:basin" in pack["node_ids"]

    g.add_node("decision:old", "decision", label="decision:applied", stage="deliberate", family="decision", text="a.py")
    g.add_node("path:a.py", "path", label="a.py", stage="context")
    g.add_edge("decision:old", "path:a.py", "focuses")
    closed = close_validity_windows(g, paths=["a.py"], frame_ids=["frame:basin"], except_id="decision:r0")
    assert "decision:old" in closed or any(n.valid_to for n in g.by_kind("decision") if n.id == "decision:old")
    g.nodes["decision:old"].valid_to = "2020-01-01T00:00:00+00:00"
    assert window_open(g.nodes["decision:old"]) is False
    hits = precedent_search(g, "a.py basin")
    assert all(h.get("id") != "decision:old" for h in hits)

    prefs = chunk_from_traces(
        [
            {"paths": ["a.py"], "frame_ids": ["frame:basin"], "outcome": "overridden", "source": "agent.round"},
            {"paths": ["a.py"], "frame_ids": ["frame:basin"], "outcome": "overridden", "source": "agent.round"},
        ]
    )
    assert prefs
    assert prefs[0]["preference"] == "refuse_blast"

    from pathlib import Path as P

    ws = Workspace(P("."), fence_paths=["a.py"])
    prop = heuristic_propose(
        ws,
        {"id": "R1", "title": "t", "paths": ["a.py"], "actions": []},
        coalition=pack,
    )
    assert "frame:basin" in prop.frame_ids or prop.coalition.get("frame_ids")
    assert prop.coalition.get("count", 0) >= 1 or prop.coalition.get("node_ids")


def test_attention_rank_seeds_coalition() -> None:
    from codeevolve.graph.control import attention_rank, coalition_pack

    g = parse_context(report=_mini_report(), agent=_mini_run())
    g.add_node("path:a.py", "path", label="a.py", stage="context")
    g.add_node("decision:last", "decision", label="decision:applied", stage="deliberate", family="decision")
    g.add_edge("decision:last", "path:a.py", "focuses")
    g.add_edge("path:a.py", "frame:basin", "cites")
    ranked = attention_rank(g, path="a.py", frame_ids=["frame:basin"], last_decision="decision:last", hops=3)
    assert ranked
    assert all("attention" in row for row in ranked)
    fams = [row.get("family") or row.get("kind") for row in ranked]
    assert len(fams) >= 1
    pack = coalition_pack(g, hits=[{"id": "path:a.py"}], path="a.py", last_decision="decision:last", frame_ids=["frame:basin"])
    assert pack.get("attention")
    attention_ids = {str(r.get("id")) for r in pack["attention"] if r.get("id")}
    assert attention_ids & set(pack["node_ids"]) or pack["count"] >= 1


def test_failure_reflection_attaches_live_graph(tmp_path: Path) -> None:
    from codeevolve.graph.control import merge_live_reflections, write_failure_reflection
    from codeevolve.graph.model import ContextGraph

    g = ContextGraph(source="test")
    g.add_node("frame:basin", "frame", label="basin", stage="deliberate", family="knowledge")
    rid = write_failure_reflection(
        g,
        {
            "index": 3,
            "verify_ok": False,
            "notes": ["verify/tests failed — rolled back"],
            "proposal": {"frame_ids": ["frame:basin"]},
        },
        out_dir=tmp_path,
    )
    assert rid
    assert rid in g.nodes
    assert g.nodes[rid].kind == "reflection"
    assert any(e.rel == "overridden" for e in g.edges)
    assert any(e.rel == "falsified_by" for e in g.edges)
    host = ContextGraph(source="next-sense")
    n = merge_live_reflections(host, g)
    assert n >= 1
    assert rid in host.nodes
    assert any(e.rel == "overridden" for e in host.edges)
    jsonl = list((tmp_path / "graph").glob("*.jsonl")) or list(tmp_path.glob("*.jsonl"))
    assert jsonl or (tmp_path / "graph" / "pivots.jsonl").is_file()

