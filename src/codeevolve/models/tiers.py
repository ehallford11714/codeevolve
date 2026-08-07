"""Model tiers: default SLM, swap up for sharper evolutionary studies."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

ModelTier = Literal["slm", "standard", "large", "frontier"]

TIER_ORDER: list[ModelTier] = ["slm", "standard", "large", "frontier"]


@dataclass(frozen=True)
class TierSpec:
    name: ModelTier
    label: str
    hf_model: str
    cloud_model: str
    anthropic_model: str
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "hf_model": self.hf_model,
            "cloud_model": self.cloud_model,
            "anthropic_model": self.anthropic_model,
            "purpose": self.purpose,
        }


TIERS: dict[ModelTier, TierSpec] = {
    "slm": TierSpec(
        name="slm",
        label="Small language model (default)",
        hf_model="Qwen/Qwen2.5-0.5B-Instruct",
        cloud_model="gpt-4o-mini",
        anthropic_model="claude-haiku-4-5-20251001",
        purpose="Guide taxonomy labels/roles; fast local evolutionary sketches",
    ),
    "standard": TierSpec(
        name="standard",
        label="Standard",
        hf_model="Qwen/Qwen2.5-1.5B-Instruct",
        cloud_model="gpt-4o-mini",
        anthropic_model="claude-haiku-4-5-20251001",
        purpose="Sharper clade naming and report polish",
    ),
    "large": TierSpec(
        name="large",
        label="Large",
        hf_model="Qwen/Qwen2.5-7B-Instruct",
        cloud_model="gpt-4o",
        anthropic_model="claude-sonnet-4-20250514",
        purpose="Deeper evolutionary studies and refactor narratives",
    ),
    "frontier": TierSpec(
        name="frontier",
        label="Frontier",
        hf_model="Qwen/Qwen2.5-14B-Instruct",
        cloud_model="gpt-4o",
        anthropic_model="claude-opus-4-20250514",
        purpose="Highest-fidelity evolutionary analysis (cloud preferred)",
    ),
}


def resolve_tier(tier: str | None = None) -> ModelTier:
    raw = (tier or os.environ.get("CODEEVOLVE_MODEL_TIER") or "slm").lower().strip()
    aliases = {
        "small": "slm",
        "mini": "slm",
        "default": "slm",
        "mid": "standard",
        "medium": "standard",
        "big": "large",
        "xl": "frontier",
        "max": "frontier",
    }
    raw = aliases.get(raw, raw)
    if raw in TIERS:
        return raw  # type: ignore[return-value]
    return "slm"


def tier_spec(tier: str | None = None) -> TierSpec:
    return TIERS[resolve_tier(tier)]


def apply_tier_env(tier: str | None = None, *, model_override: str | None = None) -> TierSpec:
    """
    Set process env so HF/cloud backends pick models for this tier.
    Explicit CODEEVOLVE_HF_MODEL / CODEEVOLVE_LLM_MODEL still win if already set
    unless model_override is provided.
    """
    spec = tier_spec(tier)
    os.environ["CODEEVOLVE_MODEL_TIER"] = spec.name
    if model_override:
        os.environ["CODEEVOLVE_HF_MODEL"] = model_override
        os.environ["CODEEVOLVE_LLM_MODEL"] = model_override
    else:
        os.environ.setdefault("CODEEVOLVE_HF_MODEL", spec.hf_model)
        # Only set cloud model default when unset
        if not os.environ.get("CODEEVOLVE_LLM_MODEL"):
            os.environ["CODEEVOLVE_LLM_MODEL"] = spec.cloud_model
        if not os.environ.get("CODEEVOLVE_ANTHROPIC_MODEL"):
            os.environ["CODEEVOLVE_ANTHROPIC_MODEL"] = spec.anthropic_model
    return spec
