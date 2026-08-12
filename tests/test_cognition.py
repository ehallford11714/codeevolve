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
from codeevolve.agent.subagents import spawn_subagents
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
    out = execute_plan(plan, tools, max_actions=6)
    assert out.results
    assert compact_texts(["a", "b"]).bullets


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
