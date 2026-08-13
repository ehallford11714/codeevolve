"""Spawn and run subagents under kernel objectives."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.agent.action import ActionPlan, execute_plan, graph_search_action, plan_from_reflection
from codeevolve.agent.compaction import compact_texts
from codeevolve.agent.kernel import KernelObjective, make_kernel
from codeevolve.agent.memory import AgentMemory
from codeevolve.agent.morpheme import morphemes_from_repo
from codeevolve.agent.rag_context import AgentRag
from codeevolve.agent.reflection import reflect
from codeevolve.agent.tools.registry import ToolRegistry, build_default_registry


def findings_from_tool_output(name: str, out: Any) -> str | None:
    """Turn a successful tool output into a short finding line. Fail closed."""
    if name == "grep" and isinstance(out, list):
        return f"grep:{len(out)} hits"
    if name == "web_search" and isinstance(out, list):
        return f"web:{len(out)} results"
    if name == "rag_query" and isinstance(out, list):
        return f"rag:{len(out)} chunks"
    if name == "morpheme_scan" and isinstance(out, dict):
        return str(out.get("summary") or "morphemes")
    if name == "provenance_hint" and isinstance(out, dict):
        return f"frames:{len(out.get('frames') or [])}"
    if name == "file_read" and isinstance(out, str):
        return f"read:{len(out)} chars"
    if name == "graph_search" and isinstance(out, dict):
        hits = [h for h in (out.get("hits") or []) if isinstance(h, dict)]
        labels = [str(h.get("id") or h.get("label") or "") for h in hits[:6]]
        labels = [x for x in labels if x]
        flow = out.get("flow") if isinstance(out.get("flow"), dict) else {}
        flow_sum = str(flow.get("summary") or "")
        prec = [p for p in (out.get("precedent") or []) if isinstance(p, dict)]
        prec_ids = [str(p.get("id") or "") for p in prec[:4] if p.get("id")]
        bits = [f"graph:{len(hits)} hits"]
        if labels:
            bits.append("[" + ",".join(labels) + "]")
        if flow_sum:
            bits.append(f"flow={flow_sum[:80]}")
        if prec_ids:
            bits.append("precedent=" + ",".join(prec_ids))
        return " ".join(bits)
    return None


@dataclass
class SubAgentResult:
    id: str
    kernel: dict[str, Any]
    status: str
    reflection: dict[str, Any] = field(default_factory=dict)
    actions: dict[str, Any] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    sense: dict[str, Any] = field(default_factory=dict)
    coalition: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kernel": self.kernel,
            "status": self.status,
            "reflection": self.reflection,
            "actions": self.actions,
            "findings": list(self.findings),
            "tool_outputs": list(self.tool_outputs)[:20],
            "sense": dict(self.sense),
            "coalition": dict(self.coalition),
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
        previous_report: Path | str | None = None,
    ) -> None:
        self.repo = Path(repo)
        self.kernel = kernel
        self.memory = memory or AgentMemory()
        self.rag = rag or AgentRag(self.repo, backend="memory")
        self.allow_web = allow_web
        self.llm = llm
        self.previous_report = previous_report
        self.tools = tools or build_default_registry(
            self.repo,
            allow_web=allow_web and "web_search" in kernel.tools,
            allow_shell=False,
            memory=self.memory,
            rag=self.rag,
        )
        self.id = uuid.uuid4().hex[:10]

    def run(self) -> SubAgentResult:
        from codeevolve.graph.control import (
            attention_rank,
            coalition_pack,
            sense_graph_crossings,
            sense_note_from_output,
        )
        from codeevolve.graph.parse import parse_context

        self.memory.add(
            f"subagent:{self.kernel.name} start — {self.kernel.description}",
            kind="episodic",
            tags=["subagent", self.kernel.name],
            meta={"kernel": self.kernel.to_dict()},
        )
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

        crossings: list[str] = []
        current_report: dict[str, Any] | None = None
        report_path = self.repo / ".codeevolve" / "report.json"
        if report_path.is_file():
            try:
                loaded = json.loads(report_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    current_report = loaded
            except (OSError, json.JSONDecodeError):
                current_report = None
        prev = self.previous_report
        if prev:
            crossings = sense_graph_crossings(current_report, prev, memory=self.memory)

        obj_dict = self.kernel.objective.to_dict()
        sense_refl = {
            "stance": "continue",
            "next_focus": self.kernel.path or self.kernel.name,
            "insights": crossings[:3],
            "spawn_kernels": [self.kernel.name],
        }
        sense_plan = ActionPlan(actions=[graph_search_action(sense_refl, obj_dict, previous=prev)])
        sense_out = execute_plan(sense_plan, self.tools, max_actions=1)
        sense_res = (sense_out.results[0].get("result") or {}) if sense_out.results else {}
        sense_payload = sense_res.get("output") if isinstance(sense_res.get("output"), dict) else {}
        graph_finding = findings_from_tool_output("graph_search", sense_payload) if sense_res.get("ok") else None
        if not graph_finding:
            graph_finding = sense_note_from_output(sense_payload if sense_payload else None)
        hit_ids = [str(h.get("id") or "") for h in (sense_payload.get("hits") or []) if isinstance(h, dict)]
        self.memory.add(
            graph_finding,
            kind="working",
            tags=["graph", "sense", "graph_search", self.kernel.name],
            score=1.4,
            meta={"graph_ids": [x for x in hit_ids if x], "ok": bool(sense_res.get("ok"))},
        )

        coalition: dict[str, Any] = {
            "node_ids": [],
            "insufficient": True,
            "stance": "insufficient",
            "count": 0,
        }
        cited = [str(h.get("id") or "") for h in (sense_payload.get("hits") or []) if isinstance(h, dict) and str(h.get("id") or "").startswith("frame:")]
        attention_rows: list[dict[str, Any]] = []
        try:
            agent_dir = self.repo / ".codeevolve" / "agent"
            g = parse_context(
                agent_dir=agent_dir if agent_dir.is_dir() else None,
                report=current_report,
            )
            attention_rows = attention_rank(
                g,
                path=self.kernel.path,
                frame_ids=cited,
                hops=3,
                per_family=4,
                limit=12,
            )
            sense_hits = list(sense_payload.get("hits") or [])
            sense_hits.extend({"id": r.get("id"), "kind": r.get("kind")} for r in attention_rows)
            coalition = coalition_pack(
                g,
                hits=sense_hits,
                path=self.kernel.path,
                frame_ids=cited,
            )
        except Exception:  # noqa: BLE001
            pass

        reflection = reflect(
            objective=obj_dict,
            round_result=None,
            memory=self.memory,
            rag_hits=[h.to_dict() for h in hits],
            morphemes=morph.get("morphemes"),
            llm=self.llm if self.llm not in {None, True} else "heuristic",
            coalition=coalition,
        )
        plan = plan_from_reflection(
            reflection.to_dict(),
            objective=obj_dict,
            enable_web=self.allow_web and "web_search" in self.kernel.tools,
            previous=prev,
        )
        allowed = set(self.kernel.tools) | {"memory_add", "memory_search", "rag_query", "graph_search"}
        plan.actions = [
            a
            for a in plan.actions
            if a.kind != "tool" or a.name in allowed
        ]
        plan.actions = [
            a
            for a in plan.actions
            if not (a.kind == "tool" and a.name == "graph_search")
        ]

        outcome = execute_plan(plan, self.tools, max_actions=max(8, self.kernel.budget_rounds * 4))
        outcome.results = list(sense_out.results) + list(outcome.results)
        findings: list[str] = []
        tool_outputs: list[dict[str, Any]] = []
        for row in outcome.results:
            tool_outputs.append(row)
            res = row.get("result") or {}
            if not res.get("ok"):
                continue
            name = str(res.get("name") or "")
            found = findings_from_tool_output(name, res.get("output"))
            if found:
                findings.append(found)

        compact = compact_texts(findings + reflection.insights, max_bullets=10)
        self.memory.add(
            compact.summary,
            kind="episodic",
            tags=["subagent_done", self.kernel.name],
            score=1.4,
        )
        self.memory.save()
        status = "ok" if findings or reflection.insights else "empty"
        sense = {
            "tool": "graph_search",
            "finding": graph_finding,
            "ok": bool(sense_res.get("ok")),
            "hit_ids": [x for x in hit_ids if x],
            "crossings": crossings[:8],
            "attention_ids": [str(r.get("id") or "") for r in attention_rows if r.get("id")],
            "order": ["graph_search", "crossings", "attention_rank", "coalition", "reflect"],
        }
        return SubAgentResult(
            id=self.id,
            kernel=self.kernel.to_dict(),
            status=status,
            reflection=reflection.to_dict(),
            actions=outcome.to_dict(),
            findings=findings,
            tool_outputs=tool_outputs,
            sense=sense,
            coalition=coalition,
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
    previous_report: Path | str | None = None,
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
            previous_report=previous_report,
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
