"""Governed knowledge: policy and authority nodes (PROV-lite, not W3C PROV-O)."""

from __future__ import annotations

from typing import Any

from codeevolve.graph.model import ContextGraph, node_id

AUTHORITY_ID = "authority:codeevolve"

POLICIES: tuple[tuple[str, str, str], ...] = (
    (
        "policy:insufficient-if-silent",
        "insufficient if silent",
        "Do not invent why a line exists when the record is silent; stance insufficient.",
    ),
    (
        "policy:no-chaos",
        "no chaos/Lyapunov",
        "Do not claim chaos or Lyapunov exponents from git history.",
    ),
    (
        "policy:dry-run-before-apply",
        "dry-run before apply",
        "Review dry-run proposals (frame_ids, falsifier, edit_previews) before apply=true.",
    ),
    (
        "policy:falsifier-required",
        "falsifier required",
        "Deliberation frames carry claim → evidence → falsifier; respect measure.",
    ),
    (
        "policy:path-fence",
        "path fence",
        "Fence edits to a path pack / blast radius before touching a hotspot.",
    ),
)


def ingest_policies(g: ContextGraph, *, source: str = "codeevolve.policy") -> None:
    g.add_node(
        AUTHORITY_ID,
        "authority",
        label="CodeEvolve",
        stage="deliberate",
        family="knowledge",
        text="Evolutionary provenance authority: silent records stay insufficient.",
        source=source,
        confidence=1.0,
        authority=AUTHORITY_ID,
    )
    for pid, label, text in POLICIES:
        g.add_node(
            pid,
            "policy",
            label=label,
            stage="deliberate",
            family="knowledge",
            text=text,
            source=source,
            confidence=1.0,
            authority=AUTHORITY_ID,
        )
        g.add_edge(pid, AUTHORITY_ID, "constrained_by")


def policy_for_outcome(outcome: str, stance: str = "") -> list[str]:
    ids: list[str] = []
    st = (stance or "").lower()
    oc = (outcome or "").lower()
    if st == "insufficient" or oc == "insufficient":
        ids.append("policy:insufficient-if-silent")
    if oc in {"dry-run", "preview"} or "dry-run" in oc:
        ids.append("policy:dry-run-before-apply")
    if oc in {"refused", "fence", "blast"}:
        ids.append("policy:path-fence")
    if "falsifier" in oc or oc == "defer":
        ids.append("policy:falsifier-required")
    if not ids:
        ids.append("policy:insufficient-if-silent")
    return ids


def outcome_from_round(rnd: dict[str, Any]) -> str:
    notes = " ".join(str(x) for x in (rnd.get("notes") or [])).lower()
    stance = ""
    prop = rnd.get("proposal")
    if isinstance(prop, dict):
        stance = str(prop.get("stance") or "").lower()
    if "rolled back" in notes or "rollback" in notes:
        return "overridden"
    if stance == "insufficient":
        return "insufficient"
    if stance == "defer":
        return "refused"
    if rnd.get("accepted"):
        return "applied"
    if rnd.get("applied"):
        return "applied"
    if "dry-run" in notes or not rnd.get("applied"):
        return "dry-run"
    return "refused"


def decision_rel(outcome: str) -> str:
    oc = (outcome or "").lower()
    if oc in {"applied", "allowed", "dry-run", "preview"}:
        return "allowed_because"
    if oc in {"overridden", "rollback"}:
        return "overridden"
    return "refused"


def claim_id(frame_id: str) -> str:
    fid = str(frame_id)
    if fid.startswith("claim:"):
        return fid
    if fid.startswith("frame:"):
        return node_id("claim", fid.split(":", 1)[-1])
    return node_id("claim", fid)
