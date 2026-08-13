"""Cognitive stack: memory → RAG → morphemes → reflect → act/tools → compact → spawn."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.agent.action import ActionOutcome, execute_plan, plan_from_reflection
from codeevolve.agent.compaction import compact_memory, compact_round_trace
from codeevolve.agent.kernel import KernelObjective, decompose_objective, list_kernels
from codeevolve.agent.memory import AgentMemory
from codeevolve.agent.morpheme import morphemes_from_repo
from codeevolve.agent.objective import Objective
from codeevolve.agent.rag_context import AgentRag
from codeevolve.agent.reflection import Reflection, reflect
from codeevolve.agent.subagents import SubAgentResult, spawn_subagents
from codeevolve.agent.tools.registry import ToolRegistry, build_default_registry


@dataclass
class CognitionState:
    memory: dict[str, Any]
    rag: dict[str, Any]
    morphemes: dict[str, Any]
    reflection: dict[str, Any]
    actions: dict[str, Any]
    compaction: dict[str, Any]
    subagents: list[dict[str, Any]] = field(default_factory=list)
    kernels: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory": self.memory,
            "rag": self.rag,
            "morphemes": self.morphemes,
            "reflection": self.reflection,
            "actions": self.actions,
            "compaction": self.compaction,
            "subagents": list(self.subagents),
            "kernels": list(self.kernels),
        }


class CognitiveRuntime:
    """Shared cognition services for EvolveAgent + subagents."""

    def __init__(
        self,
        repo: Path | str,
        *,
        work_dir: Path | str | None = None,
        rag_backend: str = "memory",
        allow_web: bool = True,
        allow_shell: bool = False,
        llm: str | bool | None = "auto",
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        spawn: bool = True,
        max_subagents: int = 3,
        parallel: bool = False,
    ) -> None:
        self.repo = Path(repo)
        self.work_dir = Path(work_dir) if work_dir else self.repo / ".codeevolve" / "agent"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.memory = AgentMemory(persist_dir=self.work_dir)
        self.rag = AgentRag(self.repo, backend=rag_backend)
        self.allow_web = allow_web
        self.allow_shell = allow_shell
        self.llm = llm
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.spawn = spawn
        self.max_subagents = max_subagents
        self.parallel = parallel
        self.tools: ToolRegistry = build_default_registry(
            self.repo,
            allow_shell=allow_shell,
            allow_web=allow_web,
            memory=self.memory,
            rag=self.rag,
        )

    def run_cycle(
        self,
        objective: Objective,
        *,
        round_result: dict[str, Any] | None = None,
        paths: list[str] | None = None,
    ) -> CognitionState:
        focus_paths = paths or ([objective.path] if objective.path else None)
        query = objective.description or objective.kind
        if objective.path:
            query = f"{query} {objective.path}"

        hits = self.rag.query(query, top_k=8, paths=focus_paths)
        morph = morphemes_from_repo(self.repo, paths=focus_paths, max_files=60)
        mem_block = self.memory.retrieve_block(
            query,
            path=objective.path,
            limit=8,
        )
        self.memory.add(
            f"cycle seed: rag={len(hits)} morph={morph.get('morpheme_count')} emb_mem",
            kind="working",
            tags=["cognition", objective.kind],
            meta={"embedded_memory": mem_block[:500]},
        )

        reflection = reflect(
            objective=objective.to_dict(),
            round_result=round_result,
            memory=self.memory,
            rag_hits=[h.to_dict() for h in hits],
            morphemes=morph.get("morphemes"),
            llm=self.llm,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            repo=self.repo,
            memory_query=query,
        )

        plan = plan_from_reflection(
            reflection.to_dict(),
            objective=objective.to_dict(),
            enable_web=self.allow_web,
        )
        # compact action is handled below explicitly
        plan.actions = [a for a in plan.actions if a.kind != "compact"]
        spawn_actions = [a for a in plan.actions if a.kind == "spawn"]
        plan.actions = [a for a in plan.actions if a.kind != "spawn"]
        outcome: ActionOutcome = execute_plan(plan, self.tools)

        for row in outcome.results:
            res = row.get("result") or {}
            if res.get("ok"):
                self.memory.add(
                    f"tool:{res.get('name')} ok",
                    kind="tool",
                    tags=[str(res.get("name"))],
                    meta={"output_type": type(res.get("output")).__name__},
                    score=0.9,
                )

        compact = compact_memory(self.memory)
        if round_result:
            rt = compact_round_trace(round_result)
            self.memory.add(rt.summary, kind="compact", tags=["round_trace"], score=1.1)

        kernels = decompose_objective(
            objective,
            reflection_kernels=reflection.spawn_kernels,
            max_kernels=self.max_subagents,
        )
        sub_results: list[SubAgentResult] = []
        should_spawn = self.spawn and (
            reflection.stance == "spawn"
            or bool(spawn_actions)
            or reflection.stance == "pivot"
        )
        if should_spawn and kernels:
            sub_results = spawn_subagents(
                self.repo,
                objective,
                kernels,
                memory=self.memory,
                rag=self.rag,
                max_agents=self.max_subagents,
                allow_web=self.allow_web,
                llm="heuristic" if self.llm in {None, True, "auto"} else self.llm,
                work_dir=self.work_dir / "subagents",
                parallel=self.parallel,
            )

        state = CognitionState(
            memory=self.memory.to_dict(),
            rag=self.rag.to_dict(),
            morphemes=morph,
            reflection=reflection.to_dict(),
            actions=outcome.to_dict(),
            compaction=compact.to_dict(),
            subagents=[s.to_dict() for s in sub_results],
            kernels=[k.to_dict() for k in kernels],
        )
        (self.work_dir / "cognition.json").write_text(
            json.dumps(state.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        self.memory.save()
        return state


def describe_cognition() -> dict[str, Any]:
    return {
        "stack": [
            "memory (working/episodic/semantic + embedded retrieve)",
            "RAG semantic chunks (in-memory vector default)",
            "morpheme / ontology morphology",
            "reflection",
            "action + tooling suite (structured JSON tool-calling)",
            "compaction",
            "kernel objectives → subagents (path locks / merge / parallel)",
            "patch engine (unified hunks, fail-closed, AST/CST symbol fence)",
            "frame-seeded steps (basin/delta)",
            "session delta memory (resume previous report)",
            "context graph families + pivots + traversal search (wavefront/BFS/flow)",
            "blast-radius preview (widen/refuse)",
            "git worktree/branch session",
            "test/CI + coverage-gated pass_tests",
            "PR review pack (frames/falsifiers)",
            "budgets + HITL approve + cost logging",
        ],
        "tools": [
            "file_read",
            "file_list",
            "grep",
            "rag_query",
            "morpheme_scan",
            "memory_search",
            "memory_add",
            "provenance_hint",
            "graph_search",
            "web_search",
            "shell (opt-in)",
        ],
        "kernels": list_kernels(),
    }
