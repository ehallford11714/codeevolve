"""SLM/LLM guide for taxonomy labels and evolutionary role assignment."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from codeevolve.models.backends import get_narrative_backend
from codeevolve.models.slm import slm_enabled, slm_json
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
            "other": "evolutionary niche",
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
    Always guide taxonomy. Default path tries the real local SLM (Qwen 0.5B),
    then cloud, then deterministic ``slm_heuristic``.
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
    system = (
        "You are CodeEvolve taxonomy guide. Return ONLY JSON: "
        '{"clades":[{"id":"...","label":"short evolutionary name",'
        '"role":"one sentence niche role","layer_hint":"core|tests|docs|config|utility|other"}]}. '
        "Labels <= 40 chars. Do not invent file paths."
    )

    # 1) Real default SLM for slm/standard tiers
    if t in {"slm", "standard"} and slm_enabled():
        parsed = slm_json(system, payload)
        if parsed and "clades" in parsed:
            return {
                "clades": parsed.get("clades") or [],
                "engine": "hf-slm",
                "tier": spec.name,
                "model": os.environ.get("CODEEVOLVE_HF_MODEL") or spec.hf_model,
            }

    # 2) Cloud for large/frontier or if SLM unavailable but key present
    has_cloud = bool(
        os.environ.get("CODEEVOLVE_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    if has_cloud and (t in {"large", "frontier"} or not slm_enabled()):
        backend_pref = (
            "anthropic"
            if os.environ.get("ANTHROPIC_API_KEY")
            and not (os.environ.get("CODEEVOLVE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))
            else "openai"
        )
        backend = get_narrative_backend(backend_pref)
        raw = backend.write(system, payload)
        parsed = _parse_json_blob(raw)
        if parsed and "clades" in parsed:
            return {
                "clades": parsed.get("clades") or [],
                "engine": backend.name,
                "tier": spec.name,
                "model": os.environ.get("CODEEVOLVE_LLM_MODEL") or spec.cloud_model,
            }

    # 3) Deterministic SLM-style guide (always available)
    guided = _heuristic_guide(clades)
    guided["tier"] = spec.name
    guided["model"] = "slm_heuristic"
    guided["note"] = "Real SLM/cloud unavailable — used slm_heuristic"
    return guided


def apply_guidance(clades: list[Any], guidance: dict[str, Any]) -> dict[str, Any]:
    """Mutate Clade objects in-place with guided labels/roles; return meta."""
    by_id = {
        c["id"]: c
        for c in (guidance.get("clades") or [])
        if isinstance(c, dict) and c.get("id")
    }
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
        clade.role = str(g.get("role") or "")[:200]
    return {
        "engine": guidance.get("engine") or guidance.get("model"),
        "tier": guidance.get("tier"),
        "model": guidance.get("model"),
        "note": guidance.get("note"),
    }
