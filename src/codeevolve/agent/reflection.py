"""Reflection — critique the last round and propose next focus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codeevolve.agent.memory import AgentMemory
from codeevolve.models.backends import get_chat_backend


@dataclass
class Reflection:
    stance: str  # continue | pivot | stop | spawn
    insights: list[str] = field(default_factory=list)
    next_focus: str = ""
    risks: list[str] = field(default_factory=list)
    spawn_kernels: list[str] = field(default_factory=list)
    backend: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "stance": self.stance,
            "insights": list(self.insights),
            "next_focus": self.next_focus,
            "risks": list(self.risks),
            "spawn_kernels": list(self.spawn_kernels),
            "backend": self.backend,
        }


def reflect_heuristic(
    *,
    objective: dict[str, Any],
    round_result: dict[str, Any] | None,
    memory_snapshot: str,
    rag_hits: list[dict[str, Any]] | None = None,
    morphemes: list[dict[str, Any]] | None = None,
) -> Reflection:
    insights: list[str] = []
    risks: list[str] = []
    spawn: list[str] = []
    stance = "continue"
    focus = objective.get("path") or objective.get("kind") or "follow_refactor"

    if not round_result:
        insights.append("No prior round — gather RAG + morphemes before acting")
        spawn.append("investigate")
        return Reflection(
            stance="continue",
            insights=insights,
            next_focus=str(focus),
            spawn_kernels=spawn,
        )

    accepted = bool(round_result.get("accepted"))
    notes = [str(n) for n in (round_result.get("notes") or [])]
    prop = round_result.get("proposal") or {}
    if prop.get("stance") == "insufficient":
        stance = "spawn"
        insights.append("Evidence insufficient — spawn investigate/search kernels")
        spawn.extend(["investigate", "search"])
    elif accepted:
        insights.append("Last action accepted under objective constraints")
        stance = "continue"
    else:
        insights.append("Last action not accepted — pivot path or tool strategy")
        stance = "pivot"
        risks.append("Repeated edits without score gain")
        spawn.append("contain")

    if any("verify failed" in n for n in notes):
        risks.append("verify_cmd failed")
        spawn.append("stabilize")

    if rag_hits:
        insights.append(f"RAG provided {len(rag_hits)} chunks for grounding")
    if morphemes:
        top = ", ".join(str(m.get("stem")) for m in morphemes[:6])
        insights.append(f"Dominant morphemes: {top}")

    if "empty working memory" in (memory_snapshot or ""):
        insights.append("Working memory empty — seed from provenance pack")

    kind = str(objective.get("kind") or "")
    if kind == "reduce_debt":
        spawn.append("pay_down")
    elif kind in {"reduce_risk", "raise_stability", "stabilize_path"}:
        spawn.append("stabilize")

    # dedupe spawn
    seen: set[str] = set()
    uniq = []
    for s in spawn:
        if s not in seen:
            seen.add(s)
            uniq.append(s)

    return Reflection(
        stance=stance,
        insights=insights[:8],
        next_focus=str(focus),
        risks=risks[:6],
        spawn_kernels=uniq[:6],
        backend="heuristic",
    )


def reflect(
    *,
    objective: dict[str, Any],
    round_result: dict[str, Any] | None,
    memory: AgentMemory,
    rag_hits: list[dict[str, Any]] | None = None,
    morphemes: list[dict[str, Any]] | None = None,
    llm: str | bool | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    repo: Any = None,
    memory_query: str | None = None,
) -> Reflection:
    q = memory_query or str(objective.get("kind") or objective.get("description") or "")
    path = objective.get("path") if isinstance(objective.get("path"), str) else None
    try:
        mem_snap = memory.retrieve_block(q, path=path, limit=8)
    except Exception:  # noqa: BLE001
        mem_snap = memory.working_snapshot()
    base = reflect_heuristic(
        objective=objective,
        round_result=round_result,
        memory_snapshot=mem_snap,
        rag_hits=rag_hits,
        morphemes=morphemes,
    )
    if not llm or llm in {False, "heuristic", "off"}:
        memory.add(
            "reflection:{} - {}".format(base.stance, "; ".join(base.insights[:3])),
            kind="reflection",
            tags=["reflection", base.stance],
            meta=base.to_dict(),
            score=1.3,
        )
        return base

    backend = get_chat_backend(llm, model=model, base_url=base_url, api_key=api_key, repo=repo)
    if backend.name == "heuristic":
        memory.add(
            "reflection:{} - {}".format(base.stance, "; ".join(base.insights[:3])),
            kind="reflection",
            tags=["reflection", base.stance],
            meta=base.to_dict(),
            score=1.3,
        )
        return base

    system = (
        "You are reflecting for a CodeEvolve coding agent. "
        "Return JSON keys: stance (continue|pivot|stop|spawn), insights (array), "
        "next_focus (string), risks (array), spawn_kernels (array of kernel names)."
    )
    user = {
        "heuristic": base.to_dict(),
        "objective": objective,
        "round": round_result,
        "memory": mem_snap,
        "rag_hits": (rag_hits or [])[:4],
        "morphemes": (morphemes or [])[:8],
    }
    import json

    text = backend.complete(system, json.dumps(user, default=str), max_tokens=800)
    try:
        # extract JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(text[start : end + 1])
            out = Reflection(
                stance=str(data.get("stance") or base.stance),
                insights=[str(x) for x in (data.get("insights") or base.insights)][:8],
                next_focus=str(data.get("next_focus") or base.next_focus),
                risks=[str(x) for x in (data.get("risks") or base.risks)][:6],
                spawn_kernels=[str(x) for x in (data.get("spawn_kernels") or base.spawn_kernels)][:6],
                backend=backend.name,
            )
            memory.add(
                "reflection:{} - {}".format(out.stance, "; ".join(out.insights[:3])),
                kind="reflection",
                tags=["reflection", out.stance],
                meta=out.to_dict(),
                score=1.4,
            )
            return out
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    memory.add(
        "reflection:{} - {}".format(base.stance, "; ".join(base.insights[:3])),
        kind="reflection",
        tags=["reflection", base.stance],
        meta=base.to_dict(),
        score=1.3,
    )
    return base
