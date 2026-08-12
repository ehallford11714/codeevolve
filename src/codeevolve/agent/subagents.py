"""Spawn and run subagents under kernel objectives."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.agent.action import execute_plan, plan_from_reflection
from codeevolve.agent.compaction import compact_texts
from codeevolve.agent.kernel import KernelObjective, make_kernel
from codeevolve.agent.memory import AgentMemory
from codeevolve.agent.morpheme import morphemes_from_repo
from codeevolve.agent.rag_context import AgentRag
from codeevolve.agent.reflection import reflect
from codeevolve.agent.tools.registry import ToolRegistry, build_default_registry


@dataclass
class SubAgentResult:
    id: str
    kernel: dict[str, Any]
    status: str
    reflection: dict[str, Any] = field(default_factory=dict)
    actions: dict[str, Any] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kernel": self.kernel,
            "status": self.status,
            "reflection": self.reflection,
            "actions": self.actions,
            "findings": list(self.findings),
            "tool_outputs": list(self.tool_outputs)[:20],
        }


class SubAgent:
    """Lightweight cognitive subagent: RAG + tools + reflection (no full analyze loop)."""

    def __init__(
        self,
        repo: Path | str,
        kernel: KernelObjective,
        *,
        memory: AgentMemory | None = None,
        rag: AgentRag | None = None,
        tools: ToolRegistry | None = None,
        allow_web: bool = True,
        llm: str | bool | None = "heuristic",
    ) -> None:
        self.repo = Path(repo)
        self.kernel = kernel
        self.memory = memory or AgentMemory()
        self.rag = rag or AgentRag(self.repo, backend="memory")
        self.allow_web = allow_web
        self.llm = llm
        self.tools = tools or build_default_registry(
            self.repo,
            allow_web=allow_web and "web_search" in kernel.tools,
            allow_shell=False,
            memory=self.memory,
            rag=self.rag,
        )
        self.id = uuid.uuid4().hex[:10]

    def run(self) -> SubAgentResult:
        self.memory.add(
            f"subagent:{self.kernel.name} start — {self.kernel.description}",
            kind="episodic",
            tags=["subagent", self.kernel.name],
            meta={"kernel": self.kernel.to_dict()},
        )
        # Seed RAG / morphemes
        query = self.kernel.objective.description or self.kernel.name
        if self.kernel.path:
            query = f"{query} {self.kernel.path}"
        hits = self.rag.query(query, top_k=6, paths=[self.kernel.path] if self.kernel.path else None)
        morph = morphemes_from_repo(
            self.repo,
            paths=[self.kernel.path] if self.kernel.path else None,
            max_files=40,
        )
        self.memory.add(
            f"RAG hits={len(hits)}; {morph.get('summary')}",
            kind="working",
            tags=["rag", "morpheme", self.kernel.name],
        )

        reflection = reflect(
            objective=self.kernel.objective.to_dict(),
            round_result=None,
            memory=self.memory,
            rag_hits=[h.to_dict() for h in hits],
            morphemes=morph.get("morphemes"),
            llm=self.llm if self.llm not in {None, True} else "heuristic",
        )
        plan = plan_from_reflection(
            reflection.to_dict(),
            objective=self.kernel.objective.to_dict(),
            enable_web=self.allow_web and "web_search" in self.kernel.tools,
        )
        # Filter plan tools to kernel allow-list (+ always memory/rag if present)
        allowed = set(self.kernel.tools) | {"memory_add", "memory_search", "rag_query"}
        plan.actions = [
            a
            for a in plan.actions
            if a.kind != "tool" or a.name in allowed or a.name in self.tools.names()
        ]
        # Drop disallowed tools
        plan.actions = [
            a
            for a in plan.actions
            if a.kind != "tool" or a.name in allowed
        ]

        outcome = execute_plan(plan, self.tools, max_actions=max(4, self.kernel.budget_rounds * 4))
        findings: list[str] = []
        tool_outputs: list[dict[str, Any]] = []
        for row in outcome.results:
            tool_outputs.append(row)
            res = row.get("result") or {}
            if not res.get("ok"):
                continue
            out = res.get("output")
            name = res.get("name") or ""
            if name == "grep" and isinstance(out, list):
                findings.append(f"grep:{len(out)} hits")
            elif name == "web_search" and isinstance(out, list):
                findings.append(f"web:{len(out)} results")
            elif name == "rag_query" and isinstance(out, list):
                findings.append(f"rag:{len(out)} chunks")
            elif name == "morpheme_scan" and isinstance(out, dict):
                findings.append(str(out.get("summary") or "morphemes"))
            elif name == "provenance_hint" and isinstance(out, dict):
                findings.append(f"frames:{len(out.get('frames') or [])}")
            elif name == "file_read" and isinstance(out, str):
                findings.append(f"read:{len(out)} chars")

        compact = compact_texts(findings + reflection.insights, max_bullets=10)
        self.memory.add(
            compact.summary,
            kind="episodic",
            tags=["subagent_done", self.kernel.name],
            score=1.4,
        )
        self.memory.save()
        status = "ok" if findings or reflection.insights else "empty"
        return SubAgentResult(
            id=self.id,
            kernel=self.kernel.to_dict(),
            status=status,
            reflection=reflection.to_dict(),
            actions=outcome.to_dict(),
            findings=findings,
            tool_outputs=tool_outputs,
        )


def spawn_subagents(
    repo: Path | str,
    parent_objective: Any,
    kernels: list[str] | list[KernelObjective],
    *,
    memory: AgentMemory | None = None,
    rag: AgentRag | None = None,
    max_agents: int = 4,
    allow_web: bool = True,
    llm: str | bool | None = "heuristic",
    work_dir: Path | str | None = None,
    parallel: bool = False,
) -> list[SubAgentResult]:
    """Spawn up to ``max_agents`` subagents for the given kernels (path-locked)."""
    from codeevolve.agent.coord import run_subagents_coordinated, write_merge_report
    from codeevolve.agent.objective import Objective

    parent = parent_objective if isinstance(parent_objective, Objective) else Objective.parse(str(parent_objective))
    mem = memory or AgentMemory(persist_dir=Path(work_dir) if work_dir else None)
    agent_rag = rag or AgentRag(Path(repo), backend="memory")
    resolved: list[KernelObjective] = []
    for k in kernels[:max_agents]:
        if isinstance(k, KernelObjective):
            resolved.append(k)
        else:
            resolved.append(make_kernel(str(k), parent, path=parent.path))

    out_dir = Path(work_dir) if work_dir else Path(repo) / ".codeevolve" / "agent" / "subagents"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _make(ker: KernelObjective) -> SubAgent:
        return SubAgent(
            repo,
            ker,
            memory=mem,
            rag=agent_rag,
            allow_web=allow_web,
            llm=llm,
        )

    results, merged = run_subagents_coordinated(
        repo,
        resolved,
        make_subagent=_make,
        parallel=parallel,
        max_workers=min(3, max_agents),
    )
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for result, ker in zip(results, resolved):
        (out_dir / f"{stamp}_{ker.name}_{result.id}.json").write_text(
            json.dumps(result.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
    write_merge_report(merged, out_dir / f"{stamp}_merged.json")
    mem.add(
        f"spawned {len(results)} subagents (parallel={parallel}): "
        + ", ".join(str(r.kernel.get("name", "?")) for r in results),
        kind="working",
        tags=["spawn"],
        score=1.2,
        meta={"merged": merged},
    )
    mem.add(
        "merge: " + "; ".join((merged.get("findings") or [])[:6]),
        kind="semantic",
        tags=["merge"],
        score=1.3,
    )
    mem.save()
    return results
