"""Memory, RAG, morphemes, tools, kernels, subagents."""

from __future__ import annotations

from pathlib import Path

from codeevolve.agent.action import execute_plan, plan_from_reflection
from codeevolve.agent.cognition import CognitiveRuntime, describe_cognition
from codeevolve.agent.compaction import compact_memory, compact_texts
from codeevolve.agent.kernel import decompose_objective, list_kernels, make_kernel
from codeevolve.agent.memory import AgentMemory
from codeevolve.agent.morpheme import extract_morphemes, morphemes_from_repo, split_morphemes
from codeevolve.agent.objective import Objective
from codeevolve.agent.rag_context import AgentRag
from codeevolve.agent.subagents import SubAgent, findings_from_tool_output, spawn_subagents
from codeevolve.agent.tools.grep import grep
from codeevolve.agent.tools.registry import build_default_registry
from codeevolve.provenance.schema import MCP_TOOLS, dispatch_mcp_tool


def test_memory_and_compaction(tmp_path: Path) -> None:
    mem = AgentMemory(persist_dir=tmp_path)
    mem.add("working note about api router", kind="working", tags=["api"])
    mem.add("tool:grep ok", kind="tool")
    for i in range(12):
        mem.add(f"episodic {i}", kind="episodic")
    assert mem.search("router")
    compact = compact_memory(mem, keep_working=2)
    assert compact.dropped >= 1
    mem.save()
    mem2 = AgentMemory(persist_dir=tmp_path)
    assert mem2.list(kind="compact")


