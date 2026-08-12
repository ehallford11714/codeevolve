"""Kernel objectives — atomic goals subagents optimize under a parent objective."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from codeevolve.agent.objective import Objective


KernelName = Literal[
    "stabilize",
    "contain",
    "pay_down",
    "evolve",
    "investigate",
    "search",
    "test",
    "document",
]


KERNEL_CATALOG: dict[str, dict[str, Any]] = {
    "stabilize": {
        "description": "Reduce revert/risk hotspots; prefer quarantine and tests",
        "objective": "raise_stability",
        "wave": "stabilize",
        "tools": ["grep", "file_read", "rag_query", "provenance_hint", "morpheme_scan"],
    },
    "contain": {
        "description": "Fence blast-radius paths; stop coupling growth",
        "objective": "reduce_risk",
        "wave": "contain",
        "tools": ["grep", "file_list", "rag_query", "provenance_hint"],
    },
    "pay_down": {
        "description": "Address debt markers / deprecations",
        "objective": "reduce_debt",
        "wave": "pay_down",
        "tools": ["grep", "file_read", "rag_query", "memory_add"],
    },
    "evolve": {
        "description": "Safe forward change after stabilize/contain",
        "objective": "follow_refactor",
        "wave": "evolve",
        "tools": ["rag_query", "file_read", "morpheme_scan"],
    },
    "investigate": {
        "description": "Read/grep/RAG until stance is no longer insufficient",
        "objective": "follow_refactor",
        "wave": None,
        "tools": ["grep", "file_read", "file_list", "rag_query", "morpheme_scan", "provenance_hint", "memory_add"],
    },
    "search": {
        "description": "Web + repo search for patterns / APIs",
        "objective": "follow_refactor",
        "wave": None,
        "tools": ["web_search", "grep", "rag_query", "memory_add"],
    },
    "test": {
        "description": "Close test gaps on fenced paths",
        "objective": "reduce_risk",
        "wave": "pay_down",
        "tools": ["grep", "file_read", "file_list", "rag_query"],
    },
    "document": {
        "description": "Write path-fence / debt notes from evidence",
        "objective": "follow_refactor",
        "wave": "contain",
        "tools": ["file_read", "provenance_hint", "memory_add", "rag_query"],
    },
}


@dataclass
class KernelObjective:
    name: str
    description: str
    parent: dict[str, Any]
    objective: Objective
    tools: list[str] = field(default_factory=list)
    budget_rounds: int = 1
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parent": dict(self.parent),
            "objective": self.objective.to_dict(),
            "tools": list(self.tools),
            "budget_rounds": self.budget_rounds,
            "path": self.path,
        }


def list_kernels() -> list[dict[str, Any]]:
    return [{"name": k, **v} for k, v in KERNEL_CATALOG.items()]


def make_kernel(
    name: str,
    parent: Objective | dict[str, Any],
    *,
    path: str | None = None,
    budget_rounds: int = 1,
) -> KernelObjective:
    key = (name or "investigate").lower().strip()
    if key not in KERNEL_CATALOG:
        key = "investigate"
    spec = KERNEL_CATALOG[key]
    parent_dict = parent.to_dict() if isinstance(parent, Objective) else dict(parent)
    focus_path = path or parent_dict.get("path")
    obj = Objective.parse(str(spec.get("objective") or "follow_refactor"), path=focus_path, wave=spec.get("wave"))
    if focus_path and obj.kind == "follow_refactor":
        # investigate kernels keep parent kind when useful
        if parent_dict.get("kind") and key in {"investigate", "search", "document"}:
            try:
                obj = Objective.parse(str(parent_dict["kind"]), path=focus_path, wave=spec.get("wave"))
            except Exception:  # noqa: BLE001
                pass
    return KernelObjective(
        name=key,
        description=str(spec["description"]),
        parent=parent_dict,
        objective=obj,
        tools=list(spec.get("tools") or []),
        budget_rounds=budget_rounds,
        path=focus_path,
    )


def decompose_objective(
    objective: Objective,
    *,
    reflection_kernels: list[str] | None = None,
    max_kernels: int = 4,
) -> list[KernelObjective]:
    """Turn a parent objective (+ optional reflection spawn list) into kernel objectives."""
    names: list[str] = []
    if reflection_kernels:
        names.extend(reflection_kernels)
    kind = objective.kind
    if kind == "reduce_debt":
        names.extend(["investigate", "pay_down", "test"])
    elif kind in {"reduce_risk", "stabilize_path"}:
        names.extend(["investigate", "stabilize", "contain"])
    elif kind == "raise_stability":
        names.extend(["stabilize", "test", "contain"])
    else:
        names.extend(["investigate", "stabilize", "pay_down", "evolve"])

    seen: set[str] = set()
    ordered: list[str] = []
    for n in names:
        if n not in seen and n in KERNEL_CATALOG:
            seen.add(n)
            ordered.append(n)
    return [make_kernel(n, objective, path=objective.path) for n in ordered[:max_kernels]]
