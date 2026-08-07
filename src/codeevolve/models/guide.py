"""SLM taxonomy guide with RAG codebase evidence (heuristic only as last resort)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from codeevolve.models.backends import get_narrative_backend
from codeevolve.models.slm import ensure_default_slm, slm_enabled, slm_json
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


def _heuristic_guide(clades: list[dict[str, Any]], *, rag_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Last-resort guide when no SLM/cloud runtime is available."""
    evidence = (rag_evidence or {}).get("evidence") or {}
    out: dict[str, Any] = {"clades": [], "engine": "slm_heuristic"}
    for c in clades:
        layer = c.get("layer") or "other"
        label = c.get("label") or c.get("id")
        code_type = c.get("code_type") or ""
        type_path = c.get("type_path") or []
        # Sniff role from top RAG snippet keywords when present
        snippets = evidence.get(str(c.get("id"))) or []
        blob = " ".join(str(s.get("text") or "") for s in snippets[:3]).lower()
        role = {
            "core": "domain nucleus — protect boundaries",
            "tests": "verification belt — raise co-touch with prod",
            "docs": "knowledge membrane",
            "config": "control plane / ops niche",
            "utility": "shared substrate — watch overcrowding",
            "other": "evolutionary niche",
        }.get(str(layer), "evolutionary niche")
        if "test" in blob or "pytest" in blob or "assert" in blob:
            layer = "tests"
            role = "verification belt — evidenced by test chunks"
        elif "readme" in blob or "documentation" in blob:
            layer = "docs"
        if code_type:
            role = f"{role}; typed as {code_type}"
            nice = f"{layer}:{code_type}"
        elif type_path:
            nice = f"{layer}:{'/'.join(type_path)}"
        else:
            nice = f"{layer}:{label}"
        if snippets:
            role = f"{role} [rag:{len(snippets)} chunks]"
        out["clades"].append(
            {
                "id": c.get("id"),
                "label": nice[:80],
                "role": role[:200],
                "layer_hint": layer,
            }
        )
    if rag_evidence:
        out["rag"] = (rag_evidence.get("rag") or {})
        out["note"] = "SLM unavailable — heuristic used RAG evidence lightly"
    return out


def _clade_payload(clades: list[dict[str, Any]], rag_evidence: dict[str, Any] | None) -> dict[str, Any]:
    evidence = (rag_evidence or {}).get("evidence") or {}
    slim_clades = []
    for c in clades[:16]:
        cid = str(c.get("id") or "")
        hits = evidence.get(cid) or []
        slim_clades.append(
            {
                "id": cid,
                "label": c.get("label"),
                "layer": c.get("layer"),
                "code_type": c.get("code_type"),
                "type_path": c.get("type_path"),
                "files": (c.get("files") or [])[:10],
                "touch_count": c.get("touch_count"),
                "churn": c.get("churn"),
                "rag_chunks": [
                    {
                        "path": h.get("path"),
                        "score": h.get("score"),
                        "excerpt": (h.get("text") or "")[:420],
                    }
                    for h in hits[:4]
                ],
            }
        )
    return {
        "clades": slim_clades,
        "rag_meta": (rag_evidence or {}).get("rag"),
        "instructions": (rag_evidence or {}).get("instructions")
        or "Use rag_chunks as primary evidence for taxonomy labels and roles.",
    }


_SYSTEM = (
    "You are CodeEvolve SLM taxonomy engine with RAG. Return ONLY JSON: "
    '{"clades":[{"id":"...","label":"short evolutionary name",'
    '"role":"one sentence niche role grounded in retrieved chunks",'
    '"layer_hint":"core|tests|docs|config|utility|other",'
    '"type_path":["architecture","api","rest"]}]}. '
    "Ground every label/role in rag_chunks. Prefer refining type_path from code evidence. "
    "Labels <= 40 chars. Never invent file paths or APIs absent from chunks."
)


def guide_taxonomy(
    clades: list[dict[str, Any]],
    *,
    tier: str | ModelTier | None = None,
    model_override: str | None = None,
    force_heuristic: bool = False,
    rag_evidence: dict[str, Any] | None = None,
    ensure_slm: bool = True,
) -> dict[str, Any]:
    """
    Guide taxonomy with the real local SLM by default, using RAG chunk evidence.

    Fallback order: hf-slm-rag → cloud-rag → heuristic(+rag light).
    """
    t = resolve_tier(tier)
    spec = apply_tier_env(t, model_override=model_override)
    if force_heuristic or os.environ.get("CODEEVOLVE_TAXONOMY_HEURISTIC", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        guided = _heuristic_guide(clades, rag_evidence=rag_evidence)
        guided["tier"] = spec.name
        guided["model"] = "slm_heuristic"
        return guided

    payload = _clade_payload(clades, rag_evidence)
    payload["tier"] = spec.to_dict()

    # Prefer ensuring SLM weights are present for taxonomy
    if ensure_slm and t in {"slm", "standard"} and slm_enabled():
        ensure_default_slm(download=None)

    # 1) Real SLM + RAG
    if t in {"slm", "standard"} and slm_enabled():
        parsed = slm_json(_SYSTEM, payload)
        if parsed and "clades" in parsed:
            return {
                "clades": parsed.get("clades") or [],
                "engine": "hf-slm-rag" if rag_evidence else "hf-slm",
                "tier": spec.name,
                "model": os.environ.get("CODEEVOLVE_HF_MODEL") or spec.hf_model,
                "rag": (rag_evidence or {}).get("rag"),
                "rag_chunks_used": sum(len(v) for v in ((rag_evidence or {}).get("evidence") or {}).values()),
            }

    # 2) Cloud with same RAG payload
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
        raw = backend.write(_SYSTEM, payload)
        parsed = _parse_json_blob(raw)
        if parsed and "clades" in parsed:
            return {
                "clades": parsed.get("clades") or [],
                "engine": f"{backend.name}-rag" if rag_evidence else backend.name,
                "tier": spec.name,
                "model": os.environ.get("CODEEVOLVE_LLM_MODEL") or spec.cloud_model,
                "rag": (rag_evidence or {}).get("rag"),
                "rag_chunks_used": sum(len(v) for v in ((rag_evidence or {}).get("evidence") or {}).values()),
            }

    # 3) Last resort
    guided = _heuristic_guide(clades, rag_evidence=rag_evidence)
    guided["tier"] = spec.name
    guided["model"] = "slm_heuristic"
    guided["note"] = guided.get("note") or "Real SLM/cloud unavailable — used slm_heuristic"
    return guided


def apply_guidance(clades: list[Any], guidance: dict[str, Any]) -> dict[str, Any]:
    """Mutate Clade objects in-place with guided labels/roles/types; return meta."""
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
        tp = g.get("type_path")
        if isinstance(tp, list) and tp:
            clade.type_path = [str(x) for x in tp[:6]]
            clade.code_type = "/".join(clade.type_path)
    return {
        "engine": guidance.get("engine") or guidance.get("model"),
        "tier": guidance.get("tier"),
        "model": guidance.get("model"),
        "note": guidance.get("note"),
        "rag": guidance.get("rag"),
        "rag_chunks_used": guidance.get("rag_chunks_used"),
    }
