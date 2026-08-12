"""Assemble a viz model from an EvolveReport or report.json dict."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from codeevolve.viz.intent import classify_intent
from codeevolve.viz.parsimony import ParsimonyResult, fitch_parsimony, spanning_tree


@dataclass
class VizCommit:
    sha: str
    subject: str
    generation: int
    parents: list[str]
    children: list[str]
    clade_id: str
    clade_label: str
    stage: str
    intent: str = "unknown"
    intent_confidence: float = 0.0
    intent_stance: str = "insufficient"
    intent_evidence: list[str] = field(default_factory=list)
    reconstructed: str = ""
    parsimony_change: bool = False
    merge: bool = False
    churn: int = 0
    risk: float = 0.0
    debt: float = 0.0
    analysis_score: float = 0.0
    frame_ids: list[str] = field(default_factory=list)


@dataclass
class VizModel:
    repo: str
    commits: list[VizCommit]
    roots: list[str]
    clades: list[dict[str, Any]]
    hierarchy: dict[str, Any] | None
    gene_flow: list[dict[str, Any]]
    parsimony: ParsimonyResult
    tree_children: dict[str, list[str]]
    tree_parent: dict[str, str]
    merge_count: int
    branch_factor: float
    max_generation: int
    current_stage: str
    node_count: int
    truncated: bool = False
    frames: list[dict[str, Any]] = field(default_factory=list)
    analysis: dict[str, Any] = field(default_factory=dict)
    intent_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "node_count": self.node_count,
            "truncated": self.truncated,
            "roots": list(self.roots),
            "merge_count": self.merge_count,
            "branch_factor": self.branch_factor,
            "max_generation": self.max_generation,
            "current_stage": self.current_stage,
            "parsimony": self.parsimony.to_dict(),
            "clades": list(self.clades),
            "gene_flow": list(self.gene_flow),
            "intent_counts": dict(self.intent_counts),
            "analysis": dict(self.analysis),
            "frames": list(self.frames),
            "commits": [_commit_dict(c) for c in self.commits],
        }


def _commit_dict(c: VizCommit) -> dict[str, Any]:
    return {
        "sha": c.sha,
        "subject": c.subject,
        "generation": c.generation,
        "parents": list(c.parents),
        "children": list(c.children),
        "clade_id": c.clade_id,
        "clade_label": c.clade_label,
        "stage": c.stage,
        "intent": c.intent,
        "intent_confidence": c.intent_confidence,
        "intent_stance": c.intent_stance,
        "intent_evidence": list(c.intent_evidence),
        "reconstructed": c.reconstructed,
        "parsimony_change": c.parsimony_change,
        "merge": c.merge,
        "churn": c.churn,
        "risk": c.risk,
        "debt": c.debt,
        "analysis_score": c.analysis_score,
        "frame_ids": list(c.frame_ids),
    }


def report_to_dict(report: Any) -> dict[str, Any]:
    """Normalize EvolveReport or dict; inject uncapped phylogeny/allocations when live."""
    if isinstance(report, dict):
        return report
    data = report.to_dict()
    phy = getattr(report, "phylogeny", None)
    if phy is not None and getattr(phy, "nodes", None) is not None:
        data.setdefault("phylogeny", {})
        data["phylogeny"]["nodes"] = [n.to_dict() for n in phy.nodes]
        data["phylogeny"]["node_count"] = len(phy.nodes)
    tax = getattr(report, "taxonomy", None)
    if tax is not None and getattr(tax, "allocations", None) is not None:
        data.setdefault("taxonomy", {})
        data["taxonomy"]["allocations"] = [a.to_dict() for a in tax.allocations]
    gen = getattr(report, "genetics", None)
    if gen is not None and getattr(gen, "gene_flow", None) is not None:
        data.setdefault("genetics", {})
        data["genetics"]["gene_flow"] = [g.to_dict() for g in gen.gene_flow]
    prov = getattr(report, "provenance", None)
    if prov is not None and hasattr(prov, "to_dict"):
        data["provenance"] = prov.to_dict()
    return data


def build_model(report: Any) -> VizModel:
    data = report_to_dict(report)
    phy = data.get("phylogeny") or {}
    tax = data.get("taxonomy") or {}
    eco = data.get("ecology") or {}
    genetics = data.get("genetics") or {}
    prov = data.get("provenance") or {}
    debt = data.get("debt") or {}
    risk = data.get("risk") or {}
    dyn = data.get("dynamics") or {}
    stab = data.get("stability") or {}
    fat = data.get("fatigue") or {}

    raw_nodes = list(phy.get("nodes") or [])
    truncated = bool(phy.get("node_count") and phy["node_count"] > len(raw_nodes))
    clade_labels = {c.get("id"): c.get("label") or c.get("id") for c in (tax.get("clades") or []) if c.get("id")}
    dominant = _dominant_clades(tax.get("allocations") or [])
    churn_by = _churn_by_sha(tax.get("allocations") or [])
    stage_of = _stage_by_generation(phy)
    risk_by_clade = _risk_by_clade(risk.get("failure_points") or [])
    debt_by_clade = _debt_by_clade(debt, tax)
    frames = [f for f in (prov.get("frames") or []) if isinstance(f, dict)][:40]

    commits: list[VizCommit] = []
    for n in raw_nodes:
        sha = str(n.get("sha") or "")
        if not sha:
            continue
        cid = dominant.get(sha) or ""
        gen = int(n.get("generation") or 0)
        parents = list(n.get("parent_shas") or n.get("parents") or [])
        subject = str(n.get("subject") or "")
        hit = classify_intent(subject, n_parents=len(parents))
        commits.append(
            VizCommit(
                sha=sha,
                subject=subject,
                generation=gen,
                parents=parents,
                children=list(n.get("children") or []),
                clade_id=cid,
                clade_label=str(clade_labels.get(cid) or cid),
                stage=stage_of.get(gen) or str(phy.get("current_stage") or eco.get("global_stage") or ""),
                intent=hit.kind,
                intent_confidence=hit.confidence,
                intent_stance=hit.stance,
                intent_evidence=list(hit.evidence),
                churn=churn_by.get(sha, 0),
                risk=float(risk_by_clade.get(cid, 0.0)),
                debt=float(debt_by_clade.get(cid, 0.0)),
                merge=len(parents) > 1,
                frame_ids=_frame_ids_for(sha, cid, frames),
            )
        )

    roots = list(phy.get("roots") or [])
    tree_children, tree_parent, tree_roots = spanning_tree(
        [c.__dict__ | {"sha": c.sha, "parent_shas": c.parents} for c in commits],
        roots,
    )
    if not roots:
        roots = tree_roots

    leaf_state = {c.sha: c.clade_id for c in commits if c.clade_id}
    par = fitch_parsimony(tree_children, roots, leaf_state, character="clade")
    change_kids = {b for _, b in par.change_edges}
    max_churn = max((c.churn for c in commits), default=1) or 1
    intent_counts: Counter[str] = Counter()
    for c in commits:
        c.reconstructed = par.reconstructed.get(c.sha) or c.clade_id
        c.parsimony_change = c.sha in change_kids
        c.analysis_score = round(
            min(
                1.0,
                0.45 * min(1.0, c.risk)
                + 0.35 * min(1.0, c.debt)
                + 0.20 * (c.churn / max_churn),
            ),
            4,
        )
        intent_counts[c.intent] += 1

    kw = (tax.get("keyword_taxonomy") or {}) if isinstance(tax.get("keyword_taxonomy"), dict) else {}
    hierarchy = kw.get("hierarchy") if isinstance(kw, dict) else None
    basin = ""
    if isinstance(dyn, dict):
        basin = str((dyn.get("basin") or dyn.get("current_basin") or "") or "")
        if not basin:
            samples = dyn.get("samples") or []
            if samples and isinstance(samples[-1], dict):
                basin = str(samples[-1].get("basin") or samples[-1].get("state") or "")

    analysis = {
        "stage": str(phy.get("current_stage") or eco.get("global_stage") or ""),
        "stage_rationale": str(phy.get("stage_rationale") or eco.get("stage_rationale") or ""),
        "debt_score": debt.get("score"),
        "debt_summary": debt.get("summary") or "",
        "risk_summary": risk.get("summary") or "",
        "risk_count": risk.get("count") or len(risk.get("failure_points") or []),
        "stability": (stab.get("score") if isinstance(stab, dict) else None) or (stab.get("stability") if isinstance(stab, dict) else None),
        "fatigue": fat.get("fatigue_score") if isinstance(fat, dict) else None,
        "basin": basin,
        "parsimony_steps": par.steps,
        "parsimony_ci": par.consistency_index,
        "parsimony_ri": par.retention_index,
        "global_frame_ids": [f.get("id") for f in frames if str(f.get("id") or "") in {"frame:stage", "frame:basin", "frame:selection", "frame:delta:report"} or str(f.get("id") or "").startswith("frame:delta")],
        "note": (
            "Intent is classified from the commit subject (conventional prefix or keywords). "
            "Stance insufficient means the subject is silent — not a motive. "
            "Analysis scores mix clade risk, debt, and allocation churn. "
            "Frames are report provenance (claim→evidence→falsifier)."
        ),
    }

    return VizModel(
        repo=str(data.get("repo") or ""),
        commits=commits,
        roots=roots,
        clades=list(tax.get("clades") or []),
        hierarchy=hierarchy if isinstance(hierarchy, dict) else None,
        gene_flow=list(genetics.get("gene_flow") or []),
        parsimony=par,
        tree_children=tree_children,
        tree_parent=tree_parent,
        merge_count=int(phy.get("merge_count") or 0),
        branch_factor=float(phy.get("branch_factor") or 0),
        max_generation=int(phy.get("max_generation") or 0),
        current_stage=str(phy.get("current_stage") or eco.get("global_stage") or ""),
        node_count=int(phy.get("node_count") or len(commits)),
        truncated=truncated,
        frames=frames,
        analysis=analysis,
        intent_counts=dict(intent_counts),
    )


def _dominant_clades(allocations: list[dict[str, Any]]) -> dict[str, str]:
    scores: dict[str, Counter[str]] = {}
    for a in allocations:
        sha = str(a.get("sha") or "")
        cid = str(a.get("clade_id") or "")
        if not sha or not cid:
            continue
        w = int(a.get("insertions") or 0) + int(a.get("deletions") or 0) or 1
        scores.setdefault(sha, Counter())[cid] += w
    return {sha: ctr.most_common(1)[0][0] for sha, ctr in scores.items() if ctr}


def _churn_by_sha(allocations: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in allocations:
        sha = str(a.get("sha") or "")
        if not sha:
            continue
        out[sha] = out.get(sha, 0) + int(a.get("insertions") or 0) + int(a.get("deletions") or 0)
    return out


def _stage_by_generation(phy: dict[str, Any]) -> dict[int, str]:
    windows = [w for w in (phy.get("stages") or []) if isinstance(w, dict)]
    max_gen = int(phy.get("max_generation") or 0)
    out: dict[int, str] = {}
    if not windows:
        return out
    n = len(windows)
    for g in range(max_gen + 1):
        idx = min(n - 1, int(g / max(1, max_gen) * n)) if max_gen else 0
        out[g] = str(windows[idx].get("stage") or "")
    return out


def _risk_by_clade(points: list[Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for p in points:
        if not isinstance(p, dict):
            continue
        cid = str(p.get("clade_id") or "")
        if not cid:
            continue
        out[cid] = max(out.get(cid, 0.0), float(p.get("severity") or 0.0))
    return out


def _debt_by_clade(debt: dict[str, Any], tax: dict[str, Any]) -> dict[str, float]:
    path_to = tax.get("path_to_clade") or {}
    out: Counter[str] = Counter()
    for key in ("deprecation_hits", "todo_hits"):
        for hit in debt.get(key) or []:
            if not isinstance(hit, dict):
                continue
            path = str(hit.get("path") or "").split(":")[0]
            cid = path_to.get(path)
            if cid:
                sev = {"high": 1.0, "med": 0.55, "low": 0.25}.get(str(hit.get("severity") or ""), 0.4)
                out[cid] += sev
    mx = max(out.values(), default=1) or 1
    return {k: min(1.0, v / mx) for k, v in out.items()}


def _frame_ids_for(sha: str, clade: str, frames: list[dict[str, Any]]) -> list[str]:
    hits: list[str] = []
    short = sha[:7]
    for f in frames:
        fid = str(f.get("id") or "")
        if not fid:
            continue
        clades = [str(x) for x in (f.get("context_clades") or [])]
        claim = str(f.get("claim") or "")
        if clade and clade in clades:
            hits.append(fid)
        elif short and short in claim:
            hits.append(fid)
        elif clade and clade in claim:
            hits.append(fid)
        if len(hits) >= 8:
            break
    return hits
