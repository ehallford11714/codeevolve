"""Budgets, human-in-the-loop approval, and cost logging."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Budget:
    max_rounds: int = 8
    max_wall_seconds: float = 1800.0
    max_tokens: int = 200_000
    max_cost_usd: float = 5.0
    max_llm_calls: int = 40

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_rounds": self.max_rounds,
            "max_wall_seconds": self.max_wall_seconds,
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_llm_calls": self.max_llm_calls,
        }


@dataclass
class CostEvent:
    when: float
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "when": self.when,
            "provider": self.provider,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "label": self.label,
        }


# Rough defaults $/1K tokens (overridable)
_PRICE = {
    "openai:gpt-4o": (0.005, 0.015),
    "openai:gpt-4o-mini": (0.00015, 0.0006),
    "anthropic:claude-sonnet": (0.003, 0.015),
    "grok:grok-3": (0.003, 0.015),
    "default": (0.001, 0.002),
}


def estimate_cost(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    key = f"{provider}:{model}"
    pin, pout = _PRICE.get("default", (0.001, 0.002))
    for k, v in _PRICE.items():
        if k != "default" and (k in key or model in k or provider in k):
            pin, pout = v
            break
    return (tokens_in / 1000.0) * pin + (tokens_out / 1000.0) * pout


@dataclass
class BudgetTracker:
    budget: Budget = field(default_factory=Budget)
    started_at: float = field(default_factory=time.time)
    rounds_used: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    cost_usd: float = 0.0
    events: list[CostEvent] = field(default_factory=list)
    stop_reason: str | None = None

    def record_llm(
        self,
        *,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        label: str = "",
    ) -> None:
        # estimate tokens from label length if zeros
        cost = estimate_cost(provider, model, tokens_in, tokens_out)
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.llm_calls += 1
        self.cost_usd += cost
        self.events.append(
            CostEvent(
                when=time.time(),
                provider=provider,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                label=label,
            )
        )

    def tick_round(self) -> None:
        self.rounds_used += 1

    def check(self) -> tuple[bool, str | None]:
        """Return (ok_to_continue, reason_if_stop)."""
        elapsed = time.time() - self.started_at
        if self.rounds_used >= self.budget.max_rounds:
            self.stop_reason = f"max_rounds {self.budget.max_rounds}"
            return False, self.stop_reason
        if elapsed >= self.budget.max_wall_seconds:
            self.stop_reason = f"max_wall_seconds {self.budget.max_wall_seconds}"
            return False, self.stop_reason
        if self.tokens_in + self.tokens_out >= self.budget.max_tokens:
            self.stop_reason = f"max_tokens {self.budget.max_tokens}"
            return False, self.stop_reason
        if self.cost_usd >= self.budget.max_cost_usd:
            self.stop_reason = f"max_cost_usd {self.budget.max_cost_usd}"
            return False, self.stop_reason
        if self.llm_calls >= self.budget.max_llm_calls:
            self.stop_reason = f"max_llm_calls {self.budget.max_llm_calls}"
            return False, self.stop_reason
        return True, None

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget.to_dict(),
            "rounds_used": self.rounds_used,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "llm_calls": self.llm_calls,
            "cost_usd": round(self.cost_usd, 6),
            "elapsed_seconds": round(time.time() - self.started_at, 2),
            "stop_reason": self.stop_reason,
            "events": [e.to_dict() for e in self.events[-40:]],
        }

    def save(self, path: Path | str) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def approve_edits(
    proposal: dict[str, Any],
    *,
    interactive: bool = True,
    auto_approve: bool = False,
    preapproved: bool | None = None,
) -> tuple[bool, str]:
    """HITL gate before applying edits.

    - auto_approve / preapproved=True → allow
    - preapproved=False → deny
    - interactive → prompt on stdin (non-interactive environments deny)
    """
    if preapproved is True or auto_approve:
        return True, "auto_approved"
    if preapproved is False:
        return False, "denied_by_caller"
    if not interactive:
        return False, "hitl_required_noninteractive"
    paths = []
    for e in (proposal.get("edit_previews") or proposal.get("edits") or []):
        if isinstance(e, dict) and e.get("path"):
            paths.append(str(e["path"]))
    print("\n=== CodeEvolve apply approval ===")
    print(f"step: {proposal.get('step_id')}  backend: {proposal.get('backend')}")
    print(f"paths: {', '.join(paths) or '(none)'}")
    print(f"rationale: {(proposal.get('rationale') or '')[:300]}")
    try:
        ans = input("Apply these edits? [y/N] ").strip().lower()
    except EOFError:
        return False, "no_tty"
    if ans in {"y", "yes"}:
        return True, "user_approved"
    return False, "user_denied"
