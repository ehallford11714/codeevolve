"""Action layer — plan and execute tool calls / edit proposals."""

from __future__ import annotations

from dataclasses import dataclass, field
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


def plan_from_reflection(
    reflection: dict[str, Any],
    *,
    objective: dict[str, Any],
    enable_web: bool = True,
) -> ActionPlan:
    """Heuristic action plan from a reflection blob."""
    actions: list[Action] = []
    notes: list[str] = []
    focus = reflection.get("next_focus") or objective.get("path") or objective.get("kind") or ""
    stance = reflection.get("stance") or "continue"

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