def test_morphemes_and_rag(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    assert "user" in split_morphemes("getUserProfile") or "profile" in split_morphemes("getUserProfile")
    morphs = extract_morphemes(["src/api/routes.py", "def handle_auth():", "class UserRepo"])
    assert morphs
    data = morphemes_from_repo(sample_repo, paths=["src/app.py", "src/utils.py"])
    assert data["morpheme_count"] >= 1
    rag = AgentRag(sample_repo, backend="memory", max_files=20, max_chunks=40)
    hits = rag.query("main helper app", top_k=4)
    assert isinstance(hits, list)
    block = rag.context_block("app utils", top_k=3)
    assert "RAG" in block or "chunk" in block.lower() or "no RAG" in block


def test_grep_tool(sample_repo: Path) -> None:
    res = grep(sample_repo, r"def main", path="src", max_hits=10)
    assert res.ok
    assert res.output


def test_kernels_and_subagents(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    obj = Objective.parse("reduce_debt", path="src/app.py")
    kernels = decompose_objective(obj, max_kernels=2)
    assert kernels
    assert make_kernel("investigate", obj).name == "investigate"
    assert list_kernels()
    results = spawn_subagents(
        sample_repo,
        obj,
        ["investigate", "pay_down"],
        max_agents=2,
        allow_web=False,
        llm="heuristic",
        work_dir=sample_repo / ".codeevolve" / "agent" / "subagents",
    )
    assert len(results) == 2
    assert results[0].kernel["name"] in {"investigate", "pay_down"}


def test_cognition_cycle(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    rt = CognitiveRuntime(
        sample_repo,
        allow_web=False,
        spawn=True,
        max_subagents=1,
        llm="heuristic",
        rag_backend="memory",
    )
    state = rt.run_cycle(Objective.parse("follow_refactor", path="src/app.py"))
    assert state.reflection.get("stance")
    assert state.memory.get("count", 0) >= 1
    info = describe_cognition()
    assert "grep" in info["tools"]
    assert "graph_search" in info["tools"]
    assert info["registered_sense_tool"] == "graph_search"
    assert state.sense.get("order")
    assert state.sense["order"][0] == "graph_search"
    assert "attention_rank" in state.sense["order"]
    assert rt.live_graph is not None
    mem_text = " ".join(
        str(i.get("content") or "") for i in (state.memory.get("items") or []) if isinstance(i, dict)
    )
    assert "tool:graph_search ok" not in mem_text
    assert "graph" in mem_text.lower() or "insufficient" in mem_text.lower()


def test_action_plan_execute(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    mem = AgentMemory()
    rag = AgentRag(sample_repo, backend="memory", max_files=10)
    tools = build_default_registry(sample_repo, allow_web=False, memory=mem, rag=rag)
    plan = plan_from_reflection(
        {"stance": "continue", "next_focus": "src/app.py", "spawn_kernels": []},
        objective={"kind": "follow_refactor", "path": "src/app.py"},
        enable_web=False,
    )
    names = [a.name for a in plan.actions]
    assert "graph_search" in names
    gs = next(a for a in plan.actions if a.name == "graph_search")
    assert gs.args.get("query")
    assert gs.args.get("traverse") == "rw"
    assert gs.args.get("precedent") is True
    out = execute_plan(plan, tools, max_actions=8)
    assert out.results
    assert compact_texts(["a", "b"]).bullets

    spawn_plan = plan_from_reflection(
        {
            "stance": "spawn",
            "next_focus": "src/app.py",
            "insights": ["need investigate"],
            "spawn_kernels": ["investigate"],
        },
        objective={"kind": "reduce_debt", "path": "src/app.py"},
        enable_web=False,
    )
    gs2 = next(a for a in spawn_plan.actions if a.name == "graph_search")
    assert gs2.args.get("flow") is True
    assert gs2.args.get("traverse") == "pivot"
    assert gs2.args.get("kernel") == "investigate"


def test_graph_search_registered_and_findings(sample_repo: Path) -> None:
    tools = build_default_registry(sample_repo, allow_web=False)
    assert "graph_search" in tools.names()
    spec = next(t for t in tools.list() if t["name"] == "graph_search")
    for key in ("query", "flow", "kernel", "family", "pivot", "traverse", "precedent", "surface", "previous", "delta", "limit"):
        assert key in spec["schema"]
    info = describe_cognition()
    assert info["registered_sense_tool"] == "graph_search"
    assert "graph_search" in info["registered_sense_tools"]
    line = findings_from_tool_output(
        "graph_search",
        {
            "hits": [{"id": "path:a.py", "label": "a.py"}, {"id": "frame:basin", "label": "basin"}],
            "flow": {"summary": "2 flow nodes; kernels investigate"},
            "precedent": [{"id": "decision:r0"}],
        },
    )
    assert line is not None
    assert "path:a.py" in line
    assert "frame:basin" in line
    assert "flow=" in line
    assert "decision:r0" in line
    inv = make_kernel("investigate", Objective.parse("follow_refactor"))
    assert "graph_search" in inv.tools


def test_typed_impasse_kernels_and_compaction(tmp_path: Path) -> None:
    from codeevolve.graph.control import classify_impasse, should_escalate_llm

    insuff = classify_impasse({"proposal": {"stance": "insufficient"}})
    assert insuff["kernel"] == "investigate"
    kernels = decompose_objective(Objective.parse("follow_refactor"), impasse=insuff, max_kernels=2)
    assert kernels[0].name == "investigate"
    verify = classify_impasse({"verify_ok": False, "notes": ["verify/tests failed — rolled back"]})
    assert verify["kernel"] == "stabilize"
    no_gain = classify_impasse({"accepted": True, "score_after": {"improved": False}})
    assert no_gain["kernel"] == "contain"
    fence = classify_impasse({"notes": ["refused apply: huge blast"]})
    assert fence["type"] == "fence_refuse"
    tie = classify_impasse({"proposal": {"paths": ["a.py", "b.py"], "edits": []}})
    assert tie["precedent"] is True
    assert tie["spawn"] is False
    pack = {"node_ids": ["frame:basin"], "insufficient": False}
    assert should_escalate_llm(pack, {"type": ""}, None) is False
    assert should_escalate_llm({"insufficient": True, "node_ids": []}, None, None) is True

    mem = AgentMemory(persist_dir=tmp_path)
    mem.add("keep me", kind="episodic", tags=["overridden", "reflexion"], score=1.8)
    for i in range(12):
        mem.add(f"working {i} filler", kind="working")
    compact_memory(mem, keep_working=2)
    kept = [i for i in mem.list(kind="episodic", limit=20) if "overridden" in i.tags]
    assert kept
    assert "compacted" not in kept[0].tags
    assert kept[0].score >= 1.5


def test_memory_park_ranking(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    mem = AgentMemory(persist_dir=tmp_path)
    old = mem.add("api router debt", kind="episodic", tags=["note"], score=0.4)
    old.created_at = old.created_at - 86400 * 10
    mem.add("api router debt graph", kind="episodic", tags=["graph", "sense"], score=1.2, meta={"graph_ids": ["path:a.py"]})
    ranked = mem.retrieve("api router", limit=4)
    assert ranked
    assert "graph" in ranked[0].tags or ranked[0].meta.get("graph_ids")


def test_mcp_cognition_tools(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    names = {t["name"] for t in MCP_TOOLS}
    assert "spawn_kernel_subagents" in names
    assert "agent_cognition_info" in names
    info = dispatch_mcp_tool("agent_cognition_info", {})
    assert "kernels" in info
    out = dispatch_mcp_tool(
        "spawn_kernel_subagents",
        {"repo": str(sample_repo), "objective": "follow_refactor", "kernels": ["investigate"], "allow_web": False},
    )
    assert out.get("count") == 1


def test_subagent_sense_before_reflect(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    obj = Objective.parse("follow_refactor", path="src/app.py")
    ker = make_kernel("investigate", obj, path="src/app.py")
    sub = SubAgent(sample_repo, ker, allow_web=False, llm="heuristic")
    result = sub.run()
    assert result.sense.get("order")
    assert result.sense["order"][0] == "graph_search"
    names = []
    for row in result.tool_outputs:
        res = row.get("result") or {}
        names.append(str(res.get("name") or (row.get("action") or {}).get("name") or ""))
    assert names
    assert names[0] == "graph_search"
    assert names.count("graph_search") == 1
    insights = " ".join(str(x) for x in (result.reflection.get("insights") or []))
    assert "coalition" in insights.lower() or result.coalition.get("insufficient") is not None


def test_coalition_in_reflect_payload(tmp_path: Path) -> None:
    from codeevolve.agent.reflection import coalition_context, reflect

    mem = AgentMemory(persist_dir=tmp_path)
    pack = {
        "node_ids": ["frame:basin", "decision:0"],
        "frame_ids": ["frame:basin"],
        "decision_ids": ["decision:0"],
        "falsifiers": ["if debt rises, reject"],
        "allowed_because": ["policy:path-fence"],
        "overridden": ["decision:old"],
        "insufficient": False,
        "count": 2,
    }
    ctx = coalition_context(pack)
    assert ctx["frame_ids"] == ["frame:basin"]
    assert ctx["overridden"] == ["decision:old"]
    r = reflect(
        objective={"kind": "reduce_debt", "path": "src/app.py"},
        round_result=None,
        memory=mem,
        coalition=pack,
        llm="heuristic",
    )
    blob = " ".join(r.insights).lower()
    assert "coalition" in blob
    assert "frame:basin" in blob
    assert "falsifier" in blob or "if debt rises" in blob


def test_runtime_failure_reflection_uses_live_graph(sample_repo: Path, monkeypatch) -> None:
    from codeevolve.graph.control import write_failure_reflection

    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    rt = CognitiveRuntime(
        sample_repo,
        allow_web=False,
        spawn=False,
        llm="heuristic",
        rag_backend="memory",
    )
    rt.run_cycle(Objective.parse("follow_refactor", path="src/app.py"))
    assert rt.live_graph is not None
    rid = write_failure_reflection(
        rt.live_graph,
        {
            "index": 0,
            "verify_ok": False,
            "notes": ["verify/tests failed — rolled back"],
            "proposal": {"frame_ids": ["frame:basin"]},
        },
        memory=rt.memory,
        out_dir=rt.work_dir,
    )
    assert rid
    assert rid in rt.live_graph.nodes
    rt.run_cycle(Objective.parse("follow_refactor", path="src/app.py"))
    assert rid in rt.live_graph.nodes
    assert any(e.rel == "overridden" for e in rt.live_graph.edges)


def test_llm_propose_includes_coalition(tmp_path: Path, monkeypatch) -> None:
    from codeevolve.agent.actor import llm_propose
    from codeevolve.agent.workspace import Workspace

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    captured: dict = {}

    class Ep:
        provider = "openai"
        kind = "cloud"
        model = "x"

        def to_dict(self):
            return {"provider": self.provider, "kind": self.kind, "model": self.model}

    class Fake:
        name = "openai"
        endpoint = Ep()

        def complete(self, system, user, max_tokens=0):
            captured["complete"] = user
            return ""

    monkeypatch.setattr("codeevolve.agent.actor.get_chat_backend", lambda *a, **k: Fake())

    def fake_loop(**kwargs):
        captured["payload"] = kwargs.get("user_payload")
        return {"edit_objects": [], "patch_objects": [], "results": [], "summary": ""}

    monkeypatch.setattr("codeevolve.agent.actor.llm_tool_loop", fake_loop)
    ws = Workspace(tmp_path, fence_paths=["a.py"])
    pack = {
        "node_ids": ["frame:basin", "decision:0"],
        "frame_ids": ["frame:basin"],
        "decision_ids": ["decision:0"],
        "falsifiers": ["if debt rises reject"],
        "allowed_because": ["policy:path-fence"],
        "overridden": ["decision:old"],
        "insufficient": False,
        "count": 2,
    }
    llm_propose(
        ws,
        {"id": "R1", "title": "t", "paths": ["a.py"], "actions": []},
        objective={"kind": "reduce_debt"},
        llm="openai",
        coalition=pack,
        structured_tools=True,
    )
    coal = (captured.get("payload") or {}).get("coalition") or {}
    assert "frame:basin" in (coal.get("frame_ids") or [])
    assert "decision:0" in (coal.get("decision_ids") or [])
    assert "decision:old" in (coal.get("overridden") or [])

