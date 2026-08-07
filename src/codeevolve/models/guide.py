"""SLM/LLM guide for taxonomy labels and evolutionary role assignment."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from codeevolve.models.backends import get_narrative_backend
from codeevolve.models.router import resolve_backend_name
from codeevolve.models.tiers import ModelTier, apply_tier_env, resolve_tier, tier_spec


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _heuristic_guide(clades: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic SLM-stand-in when no model runtime is available."""
    out: dict[str, Any] = {"clades": [], "engine": "slm_heuristic"}
    for c in clades:
        layer = c.get("layer") or "other"
        label = c.get("label") or c.get("id")
        role = {
            "core": "domain nucleus — protect boundaries",
            "tests": "verification belt — raise co-touch with prod",
            "docs": "knowledge membrane",
            "config": "control plane / ops niche",
            "utility": "shared substrate — watch overcrowding",
            "other": "peripheral surface",
        }.get(str(layer), "evolutionary niche")
        nice = f"{layer}:{label}"
        out["clades"].append(
            {
                "id": c.get("id"),
                "label": nice,
                "role": role,
                "layer_hint": layer,
            }
        )
    return out


def guide_taxonomy(
    clades: list[dict[str, Any]],
    *,
    tier: str | ModelTier | None = None,
    model_override: str | None = None,
    force_heuristic: bool = False,
) -> dict[str, Any]:
    """
    Always run an SLM-tier guide by default to name/roles for clades.

    Falls back to deterministic ``slm_heuristic`` if model backends are unavailable.
    """
    t = resolve_tier(tier)
    spec = apply_tier_env(t, model_override=model_override)
    if force_heuristic or os.environ.get("CODEEVOLVE_TAXONOMY_HEURISTIC", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        guided = _heuristic_guide(clades)
        guided["tier"] = spec.name
        guided["model"] = "slm_heuristic"
        return guided

    # Prefer HF for slm/standard; cloud for large/frontier when keys exist
    backend_pref: str | bool
    if t in {"large", "frontier"} and (
        os.environ.get("CODEEVOLVE_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    ):
        backend_pref = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") and not (
            os.environ.get("CODEEVOLVE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        ) else "openai"
    elif os.environ.get("CODEEVOLVE_SKIP_HF", "").lower() in {"1", "true", "yes"}:
        if os.environ.get("CODEEVOLVE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            backend_pref = "openai"
        else:
            guided = _heuristic_guide(clades)
            guided["tier"] = spec.name
            guided["model"] = "slm_heuristic"
            guided["note"] = "HF skipped and no cloud key — used slm_heuristic guide"
            return guided
    else:
        backend_pref = "hf-qwen"

    # Ensure resolve doesn't collapse to pure heuristic without trying
    os.environ.setdefault("CODEEVOLVE_USE_LLM", "1")
    backend = get_narrative_backend(backend_pref)
    system = (
        "You are CodeEvolve taxonomy guide. Given clades (id, seed label, layer, sample files), "
        "return ONLY JSON: {\"clades\":[{\"id\":\"...\",\"label\":\"short evolutionary name\","
        "\"role\":\"one sentence niche role\",\"layer_hint\":\"core|tests|docs|config|utility|other\"}]}. "
        "Keep labels <= 40 chars. Do not invent file paths."
    )
    payload = {
        "tier": spec.to_dict(),
        "clades": [
            {
                "id": c.get("id"),
                "label": c.get("label"),
                "layer": c.get("layer"),
                "files": (c.get("files") or [])[:12],
                "touch_count": c.get("touch_count"),
                "churn": c.get("churn"),
            }
            for c in clades[:20]
        ],
    }
    raw = backend.write(system, payload)
    parsed = _parse_json_blob(raw)
    if not parsed or "clades" not in parsed:
        guided = _heuristic_guide(clades)
        guided["tier"] = spec.name
        guided["model"] = f"{backend.name}+slm_heuristic_fallback"
        guided["raw_preview"] = (raw or "")[:400]
        return guided

    guided = {
        "clades": parsed.get("clades") or [],
        "engine": backend.name,
        "tier": spec.name,
        "model": os.environ.get("CODEEVOLVE_HF_MODEL") or os.environ.get("CODEEVOLVE_LLM_MODEL") or spec.hf_model,
    }
    return guided


def apply_guidance(clades: list[Any], guidance: dict[str, Any]) -> dict[str, Any]:
    """Mutate Clade objects in-place with guided labels/roles; return meta."""
    by_id = {c["id"]: c for c in (guidance.get("clades") or []) if isinstance(c, dict) and c.get("id")}
    for clade in clades:
        g = by_id.get(clade.id)
        if not g:
            continue
        if g.get("label"):
            clade.label = str(g["label"])[:80]
        if g.get("layer_hint") and g["layer_hint"] in {
            "core",
            "tests",
            "docs",
            "config",
            "utility",
            "other",
        }:
            clade.layer = str(g["layer_hint"])
        # stash role on object dynamically for to_dict enrichment
        setattr(clade, "role", str(g.get("role") or "")[:200])
    return {
        "engine": guidance.get("engine") or guidance.get("model"),
        "tier": guidance.get("tier"),
        "model": guidance.get("model"),
        "note": guidance.get("note"),
    }


def default_study_backend(tier: str | None = None) -> str:
    """Backend name for evolutionary report polish at this tier."""
    t = resolve_tier(tier)
    apply_tier_env(t)
    if t == "slm":
        name = resolve_backend_name("hf-qwen")
        if name == "heuristic" and (
            os.environ.get("CODEEVOLVE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        ):
            return "openai"
        return "slm" if name == "heuristic" else name
    if t in {"large", "frontier"}:
        return resolve_backend_name("auto")
    return resolve_backend_name("hf-qwen")
