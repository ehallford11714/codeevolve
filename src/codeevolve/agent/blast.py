"""Blast-radius preview before apply — widen fence or refuse oversized edits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BlastPreview:
    paths: list[str]
    co_changers: list[str]
    blast_score: float
    risk_ids: list[str]
    widened_fence: list[str]
    refuse: bool
    reason: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "paths": list(self.paths),
            "co_changers": list(self.co_changers),
            "blast_score": self.blast_score,
            "risk_ids": list(self.risk_ids),
            "widened_fence": list(self.widened_fence),
            "refuse": self.refuse,
            "reason": self.reason,
            "notes": list(self.notes),
        }


def _norm(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def coupled_neighbors(report: dict[str, Any], path: str, *, limit: int = 12) -> list[tuple[str, float]]:
    """Neighbors from risk failure points + coupling edges + blast table."""
    path = _norm(path)
    scored: dict[str, float] = {}

    risk = report.get("risk") or {}
    for fp in risk.get("failure_points") or []:
        fp_path = _norm(str(fp.get("path") or ""))
        if not fp_path:
            continue
        kind = str(fp.get("kind") or "")
        sev = float(fp.get("severity") or 0.5)
        if fp_path == path or path in fp_path or fp_path in path:
            # pull suggested related paths from evidence payload if any
            for ev in fp.get("evidence") or []:
                if isinstance(ev, dict) and ev.get("path"):
                    scored[_norm(str(ev["path"]))] = max(scored.get(_norm(str(ev["path"])), 0), sev)
            if kind in {"hotspot_blast", "change_coupling"}:
                scored[fp_path] = max(scored.get(fp_path, 0), sev)

    coupling = risk.get("coupling") or report.get("coupling") or {}
    edges = coupling.get("edges") or []
    for e in edges:
        if not isinstance(e, dict):
            continue
        a, b = _norm(str(e.get("a") or e.get("src") or "")), _norm(str(e.get("b") or e.get("dst") or ""))
        w = float(e.get("weight") or e.get("score") or 0.5)
        if a == path and b:
            scored[b] = max(scored.get(b, 0), w)
        elif b == path and a:
            scored[a] = max(scored.get(a, 0), w)

    blast = risk.get("blast_radius") or report.get("blast_radius") or []
    if isinstance(blast, dict):
        blast = blast.get("rows") or blast.get("paths") or []
    for row in blast:
        if not isinstance(row, dict):
            continue
        rp = _norm(str(row.get("path") or ""))
        if rp != path:
            continue
        for n in row.get("co_changers") or row.get("neighbors") or []:
            scored[_norm(str(n))] = max(scored.get(_norm(str(n)), 0), float(row.get("blast_score") or 0.5))

    # path_pack style
    for key in ("co_changers", "coupled_paths", "neighbors"):
        for n in (report.get(key) or []):
            if isinstance(n, str):
                scored[_norm(n)] = max(scored.get(_norm(n), 0), 0.4)
            elif isinstance(n, dict) and n.get("path"):
                scored[_norm(str(n["path"]))] = max(scored.get(_norm(str(n["path"])), 0), float(n.get("score") or 0.4))

    scored.pop(path, None)
    return sorted(scored.items(), key=lambda x: -x[1])[:limit]


def preview_blast(
    report: dict[str, Any],
    edit_paths: list[str],
    *,
    fence: list[str] | None = None,
    path_pack: dict[str, Any] | None = None,
    max_blast: float = 8.0,
    max_widen: int = 6,
    auto_widen: bool = True,
    refuse_if_huge: bool = True,
) -> BlastPreview:
    """Preview blast radius; optionally widen fence; refuse if blast is huge."""
    notes: list[str] = []
    fence_list = [_norm(p) for p in (fence or []) if p]
    edit_norm = [_norm(p) for p in edit_paths if p]
    all_neighbors: dict[str, float] = {}
    risk_ids: list[str] = []
    blast_score = 0.0

    pack = path_pack or {}
    # path pack may embed blast / coupling
    for key in ("blast", "blast_radius", "coupling"):
        blob = pack.get(key)
        if isinstance(blob, dict):
            for n in blob.get("co_changers") or blob.get("neighbors") or []:
                if isinstance(n, str):
                    all_neighbors[_norm(n)] = max(all_neighbors.get(_norm(n), 0), 0.5)
                elif isinstance(n, dict) and n.get("path"):
                    all_neighbors[_norm(str(n["path"]))] = max(
                        all_neighbors.get(_norm(str(n["path"])), 0),
                        float(n.get("score") or 0.5),
                    )
            if blob.get("blast_score") is not None:
                try:
                    blast_score = max(blast_score, float(blob["blast_score"]))
                except (TypeError, ValueError):
                    pass

    for p in edit_norm:
        for n, w in coupled_neighbors(report, p):
            all_neighbors[n] = max(all_neighbors.get(n, 0), w)
            blast_score = max(blast_score, w)
        for fp in (report.get("risk") or {}).get("failure_points") or []:
            fp_path = _norm(str(fp.get("path") or ""))
            if fp_path == p or p in fp_path or fp_path in p:
                if fp.get("id"):
                    risk_ids.append(str(fp["id"]))
                try:
                    blast_score = max(blast_score, float(fp.get("severity") or 0) * 3)
                except (TypeError, ValueError):
                    pass

    co = sorted(all_neighbors.keys(), key=lambda k: -all_neighbors[k])
    widened = list(fence_list)
    for n in co:
        if n in widened or n in edit_norm:
            continue
        if auto_widen and len(widened) < max(len(fence_list), 1) + max_widen:
            widened.append(n)
            notes.append(f"widened fence with co-changer {n}")
        if len([x for x in widened if x not in fence_list]) >= max_widen:
            break

    refuse = False
    reason = "ok"
    if refuse_if_huge and blast_score >= max_blast and len(co) >= max_widen:
        refuse = True
        reason = f"blast_score {blast_score:.2f} with {len(co)} co-changers ≥ refuse threshold"
        notes.append(reason)
    elif not edit_norm:
        reason = "no edit paths"

    return BlastPreview(
        paths=edit_norm,
        co_changers=co[:20],
        blast_score=round(blast_score, 4),
        risk_ids=list(dict.fromkeys(risk_ids))[:20],
        widened_fence=widened or edit_norm,
        refuse=refuse,
        reason=reason,
        notes=notes,
    )
