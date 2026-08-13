"""Action layer — plan and execute tool calls / edit proposals."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from codeevolve.agent.tools.registry import ToolRegistry, ToolResult


ActionKind = Literal[
    "tool",
    "edit",
    "reflect",
    "compact",
    "spawn",
    "noop",
]


@dataclass
class Action:
    kind: ActionKind
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "args": dict(self.args),
            "rationale": self.rationale,
        }


@dataclass
class ActionPlan:
    actions: list[Action] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"actions": [a.to_dict() for a in self.actions], "notes": list(self.notes)}


@dataclass
class ActionOutcome:
    plan: ActionPlan
    results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"plan": self.plan.to_dict(), "results": list(self.results)}


def _graph_search_query(reflection: dict[str, Any], objective: dict[str, Any]) -> str:
    focus = str(reflection.get("next_focus") or objective.get("path") or objective.get("kind") or "")
    insights = [str(x) for x in (reflection.get("insights") or [])[:3] if x]
    kernels = [str(k) for k in (reflection.get("spawn_kernels") or [])[:3] if k]
    path = str(objective.get("path") or "")
    bits = [focus, *insights, *kernels]
    if path and path not in bits:
        bits.append(path)
    return " ".join(b for b in bits if b).strip() or str(objective.get("kind") or "code")


def graph_search_action(
    reflection: dict[str, Any] | None,
    objective: dict[str, Any],
    *,
    previous: str | Path | None = None,
) -> Action:
    """Always-on sense organ: registered graph_search over the context graph."""
    from pathlib import Path as _Path

    refl = reflection or {}
    query = _graph_search_query(refl, objective)
    stance = str(refl.get("stance") or "continue")
    kernels = [str(k).lower() for k in (refl.get("spawn_kernels") or []) if k]
    investigating = stance in {"spawn", "pivot"} or bool(set(kernels) & {"investigate", "search"})
    kernel = next((k for k in (refl.get("spawn_kernels") or []) if str(k).lower() in {"investigate", "search"}), None)
    pivot_implied = stance in {"pivot", "spawn"} or bool(kernels)
    prev = str(previous) if previous else None
    if prev and not _Path(prev).is_file():
        prev = None
    args: dict[str, Any] = {
        "query": query,
        "flow": investigating,
        "traverse": "pivot" if pivot_implied else "rw",
        "limit": 12,
        "surface": True,
        "precedent": True,
        "delta": bool(prev),
    }
    if prev:
        args["previous"] = prev
    if kernel:
        args["kernel"] = str(kernel)
    return Action(
        kind="tool",
        name="graph_search",
        args=args,
        rationale="Sense organ: registered graph_search (precedent + delta + families/pivots/flow)",
    )


def plan_from_reflection(
    reflection: dict[str, Any],
    *,
    objective: dict[str, Any],
    enable_web: bool = True,
    previous: str | Path | None = None,
) -> ActionPlan:
    """Heuristic action plan from a reflection blob."""
    actions: list[Action] = []
    notes: list[str] = []
    focus = reflection.get("next_focus") or objective.get("path") or objective.get("kind") or ""
    stance = reflection.get("stance") or "continue"

    actions.append(graph_search_action(reflection, objective, previous=previous))
    actions.append(
        Action(
            kind="tool",
            name="rag_query",
            args={"query": str(focus), "top_k": 6},
            rationale="Ground next step in semantic chunks",
        )
    )
    actions.append(
        Action(
            kind="tool",
            name="morpheme_scan",
            args={"paths": [objective["path"]] if objective.get("path") else None},
            rationale="Morphology / ontology cues",
        )
    )
    if objective.get("path"):
        actions.append(
            Action(
                kind="tool",
                name="grep",
                args={"pattern": r"TODO|FIXME|deprecated", "path": objective["path"], "max_hits": 20},
                rationale="Scan debt markers near focus path",
            )
        )
        actions.append(
            Action(
                kind="tool",
                name="provenance_hint",
                args={"path": objective["path"]},
                rationale="Path fence provenance",
            )
        )
    else:
        actions.append(
            Action(
                kind="tool",
                name="provenance_hint",
                args={},
                rationale="Load deliberation frames",
            )
        )

    if stance in {"spawn", "pivot"} and enable_web:
        actions.append(
            Action(
                kind="tool",
                name="web_search",
                args={"query": f"code smell {focus} best practice", "max_results": 3},
                rationale="External context when pivoting",
            )
        )

    if stance == "spawn":
        for k in (reflection.get("spawn_kernels") or [])[:3]:
            actions.append(
                Action(kind="spawn", name=str(k), args={"kernel": str(k)}, rationale="Reflection requested spawn")
            )

    actions.append(Action(kind="compact", name="compact_memory", args={}, rationale="Keep context small"))
    notes.append(f"planned from stance={stance}")
    return ActionPlan(actions=actions, notes=notes)


def execute_plan(plan: ActionPlan, tools: ToolRegistry, *, max_actions: int = 12) -> ActionOutcome:
    results: list[dict[str, Any]] = []
    for action in plan.actions[:max_actions]:
        if action.kind == "tool":
            res: ToolResult = tools.call(action.name, **action.args)
            results.append({"action": action.to_dict(), "result": res.to_dict()})
        elif action.kind in {"compact", "reflect", "spawn", "edit", "noop"}:
            results.append(
                {
                    "action": action.to_dict(),
                    "result": {
                        "ok": True,
                        "name": action.name,
                        "output": f"deferred:{action.kind}",
                        "error": None,
                    },
                }
            )
        else:
            results.append(
                {
                    "action": action.to_dict(),
                    "result": {"ok": False, "name": action.name, "output": None, "error": "unknown kind"},
                }
            )
    return ActionOutcome(plan=plan, results=results)
