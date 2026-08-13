"""Cognitive stack: sense (graph) → coalition → reflect → act/tools → compact → spawn."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.agent.action import ActionOutcome, ActionPlan, execute_plan, graph_search_action, plan_from_reflection
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
    sense: dict[str, Any] = field(default_factory=dict)
    coalition: dict[str, Any] = field(default_factory=dict)
    impasse: dict[str, Any] = field(default_factory=dict)

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
            "sense": dict(self.sense),
            "coalition": dict(self.coalition),
            "impasse": dict(self.impasse),
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
        self.previous_report: Path | str | None = None
        self.last_coalition: dict[str, Any] = {}
        self.last_impasse: dict[str, Any] = {}
        self.live_graph: Any = None
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
        previous_report: Path | str | None = None,
    ) -> CognitionState:
        from codeevolve.agent.subagents import findings_from_tool_output
        from codeevolve.graph.control import (
            attention_rank,
            classify_impasse,
            coalition_pack,
            merge_live_reflections,
            sense_graph_crossings,
            sense_note_from_output,
        )
        from codeevolve.graph.model import node_id
        from codeevolve.graph.parse import parse_context
        from codeevolve.graph.precedent import precedent_search

        focus_paths = paths or ([objective.path] if objective.path else None)
        query = objective.description or objective.kind
        if objective.path:
            query = f"{query} {objective.path}"
        prev = previous_report if previous_report is not None else self.previous_report

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

        crossings: list[str] = []
        report_path = self.repo / ".codeevolve" / "report.json"
        current_report: dict[str, Any] | None = None
        if report_path.is_file():
            try:
                loaded = json.loads(report_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    current_report = loaded
            except (OSError, json.JSONDecodeError):
                current_report = None
        if prev:
            crossings = sense_graph_crossings(current_report, prev, memory=self.memory)

        prior_stance = ""
        if round_result and isinstance(round_result.get("proposal"), dict):
            prior_stance = str(round_result["proposal"].get("stance") or "")
        sense_refl = {
            "stance": prior_stance or "continue",
            "next_focus": (focus_paths or [None])[0] or objective.path or objective.kind,
            "insights": crossings[:3],
            "spawn_kernels": [],
        }
        sense_plan = ActionPlan(
            actions=[graph_search_action(sense_refl, objective.to_dict(), previous=prev)]
        )
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
            tags=["graph", "sense", "graph_search"],
            score=1.4,
            meta={"graph_ids": [x for x in hit_ids if x], "ok": bool(sense_res.get("ok"))},
        )

        coalition: dict[str, Any] = {
            "node_ids": [],
            "insufficient": True,
            "stance": "insufficient",
            "count": 0,
        }
        cited_frames: list[str] = []
        last_decision: str | None = None
        if round_result:
            idx = round_result.get("index")
            if idx is not None:
                last_decision = node_id("decision", int(idx))
            prior_prop = round_result.get("proposal") if isinstance(round_result.get("proposal"), dict) else {}
            cited_frames.extend(str(x) for x in (prior_prop.get("frame_ids") or []) if x)
        for h in sense_payload.get("hits") or []:
            if isinstance(h, dict):
                hid = str(h.get("id") or "")
                if hid.startswith("frame:"):
                    cited_frames.append(hid)
        attention_rows: list[dict[str, Any]] = []
        try:
            g = parse_context(
                agent_dir=self.work_dir if self.work_dir.is_dir() else None,
                report=current_report,
            )
            merge_live_reflections(g, self.live_graph)
            attention_rows = attention_rank(
                g,
                path=objective.path,
                frame_ids=cited_frames,
                last_decision=last_decision,
                hops=3,
                per_family=4,
                limit=12,
            )
            sense_hits = list(sense_payload.get("hits") or [])
            sense_hits.extend({"id": r.get("id"), "kind": r.get("kind"), "family": r.get("family")} for r in attention_rows)
            coalition = coalition_pack(
                g,
                hits=sense_hits,
                path=objective.path,
                last_decision=last_decision,
                frame_ids=cited_frames,
            )
            self.live_graph = g
        except Exception:  # noqa: BLE001
            coalition = {"node_ids": [], "insufficient": True, "stance": "insufficient", "count": 0}
        self.last_coalition = coalition
        if coalition.get("insufficient"):
            self.memory.add(
                "graph coalition: insufficient",
                kind="working",
                tags=["graph", "coalition", "insufficient"],
                score=1.1,
            )
        else:
            self.memory.add(
                "coalition "
                + f"n={coalition.get('count')} frames={coalition.get('frame_ids')} "
                + f"decisions={coalition.get('decision_ids')}",
                kind="working",
                tags=["graph", "coalition"],
                score=1.3,
                meta={"graph_ids": coalition.get("node_ids") or []},
            )

        impasse = classify_impasse(round_result, coalition=coalition)
        self.last_impasse = impasse
        if impasse.get("precedent"):
            try:
                g2 = parse_context(agent_dir=self.work_dir if self.work_dir.is_dir() else None)
                prec = precedent_search(g2, query, limit=8)
                self.memory.add(
                    "path-tie precedent: " + ",".join(str(p.get("id") or "") for p in prec[:6]),
                    kind="working",
                    tags=["graph", "precedent", "path_tie"],
                    score=1.3,
                    meta={"graph_ids": [str(p.get("id") or "") for p in prec[:8]]},
                )
            except Exception:  # noqa: BLE001
                pass

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
            coalition=coalition,
        )

        plan = plan_from_reflection(
            reflection.to_dict(),
            objective=objective.to_dict(),
            enable_web=self.allow_web,
            previous=prev,
        )
        plan.actions = [a for a in plan.actions if a.kind != "compact"]
        spawn_actions = [a for a in plan.actions if a.kind == "spawn"]
        plan.actions = [
            a
            for a in plan.actions
            if a.kind != "spawn" and not (a.kind == "tool" and a.name == "graph_search")
        ]
        outcome: ActionOutcome = execute_plan(plan, self.tools)
        outcome.results = list(sense_out.results) + list(outcome.results)

        for row in outcome.results:
            res = row.get("result") or {}
            name = str(res.get("name") or "")
            if name == "graph_search":
                continue
            found = findings_from_tool_output(name, res.get("output")) if res.get("ok") else None
            if found:
                self.memory.add(
                    found,
                    kind="working",
                    tags=[name, "sense"],
                    meta={"tool": name},
                    score=0.95,
                )

        compact = compact_memory(self.memory)
        if round_result:
            rt = compact_round_trace(round_result)
            self.memory.add(rt.summary, kind="compact", tags=["round_trace"], score=1.1)

        kernels = decompose_objective(
            objective,
            reflection_kernels=reflection.spawn_kernels,
            max_kernels=self.max_subagents,
            impasse=impasse,
        )
        sub_results: list[SubAgentResult] = []
        should_spawn = self.spawn and not impasse.get("precedent") and (
            reflection.stance == "spawn"
            or bool(spawn_actions)
            or reflection.stance == "pivot"
            or bool(impasse.get("spawn") and impasse.get("type"))
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
                previous_report=prev,
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
            sense={
                "tool": "graph_search",
                "finding": graph_finding,
                "ok": bool(sense_res.get("ok")),
                "hit_ids": [x for x in hit_ids if x],
                "crossings": crossings[:8],
                "attention_ids": [str(r.get("id") or "") for r in attention_rows if r.get("id")],
                "order": ["graph_search", "crossings", "attention_rank", "coalition", "working-memory", "reflect"],
            },
            coalition=coalition,
            impasse=impasse,
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
            "graph_search sense organ (before reflect; precedent + previous-report delta)",
            "delta crossings (proactive_surface; fail closed)",
            "working-memory hits (ids/family/pivot/flow — not tool:ok)",
            "coalition broadcast (~12 nodes: attention_rank + steiner / knowledge / propose pivot)",
            "memory retrieve (recency × relevance × importance; graph-linked boost)",
            "RAG semantic chunks (in-memory vector default)",
            "morpheme / ontology morphology",
            "reflection (coalition frame_ids / decisions / falsifiers / allowed_because / overridden)",
            "gated propose (heuristic System-1; LLM if empty coalition / typed impasse / overridden)",
            "action + tooling suite (structured JSON tool-calling)",
            "compaction (keeps overridden decisions)",
            "kernel objectives → subagents (typed impasse → kernel; path-tie uses precedent)",
            "write-back with closed validity windows + agent-trace chunks",
            "patch engine (unified hunks, fail-closed, AST/CST symbol fence)",
            "frame-seeded steps (basin/delta)",
            "blast-radius preview (widen/refuse)",
            "git worktree/branch session",
            "test/CI + coverage-gated pass_tests",
            "PR review pack (frames/falsifiers)",
            "budgets + HITL approve + cost logging",
        ],
        "bus": [
            "sense (graph_search + crossings + attention_rank)",
            "coalition (~12)",
            "reflect / propose (gated; coalition in reflect + LLM propose)",
            "write-back (close windows, chunk traces, reflexion on rollback)",
        ],
        "registered_sense_tool": "graph_search",
        "registered_sense_tools": ["graph_search"],
        "tools": [
            "graph_search",
            "file_read",
            "file_list",
            "grep",
            "rag_query",
            "morpheme_scan",
            "memory_search",
            "memory_add",
            "provenance_hint",
            "web_search",
            "shell (opt-in)",
        ],
        "kernels": list_kernels(),
    }
