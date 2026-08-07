"""Unified provenance ledger for deliberation over evolutionary history.

Normalizes scattered CodeEvolve signals into queryable records + claim→evidence
chains. This is the substrate for reasoning *about* a codebase's path — not a
model of reasoning itself.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Literal

ProvenanceKind = Literal[
    "commit_delta",
    "lineage",
    "clade",
    "lifecycle_event",
    "changepoint",
    "stage_segment",
    "hypothesis",
    "experiment",
    "failure_point",
    "drift",
    "signal",
    "code_type",
    "state_sample",
    "trajectory",
    "impulse_response",
    "regime_basin",
    "path_episode",
    "selection_item",
    "report_delta",
    "coupling_edge",
    "debt_item",
    "gene_flow",
    "clone_link",
    "reticulation",
    "blast_radius",
    "symbol",
    "cst_delta",
]


@dataclass
class EvidenceRef:
    """Pointer into the ledger or underlying report."""

    record_id: str
    kind: ProvenanceKind | str
    role: str = "supports"  # supports | contradicts | context | measures
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "kind": self.kind,
            "role": self.role,
            "note": self.note,
        }


@dataclass
class ProvenanceRecord:
    id: str
    kind: ProvenanceKind
    when: str | None = None  # ISO timestamp when known
    path: str | None = None
    clade_id: str | None = None
    sha: str | None = None
    label: str = ""
    summary: str = ""
    confidence: float | None = None
    tags: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    links: list[EvidenceRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "when": self.when,
            "path": self.path,
            "clade_id": self.clade_id,
            "sha": self.sha,
            "label": self.label,
            "summary": self.summary,
            "confidence": self.confidence,
            "tags": list(self.tags),
            "payload": dict(self.payload),
            "links": [x.to_dict() for x in self.links],
        }


@dataclass
class DeliberationFrame:
    """One claim with joined provenance — unit of deliberation."""

    id: str
    claim: str
    stance: str  # support | weak | contradict | insufficient | open | risk
    confidence: float
    evidence: list[EvidenceRef] = field(default_factory=list)
    falsifier: str = ""
    measure: str = ""
    suggested_questions: list[str] = field(default_factory=list)
    context_paths: list[str] = field(default_factory=list)
    context_clades: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim": self.claim,
            "stance": self.stance,
            "confidence": round(self.confidence, 3),
            "evidence": [e.to_dict() for e in self.evidence],
            "falsifier": self.falsifier,
            "measure": self.measure,
            "suggested_questions": list(self.suggested_questions),
            "context_paths": list(self.context_paths)[:20],
            "context_clades": list(self.context_clades)[:12],
        }


@dataclass
class ProvenanceLedger:
    repo: str
    records: list[ProvenanceRecord] = field(default_factory=list)
    frames: list[DeliberationFrame] = field(default_factory=list)
    indexes: dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "summary": self.summary,
            "record_count": len(self.records),
            "frame_count": len(self.frames),
            "indexes": {
                "kinds": dict(self.indexes.get("kinds") or {}),
                "path_count": len(self.indexes.get("by_path") or {}),
                "clade_count": len(self.indexes.get("by_clade") or {}),
                "time_span": self.indexes.get("time_span"),
            },
            "frames": [f.to_dict() for f in self.frames],
            "records": [r.to_dict() for r in self.records],
        }

    def query(
        self,
        *,
        path: str | None = None,
        clade: str | None = None,
        kind: str | None = None,
        since: str | None = None,
        until: str | None = None,
        tag: str | None = None,
        limit: int = 80,
    ) -> list[ProvenanceRecord]:
        out: list[ProvenanceRecord] = []
        for r in self.records:
            if path and path not in (r.path or "") and not (r.path or "").endswith(path):
                # also allow prefix match
                if not (r.path or "").startswith(path) and path not in (r.summary or ""):
                    continue
            if clade and r.clade_id != clade and clade not in (r.tags or []):
                continue
            if kind and r.kind != kind:
                continue
            if tag and tag not in r.tags:
                continue
            if since and r.when and r.when < since:
                continue
            if until and r.when and r.when > until:
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def frame_for(self, frame_id: str) -> DeliberationFrame | None:
        for f in self.frames:
            if f.id == frame_id or f.id.endswith(frame_id) or frame_id in f.id:
                return f
        return None

    def record_for(self, record_id: str) -> ProvenanceRecord | None:
        for r in self.records:
            if r.id == record_id:
                return r
        return None

    def resolve(
        self,
        start_id: str,
        *,
        depth: int = 2,
        max_nodes: int = 40,
    ) -> dict[str, Any]:
        """Walk evidence links outward from a record or frame id."""
        by_id = {r.id: r for r in self.records}
        frame = self.frame_for(start_id)
        seeds: list[str] = []
        if frame:
            seeds = [e.record_id for e in frame.evidence if e.record_id]
        elif start_id in by_id:
            seeds = [start_id]
        else:
            # soft match on label / path
            for r in self.records:
                if start_id in r.id or start_id == (r.path or "") or start_id in r.label:
                    seeds.append(r.id)
                    if len(seeds) >= 5:
                        break

        seen: set[str] = set()
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        frontier = [(sid, 0) for sid in seeds]

        while frontier and len(nodes) < max_nodes:
            rid, d = frontier.pop(0)
            if rid in seen or rid not in by_id:
                continue
            seen.add(rid)
            rec = by_id[rid]
            nodes.append({"depth": d, **rec.to_dict()})
            if d >= depth:
                continue
            for lk in rec.links:
                if not lk.record_id:
                    continue
                edges.append(
                    {
                        "from": rid,
                        "to": lk.record_id,
                        "role": lk.role,
                        "note": lk.note,
                    }
                )
                if lk.record_id not in seen:
                    frontier.append((lk.record_id, d + 1))
            # reverse links (who points here)
            for other in self.records:
                if other.id in seen:
                    continue
                for lk in other.links:
                    if lk.record_id == rid:
                        edges.append(
                            {
                                "from": other.id,
                                "to": rid,
                                "role": lk.role,
                                "note": "reverse",
                            }
                        )
                        if d + 1 <= depth:
                            frontier.append((other.id, d + 1))

        return {
            "start": start_id,
            "frame": frame.to_dict() if frame else None,
            "node_count": len(nodes),
            "nodes": nodes,
            "edges": edges[:120],
        }

    def timeline(
        self,
        *,
        path: str | None = None,
        clade: str | None = None,
        kinds: Iterable[str] | None = None,
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        """Chronological provenance slice (records with `when`)."""
        kind_set = set(kinds) if kinds else None
        dated = []
        for r in self.records:
            if not r.when:
                continue
            if path and path not in (r.path or "") and not (r.path or "").startswith(path or ""):
                # keep global events even when path-focused
                if r.kind not in {"lifecycle_event", "changepoint", "stage_segment"}:
                    continue
            if clade and r.clade_id and r.clade_id != clade:
                continue
            if kind_set and r.kind not in kind_set:
                continue
            dated.append(r)
        dated.sort(key=lambda x: x.when or "")
        return [
            {
                "when": r.when,
                "id": r.id,
                "kind": r.kind,
                "label": r.label,
                "summary": r.summary,
                "path": r.path,
                "clade_id": r.clade_id,
                "confidence": r.confidence,
            }
            for r in dated[:limit]
        ]

    def expand_frame(self, frame_id: str) -> dict[str, Any] | None:
        """Frame plus resolved evidence records — primary deliberation unit."""
        frame = self.frame_for(frame_id)
        if not frame:
            return None
        by_id = {r.id: r for r in self.records}
        evidence_records = []
        for e in frame.evidence:
            rec = by_id.get(e.record_id)
            if rec:
                evidence_records.append({"role": e.role, "note": e.note, **rec.to_dict()})
        chain = self.resolve(frame.id, depth=2)
        return {
            "frame": frame.to_dict(),
            "evidence_records": evidence_records,
            "chain": {"nodes": chain["nodes"], "edges": chain["edges"]},
            "timeline": self.timeline(
                path=frame.context_paths[0] if frame.context_paths else None,
                clade=frame.context_clades[0] if frame.context_clades else None,
                limit=30,
            ),
            "howto": (
                "Accept/reject the claim only after checking falsifier against "
                "evidence_records and timeline; prefer measures that are re-runnable."
            ),
        }

    def deliberation_pack(
        self,
        *,
        path: str | None = None,
        clade: str | None = None,
        max_frames: int = 12,
        max_records: int = 40,
    ) -> dict[str, Any]:
        """Compact pack for an agent/human deliberating over provenance."""
        frames = list(self.frames)
        if path or clade:
            recs = self.query(path=path, clade=clade, limit=max_records)
            ids = {r.id for r in recs}
            focused = [
                f
                for f in frames
                if any(e.record_id in ids for e in f.evidence)
                or (path and any(path in p or p.startswith(path) for p in f.context_paths))
                or (clade and clade in f.context_clades)
            ]
            frames = focused or frames[:max_frames]
            # Prefer path_pack enrichment
            path_focus = self.path_pack(path, clade=clade, max_records=max_records) if path else None
        else:
            recs = self.records[:max_records]
            path_focus = None
        frames = frames[:max_frames]
        return {
            "repo": self.repo,
            "summary": self.summary,
            "focus": {"path": path, "clade": clade},
            "frames": [f.to_dict() for f in frames],
            "records": [r.to_dict() for r in recs[:max_records]],
            "timeline": self.timeline(path=path, clade=clade, limit=25),
            "path_focus": path_focus,
            "howto": (
                "Deliberate by (1) picking a frame, (2) inspecting linked evidence "
                "records / timeline, (3) checking falsifier/measure before acting, "
                "(4) asking suggested_questions against fresh git state. "
                "Use resolve(frame_id) or expand_frame(frame_id) for chains."
            ),
        }

    def path_pack(
        self,
        path: str,
        *,
        clade: str | None = None,
        max_records: int = 50,
    ) -> dict[str, Any]:
        """Path-centric provenance: lineage → deltas → clade → related frames."""
        recs = self.query(path=path, clade=clade, limit=max_records)
        lineage = next((r for r in recs if r.kind == "lineage"), None)
        deltas = [r for r in recs if r.kind == "commit_delta"][:20]
        types = [r for r in recs if r.kind == "code_type"][:5]
        risks = [r for r in recs if r.kind == "failure_point"]
        cid = clade or (lineage.clade_id if lineage else None) or (recs[0].clade_id if recs else None)
        clade_rec = self.record_for(_rid("clade", cid)) if cid else None
        frames = [
            f
            for f in self.frames
            if path in f.context_paths
            or any(path in (self.record_for(e.record_id).path or "") for e in f.evidence if self.record_for(e.record_id))
            or (cid and cid in f.context_clades)
        ][:8]
        episodes = [r for r in recs if r.kind == "path_episode"][:8]
        if not episodes:
            episodes = [r for r in self.records if r.kind == "path_episode" and r.path and path in r.path][:8]
        flows = [
            r
            for r in self.records
            if r.kind in {"gene_flow", "clone_link", "reticulation", "coupling_edge"}
            and (path in (r.path or "") or path in r.summary or (cid and r.clade_id == cid))
        ][:10]
        blast = next((r for r in self.records if r.kind == "blast_radius" and r.path and path in r.path), None)
        symbols = [r for r in self.records if r.kind == "symbol" and r.path and path in (r.path or "")][:12]
        cst = [r for r in self.records if r.kind == "cst_delta" and r.path and path in (r.path or "")][:8]
        return {
            "path": path,
            "clade_id": cid,
            "lineage": lineage.to_dict() if lineage else None,
            "code_type": types[0].to_dict() if types else None,
            "clade": clade_rec.to_dict() if clade_rec else None,
            "blast_radius": blast.to_dict() if blast else None,
            "symbols": [s.to_dict() for s in symbols],
            "cst_deltas": [c.to_dict() for c in cst],
            "episodes": [e.to_dict() for e in episodes],
            "recent_deltas": [d.to_dict() for d in deltas],
            "risks": [r.to_dict() for r in risks],
            "graph_links": [f.to_dict() for f in flows],
            "related_frames": [f.to_dict() for f in frames],
            "timeline": self.timeline(path=path, clade=cid, limit=20),
            "suggested_questions": [
                f"What first introduced {path} and what clade owned it?",
                f"Which path episodes coincide with lifecycle shocks?",
                "Is heating/cooling on this typed branch falsified by recent deltas?",
                "Do blast radius / CST deltas justify containment before edit?",
            ],
        }


def _rid(kind: str, *parts: Any) -> str:
    body = ":".join(str(p) for p in parts if p is not None and p != "")
    return f"{kind}:{body}"[:160]


def _ingest_dynamics_and_process(report: dict[str, Any], add) -> None:
    """State trajectory, impulses, basins, episodes, selection, report.diff."""
    from codeevolve.provenance.dynamics import build_dynamics

    dyn = report.get("dynamics")
    if not isinstance(dyn, dict) or not dyn.get("samples"):
        dyn = build_dynamics(report).to_dict()

    samples = dyn.get("samples") or []
    for s in samples:
        if not isinstance(s, dict):
            continue
        add(
            ProvenanceRecord(
                id=_rid("state", s.get("month") or s.get("when")),
                kind="state_sample",
                when=s.get("when"),
                label=str(s.get("month") or ""),
                summary=(
                    f"state {s.get('month')}: activity={s.get('activity')} "
                    f"churn={s.get('churn')} instability={s.get('instability')}"
                ),
                tags=["dynamics", "state"],
                payload=s,
            )
        )
    if samples:
        add(
            ProvenanceRecord(
                id=_rid("trajectory", "global"),
                kind="trajectory",
                when=samples[0].get("when") if isinstance(samples[0], dict) else None,
                label="global_trajectory",
                summary=str(dyn.get("summary") or f"trajectory n={len(samples)}"),
                confidence=0.35 if dyn.get("insufficient") else 0.65,
                tags=["dynamics", "trajectory"]
                + (["insufficient"] if dyn.get("insufficient") else []),
                payload={
                    "sample_count": len(samples),
                    "insufficient": dyn.get("insufficient"),
                    "months": [s.get("month") for s in samples if isinstance(s, dict)],
                },
                links=[
                    EvidenceRef(_rid("state", s.get("month")), "state_sample", "measures")
                    for s in samples[-8:]
                    if isinstance(s, dict)
                ],
            )
        )
    for imp in dyn.get("impulses") or []:
        if not isinstance(imp, dict):
            continue
        iid = _rid("impulse", imp.get("event_kind"), imp.get("event_label"), (imp.get("event_when") or "")[:10])
        add(
            ProvenanceRecord(
                id=iid,
                kind="impulse_response",
                when=imp.get("event_when"),
                label=str(imp.get("event_label") or ""),
                summary=str(imp.get("summary") or ""),
                confidence=imp.get("confidence"),
                tags=["dynamics", "impulse", str(imp.get("event_kind") or "")],
                payload=imp,
                links=[
                    EvidenceRef(
                        _rid(
                            "event",
                            imp.get("event_kind"),
                            imp.get("event_label"),
                            str(imp.get("event_when") or "")[:10],
                        ),
                        "lifecycle_event",
                        "context",
                    )
                ],
            )
        )
    for b in dyn.get("basins") or []:
        if not isinstance(b, dict):
            continue
        add(
            ProvenanceRecord(
                id=_rid("basin", b.get("stage"), (b.get("start") or "")[:10]),
                kind="regime_basin",
                when=b.get("start"),
                label=str(b.get("stage") or ""),
                summary=str(b.get("summary") or ""),
                confidence=float(b.get("occupancy") or 0.0),
                tags=["dynamics", "basin", str(b.get("stage") or "")],
                payload=b,
            )
        )
    for ep in dyn.get("episodes") or []:
        if not isinstance(ep, dict):
            continue
        add(
            ProvenanceRecord(
                id=_rid("episode", ep.get("path"), ep.get("start_sha"), ep.get("end_sha")),
                kind="path_episode",
                when=ep.get("start_when"),
                path=ep.get("path"),
                clade_id=ep.get("clade_id"),
                sha=ep.get("end_sha"),
                label=str(ep.get("path") or ""),
                summary=str(ep.get("summary") or ""),
                tags=["episode", "path"],
                payload=ep,
                links=[
                    EvidenceRef(_rid("lineage", ep.get("path")), "lineage", "context")
                    if ep.get("path")
                    else EvidenceRef("", "lineage")
                ],
            )
        )

    # Selection / PR / issue evidence
    sel = report.get("selection") or {}
    if sel:
        add(
            ProvenanceRecord(
                id=_rid("signal", "selection_pressure"),
                kind="signal",
                label="selection_pressure",
                summary=(
                    f"selection pressure={sel.get('pressure_score')} "
                    f"open={sel.get('open_issues')} bug_rate={sel.get('bug_label_rate')}"
                ),
                confidence=float(sel.get("pressure_score") or 0.0),
                tags=["selection", "process"],
                payload={
                    k: sel.get(k)
                    for k in (
                        "pressure_score",
                        "open_issues",
                        "bug_label_rate",
                        "pr_merge_rate",
                        "issues_sampled",
                        "prs_sampled",
                    )
                },
            )
        )
    for issue in (sel.get("recent_issues") or [])[:25]:
        if not isinstance(issue, dict):
            continue
        add(
            ProvenanceRecord(
                id=_rid("issue", issue.get("number"), issue.get("title")),
                kind="selection_item",
                when=issue.get("created_at") or issue.get("closed_at"),
                label=f"#{issue.get('number')} {issue.get('title')}",
                summary=f"issue #{issue.get('number')} state={issue.get('state')} labels={issue.get('labels')}",
                tags=["selection", "issue", str(issue.get("epistemic") or "stated")],
                payload=issue,
            )
        )
    for pr in (sel.get("recent_prs") or [])[:25]:
        if not isinstance(pr, dict):
            continue
        add(
            ProvenanceRecord(
                id=_rid("pr", pr.get("number"), pr.get("title")),
                kind="selection_item",
                when=pr.get("merged_at") or pr.get("created_at"),
                label=f"PR#{pr.get('number')} {pr.get('title')}",
                summary=(
                    f"pr #{pr.get('number')} merged={bool(pr.get('merged_at'))} "
                    f"state={pr.get('state')}"
                ),
                tags=["selection", "pr", str(pr.get("epistemic") or "stated")],
                payload=pr,
            )
        )

    # Inter-report diff
    diff = report.get("diff") or {}
    if diff.get("deltas") or diff.get("improved") or diff.get("worsened"):
        add(
            ProvenanceRecord(
                id=_rid("delta", "report"),
                kind="report_delta",
                label="inter_report_diff",
                summary=(
                    f"improved={len(diff.get('improved') or [])} "
                    f"worsened={len(diff.get('worsened') or [])}"
                ),
                tags=["diff", "temporal"],
                payload=diff,
            )
        )
        for item in (diff.get("worsened") or [])[:12]:
            add(
                ProvenanceRecord(
                    id=_rid("delta", "worse", item),
                    kind="report_delta",
                    label=str(item),
                    summary=f"worsened: {item}",
                    tags=["diff", "worsened"],
                    payload={"direction": "worsened", "item": item},
                )
            )
        for item in (diff.get("improved") or [])[:12]:
            add(
                ProvenanceRecord(
                    id=_rid("delta", "better", item),
                    kind="report_delta",
                    label=str(item),
                    summary=f"improved: {item}",
                    tags=["diff", "improved"],
                    payload={"direction": "improved", "item": item},
                )
            )


def _ingest_blast_and_micro(report: dict[str, Any], add) -> None:
    """Blast radius + symbol/CST micro-provenance."""
    for row in report.get("blast_radius") or []:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        add(
            ProvenanceRecord(
                id=_rid("blast", path),
                kind="blast_radius",
                path=path or None,
                label=path,
                summary=(
                    f"blast {path}: co_changers={row.get('co_changers')} "
                    f"score={row.get('blast_score')}"
                ),
                confidence=float(row.get("blast_score") or 0.0),
                tags=["blast", "risk"],
                payload=row,
                links=[
                    EvidenceRef(_rid("lineage", path), "lineage", "context")
                    if path
                    else EvidenceRef("", "lineage")
                ],
            )
        )

    sym = report.get("symbols") or {}
    for s in (sym.get("symbols") or [])[:80]:
        if not isinstance(s, dict):
            continue
        path = str(s.get("path") or "")
        qn = str(s.get("qualname") or "")
        add(
            ProvenanceRecord(
                id=_rid("sym", qn or path),
                kind="symbol",
                path=path or None,
                label=qn,
                summary=f"symbol {qn} ({s.get('kind')}) @ {path}:{s.get('line')}",
                tags=["micro", "symbol", str(s.get("kind") or "")],
                payload=s,
                links=[
                    EvidenceRef(_rid("lineage", path), "lineage", "context")
                    if path
                    else EvidenceRef("", "lineage"),
                    EvidenceRef(_rid("blast", path), "blast_radius", "measures")
                    if path
                    else EvidenceRef("", "blast_radius"),
                ],
            )
        )

    cst = report.get("cst_evolution") or {}
    for d in (cst.get("deltas") or [])[:40]:
        if not isinstance(d, dict):
            continue
        path = str(d.get("path") or "")
        node = str(d.get("node") or d.get("type") or "node")
        add(
            ProvenanceRecord(
                id=_rid("cst", path, node, d.get("window")),
                kind="cst_delta",
                path=path or None,
                when=d.get("when") or d.get("timestamp"),
                label=f"{node}@{path}",
                summary=(
                    f"CST {node} Δ={d.get('delta')} on {path} "
                    f"window={d.get('window')}"
                ),
                tags=["micro", "cst", node],
                payload=d,
                links=[
                    EvidenceRef(_rid("lineage", path), "lineage", "context")
                    if path
                    else EvidenceRef("", "lineage")
                ],
            )
        )
    for w in (cst.get("windows") or [])[:12]:
        if not isinstance(w, dict):
            continue
        add(
            ProvenanceRecord(
                id=_rid("cstwin", w.get("label") or w.get("window") or w.get("index")),
                kind="cst_delta",
                when=w.get("when"),
                label=str(w.get("label") or "cst_window"),
                summary=str(w.get("summary") or f"CST window {w.get('label')}: {w.get('counts')}"),
                tags=["micro", "cst", "window"],
                payload=w,
            )
        )


def _ingest_genetics_graph(report: dict[str, Any], add) -> None:
    gen = report.get("genetics") or {}
    for edge in (gen.get("gene_flow") or [])[:40]:
        if not isinstance(edge, dict):
            continue
        src = edge.get("source_clade") or edge.get("a")
        dst = edge.get("target_clade") or edge.get("b")
        add(
            ProvenanceRecord(
                id=_rid("flow", src, dst),
                kind="gene_flow",
                clade_id=str(src) if src else None,
                label=f"{src}→{dst}",
                summary=f"gene_flow weight={edge.get('weight')} kind={edge.get('kind')}",
                tags=["genetics", "flow", str(edge.get("kind") or "")],
                payload=edge,
                links=[
                    EvidenceRef(_rid("clade", src), "clade", "context") if src else EvidenceRef("", "clade"),
                    EvidenceRef(_rid("clade", dst), "clade", "context") if dst else EvidenceRef("", "clade"),
                ],
            )
        )
    for h in (gen.get("hgt_suspects") or [])[:20]:
        if not isinstance(h, dict):
            continue
        add(
            ProvenanceRecord(
                id=_rid("hgt", h.get("sha")),
                kind="gene_flow",
                sha=h.get("sha"),
                label=str(h.get("subject") or "hgt_suspect"),
                summary=f"HGT suspect sha={str(h.get('sha') or '')[:7]} files={h.get('files')}",
                tags=["genetics", "hgt"],
                payload=h,
            )
        )
    clones = report.get("clones") or {}
    for g in (clones.get("genealogies") or [])[:30]:
        if not isinstance(g, dict):
            continue
        add(
            ProvenanceRecord(
                id=_rid("clone", g.get("id") or g.get("qualname") or g.get("hash")),
                kind="clone_link",
                path=g.get("path") or (g.get("paths") or [None])[0],
                label=str(g.get("qualname") or g.get("pattern") or "clone"),
                summary=str(g.get("summary") or g.get("pattern") or "clone genealogy"),
                tags=["genetics", "clone", str(g.get("pattern") or "")],
                payload=g,
            )
        )
    ret = report.get("reticulation") or {}
    for edge in (ret.get("edges") or [])[:30]:
        if not isinstance(edge, dict):
            continue
        a = edge.get("a") or edge.get("source") or edge.get("path_a")
        b = edge.get("b") or edge.get("target") or edge.get("path_b")
        add(
            ProvenanceRecord(
                id=_rid("ret", a, b),
                kind="reticulation",
                path=str(a) if a else None,
                label=f"{a}≈{b}",
                summary=f"reticulation dist={edge.get('distance') or edge.get('similarity')}",
                tags=["genetics", "reticulation"],
                payload=edge,
                links=[
                    EvidenceRef(_rid("lineage", a), "lineage", "context") if a else EvidenceRef("", "lineage"),
                    EvidenceRef(_rid("lineage", b), "lineage", "context") if b else EvidenceRef("", "lineage"),
                ],
            )
        )
    fork = report.get("fork_lineage") or {}
    for dup in (fork.get("duplicate_blobs") or fork.get("duplicates") or [])[:20]:
        if not isinstance(dup, dict):
            continue
        paths = dup.get("paths") or []
        add(
            ProvenanceRecord(
                id=_rid("fork", dup.get("hash") or (paths[0] if paths else "dup")),
                kind="clone_link",
                path=paths[0] if paths else None,
                label="fork_duplicate",
                summary=str(dup.get("summary") or f"duplicate blob paths={paths[:4]}"),
                tags=["genetics", "fork"],
                payload=dup,
            )
        )


def build_provenance_ledger(report: dict[str, Any]) -> ProvenanceLedger:
    """Assemble a ledger from an EvolveReport.to_dict() (or analyze ctx)."""
    repo = str(report.get("repo") or report.get("local_path") or ".")
    records: list[ProvenanceRecord] = []
    by_path: dict[str, list[str]] = defaultdict(list)
    by_clade: dict[str, list[str]] = defaultdict(list)
    kinds: dict[str, int] = defaultdict(int)
    times: list[str] = []

    def add(rec: ProvenanceRecord) -> None:
        records.append(rec)
        kinds[rec.kind] += 1
        if rec.path:
            by_path[rec.path].append(rec.id)
        if rec.clade_id:
            by_clade[rec.clade_id].append(rec.id)
        if rec.when:
            times.append(rec.when)

    tax = report.get("taxonomy") or {}
    # Clades
    for c in tax.get("clades") or []:
        cid = str(c.get("id") or "")
        add(
            ProvenanceRecord(
                id=_rid("clade", cid),
                kind="clade",
                clade_id=cid,
                label=str(c.get("label") or cid),
                summary=(
                    f"clade {cid} layer={c.get('layer')} type={c.get('code_type')} "
                    f"files={c.get('file_count')} churn={c.get('churn')}"
                ),
                tags=["clade", str(c.get("layer") or ""), str(c.get("code_type") or "")],
                payload={
                    "layer": c.get("layer"),
                    "code_type": c.get("code_type"),
                    "type_path": c.get("type_path"),
                    "role": c.get("role"),
                    "file_count": c.get("file_count"),
                    "churn": c.get("churn"),
                },
            )
        )
        for p in (c.get("files") or [])[:40]:
            add(
                ProvenanceRecord(
                    id=_rid("code_type", p),
                    kind="code_type",
                    path=p,
                    clade_id=cid,
                    label=str(c.get("code_type") or c.get("label") or ""),
                    summary=f"{p} in {cid} typed {c.get('code_type')}",
                    tags=["path", "type"],
                    payload={"type_path": c.get("type_path"), "layer": c.get("layer")},
                    links=[EvidenceRef(_rid("clade", cid), "clade", "context")],
                )
            )

    # Allocations (capped but richer than report default for ledger build — use what's there)
    for a in (tax.get("allocations") or [])[:800]:
        path = str(a.get("path") or "")
        sha = str(a.get("sha") or "")
        cid = str(a.get("clade_id") or "")
        add(
            ProvenanceRecord(
                id=_rid("delta", sha[:10], path),
                kind="commit_delta",
                sha=sha,
                path=path,
                clade_id=cid,
                label=f"+{a.get('insertions')}/-{a.get('deletions')}",
                summary=f"delta {sha[:7]} → {path} ({cid})",
                tags=["delta", "allocation"],
                payload={
                    "insertions": a.get("insertions"),
                    "deletions": a.get("deletions"),
                    "lineage_id": a.get("lineage_id"),
                },
                links=[
                    EvidenceRef(_rid("clade", cid), "clade", "context") if cid else EvidenceRef("", "clade"),
                ],
            )
        )

    # Genetics lineages
    gen = report.get("genetics") or {}
    for lin in (gen.get("lineages") or gen.get("files") or [])[:300]:
        if not isinstance(lin, dict):
            continue
        path = str(lin.get("path") or "")
        cid = str(lin.get("clade_id") or "")
        add(
            ProvenanceRecord(
                id=_rid("lineage", path),
                kind="lineage",
                path=path,
                clade_id=cid or None,
                sha=str(lin.get("last_sha") or lin.get("first_sha") or "") or None,
                label=path,
                summary=(
                    f"lineage {path} first={str(lin.get('first_sha') or '')[:7]} "
                    f"last={str(lin.get('last_sha') or '')[:7]} fitness={lin.get('fitness')}"
                ),
                confidence=float(lin.get("fitness")) if lin.get("fitness") is not None else None,
                tags=["lineage"],
                payload={
                    "first_sha": lin.get("first_sha"),
                    "last_sha": lin.get("last_sha"),
                    "prior_paths": lin.get("prior_paths"),
                    "fitness": lin.get("fitness"),
                },
            )
        )

    # Ecology calibration
    eco = report.get("ecology") or {}
    cal = eco.get("calibration") or {}
    event_rows: list[Any] = []
    if isinstance(cal.get("events"), dict):
        event_rows = list(cal["events"].get("events") or [])
    elif isinstance(cal.get("events"), list):
        event_rows = cal["events"]
    for ev in event_rows:
        if not isinstance(ev, dict):
            continue
        eid = _rid("event", ev.get("kind"), ev.get("label"), (ev.get("when") or "")[:10])
        add(
            ProvenanceRecord(
                id=eid,
                kind="lifecycle_event",
                when=ev.get("when"),
                label=str(ev.get("label") or ev.get("kind")),
                summary=f"{ev.get('kind')} {ev.get('label')} → stage_hint={ev.get('stage_hint')}",
                confidence=ev.get("confidence"),
                tags=["event", str(ev.get("kind") or ""), str(ev.get("stage_hint") or "")],
                payload=ev,
            )
        )
    for cp in ((cal.get("changepoints") or {}).get("points") or []):
        if not isinstance(cp, dict):
            continue
        pid = _rid("cp", cp.get("series"), cp.get("when", "")[:10], cp.get("direction"))
        add(
            ProvenanceRecord(
                id=pid,
                kind="changepoint",
                when=cp.get("when"),
                label=f"{cp.get('series')}:{cp.get('direction')}",
                summary=(
                    f"changepoint {cp.get('series')} {cp.get('direction')} "
                    f"mag={cp.get('magnitude')} @ {cp.get('when')}"
                ),
                tags=["changepoint", str(cp.get("series") or "")],
                payload=cp,
            )
        )
    for seg in cal.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = _rid("seg", seg.get("stage"), (seg.get("start") or "")[:10])
        add(
            ProvenanceRecord(
                id=sid,
                kind="stage_segment",
                when=seg.get("start"),
                label=str(seg.get("label") or seg.get("stage")),
                summary=(
                    f"segment {seg.get('stage')} [{seg.get('start')} → {seg.get('end')}] "
                    f"via {seg.get('source')}"
                ),
                confidence=seg.get("confidence"),
                tags=["segment", str(seg.get("stage") or ""), str(seg.get("source") or "")],
                payload=seg,
            )
        )
    for anc in cal.get("anchors") or []:
        if not isinstance(anc, dict):
            continue
        ev = anc.get("event") or {}
        cp = anc.get("changepoint") or {}
        aid = _rid("anchor", ev.get("label"), anc.get("stage"))
        links = []
        if ev.get("label"):
            links.append(
                EvidenceRef(
                    _rid("event", ev.get("kind"), ev.get("label"), str(ev.get("when") or "")[:10]),
                    "lifecycle_event",
                    "supports",
                )
            )
        if cp.get("when"):
            links.append(
                EvidenceRef(
                    _rid("cp", cp.get("series"), str(cp.get("when") or "")[:10], cp.get("direction")),
                    "changepoint",
                    "supports",
                    note=f"delta_days={anc.get('delta_days')}",
                )
            )
        add(
            ProvenanceRecord(
                id=aid,
                kind="lifecycle_event",
                when=ev.get("when"),
                label=f"anchor:{ev.get('label')}→{anc.get('stage')}",
                summary=str(anc.get("rationale") or ""),
                confidence=anc.get("confidence"),
                tags=["anchor", str(anc.get("stage") or ""), str(ev.get("kind") or "")],
                payload=anc,
                links=links,
            )
        )

    # Hypotheses
    hyp = report.get("hypothesis_panel") or {}
    for claim in hyp.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        hid = _rid("hyp", claim.get("id"))
        add(
            ProvenanceRecord(
                id=hid,
                kind="hypothesis",
                label=str(claim.get("id") or ""),
                summary=str(claim.get("claim") or ""),
                confidence=claim.get("confidence"),
                tags=["hypothesis", str(claim.get("verdict") or "")],
                payload=claim,
            )
        )
    if hyp.get("stage_hypothesis"):
        sh = hyp["stage_hypothesis"]
        add(
            ProvenanceRecord(
                id=_rid("hyp", "stage"),
                kind="hypothesis",
                label="stage_hypothesis",
                summary=str(sh.get("claim") or ""),
                confidence=sh.get("confidence"),
                tags=["hypothesis", "stage", str(sh.get("verdict") or "")],
                payload=sh,
            )
        )

    # Next experiments
    ht = report.get("hierarchy_trends") or {}
    for ex in ht.get("next_experiments") or []:
        if not isinstance(ex, dict):
            continue
        xid = _rid("exp", ex.get("id"))
        add(
            ProvenanceRecord(
                id=xid,
                kind="experiment",
                label=str(ex.get("id") or ""),
                summary=str(ex.get("claim") or ""),
                tags=["experiment", str(ex.get("branch") or "")],
                payload=ex,
            )
        )

    # Failure points
    risk = report.get("risk") or {}
    for fp in risk.get("failure_points") or []:
        if not isinstance(fp, dict):
            continue
        fid = _rid("fp", fp.get("id"), fp.get("path"))
        add(
            ProvenanceRecord(
                id=fid,
                kind="failure_point",
                path=fp.get("path"),
                clade_id=fp.get("clade_id"),
                label=str(fp.get("title") or fp.get("id") or ""),
                summary=str(fp.get("title") or ""),
                confidence=None,
                tags=["risk", str(fp.get("severity") or ""), str(fp.get("kind") or "")],
                payload=fp,
            )
        )

    # Drift
    drift = report.get("drift") or {}
    for d in drift.get("clade_drift") or []:
        if not isinstance(d, dict):
            continue
        did = _rid("drift", d.get("clade_id"))
        add(
            ProvenanceRecord(
                id=did,
                kind="drift",
                clade_id=d.get("clade_id"),
                label=str(d.get("label") or d.get("clade_id")),
                summary=f"drift={d.get('drift')} on {d.get('clade_id')}",
                tags=["drift"],
                payload=d,
            )
        )

    # Signal confidence
    sig = report.get("signal_confidence") or {}
    for s in sig.get("signals") or sig.get("items") or []:
        if not isinstance(s, dict):
            continue
        name = str(s.get("signal") or s.get("name") or "")
        add(
            ProvenanceRecord(
                id=_rid("signal", name),
                kind="signal",
                label=name,
                summary=str(s.get("summary") or s.get("reliability") or name),
                confidence=s.get("confidence"),
                tags=["signal", str(s.get("reliability") or "")],
                payload=s,
            )
        )

    # Debt / coupling with proper kinds
    debt = report.get("debt") or {}
    if debt.get("score") is not None:
        add(
            ProvenanceRecord(
                id=_rid("signal", "debt_score"),
                kind="signal",
                label="debt_score",
                summary=f"debt score={debt.get('score')}",
                tags=["signal", "debt"],
                payload={"score": debt.get("score"), "summary": debt.get("summary")},
            )
        )
    for item in (debt.get("items") or debt.get("findings") or [])[:25]:
        if not isinstance(item, dict):
            continue
        pth = str(item.get("path") or item.get("file") or "")
        add(
            ProvenanceRecord(
                id=_rid("debt", pth or item.get("id") or item.get("kind")),
                kind="debt_item",
                path=pth or None,
                label=str(item.get("title") or item.get("kind") or "debt"),
                summary=str(item.get("summary") or item.get("message") or item.get("kind") or "debt"),
                tags=["debt", str(item.get("severity") or item.get("kind") or "")],
                payload=item,
            )
        )
    coupling = report.get("coupling") or {}
    for edge in (coupling.get("edges") or [])[:40]:
        if not isinstance(edge, dict):
            continue
        a = str(edge.get("a") or edge.get("src") or "")
        b = str(edge.get("b") or edge.get("dst") or "")
        add(
            ProvenanceRecord(
                id=_rid("couple", a, b),
                kind="coupling_edge",
                path=a or None,
                label=f"couple {a}↔{b}",
                summary=f"coupling weight={edge.get('weight')} kind={edge.get('kind')}",
                tags=["coupling", str(edge.get("kind") or "")],
                payload=edge,
                links=[
                    EvidenceRef(_rid("lineage", a), "lineage", "context") if a else EvidenceRef("", "lineage"),
                    EvidenceRef(_rid("lineage", b), "lineage", "context") if b else EvidenceRef("", "lineage"),
                ],
            )
        )

    _ingest_dynamics_and_process(report, add)
    _ingest_genetics_graph(report, add)
    _ingest_blast_and_micro(report, add)

    # Drop empty link stubs
    for r in records:
        r.links = [lk for lk in r.links if lk.record_id]

    frames = _build_frames(records, report)
    time_span = None
    if times:
        time_span = {"start": min(times), "end": max(times)}
    ledger = ProvenanceLedger(
        repo=repo,
        records=records,
        frames=frames,
        indexes={
            "kinds": dict(kinds),
            "by_path": {k: v[:40] for k, v in list(by_path.items())[:400]},
            "by_clade": {k: v[:40] for k, v in by_clade.items()},
            "time_span": time_span,
        },
        summary=(
            f"Provenance ledger: {len(records)} records, {len(frames)} deliberation frames; "
            f"kinds={dict(kinds)}"
        ),
    )
    return ledger


def _build_frames(records: list[ProvenanceRecord], report: dict[str, Any]) -> list[DeliberationFrame]:
    by_id = {r.id: r for r in records}
    frames: list[DeliberationFrame] = []

    hyp = report.get("hypothesis_panel") or {}
    for claim in hyp.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        hid = _rid("hyp", claim.get("id"))
        evidence = [EvidenceRef(hid, "hypothesis", "supports")]
        # Link stage segments / anchors when claim mentions stage or lehman
        cid = str(claim.get("id") or "")
        for r in records:
            if r.kind in {"stage_segment", "lifecycle_event", "changepoint"} and (
                cid.startswith("lehman") or "stage" in cid or r.tags
            ):
                if cid.startswith("lehman") and r.kind == "changepoint":
                    evidence.append(EvidenceRef(r.id, r.kind, "context"))
                elif "stage" in cid and r.kind in {"stage_segment", "lifecycle_event"}:
                    evidence.append(EvidenceRef(r.id, r.kind, "context"))
            if len(evidence) >= 8:
                break
        frames.append(
            DeliberationFrame(
                id=f"frame:{cid}",
                claim=str(claim.get("claim") or ""),
                stance=str(claim.get("verdict") or "open"),
                confidence=float(claim.get("confidence") or 0.0),
                evidence=evidence[:10],
                falsifier="; ".join(claim.get("caveats") or [])[:300],
                measure=str(claim.get("method") or ""),
                suggested_questions=[
                    f"What git evidence would flip verdict away from {claim.get('verdict')}?",
                    "Which lifecycle event most recently affected this claim?",
                ],
            )
        )

    ht = report.get("hierarchy_trends") or {}
    for ex in ht.get("next_experiments") or []:
        if not isinstance(ex, dict):
            continue
        xid = _rid("exp", ex.get("id"))
        evidence = [EvidenceRef(xid, "experiment", "measures")]
        branch = str(ex.get("branch") or "")
        for r in records:
            if r.kind in {"code_type", "clade"} and branch and branch in (r.label or r.summary or ""):
                evidence.append(EvidenceRef(r.id, r.kind, "context"))
            if r.kind in {"changepoint", "lifecycle_event"} and ex.get("id") in {
                "changepoint_persist",
                "security_disturbance",
                "event_anchor",
            }:
                evidence.append(EvidenceRef(r.id, r.kind, "supports"))
            if len(evidence) >= 8:
                break
        frames.append(
            DeliberationFrame(
                id=f"frame:exp:{ex.get('id')}",
                claim=str(ex.get("claim") or ""),
                stance="open",
                confidence=0.55,
                evidence=evidence[:10],
                falsifier=str(ex.get("falsifier") or ""),
                measure=str(ex.get("measure") or ""),
                suggested_questions=[
                    "Has the falsifier already occurred in the latest window?",
                    "What paths/clades should we re-measure?",
                ],
                context_clades=[branch] if branch.startswith("clade_") else [],
            )
        )

    for fp in (report.get("risk") or {}).get("failure_points") or []:
        if not isinstance(fp, dict):
            continue
        fid = _rid("fp", fp.get("id"), fp.get("path"))
        evidence = [EvidenceRef(fid, "failure_point", "supports")]
        path = str(fp.get("path") or "")
        cid = str(fp.get("clade_id") or "")
        if path and _rid("lineage", path) in by_id:
            evidence.append(EvidenceRef(_rid("lineage", path), "lineage", "context"))
        if cid:
            evidence.append(EvidenceRef(_rid("clade", cid), "clade", "context"))
        if path and _rid("blast", path) in by_id:
            evidence.append(EvidenceRef(_rid("blast", path), "blast_radius", "measures"))
        for r in records:
            if r.kind == "symbol" and r.path == path:
                evidence.append(EvidenceRef(r.id, "symbol", "context"))
            if r.kind == "cst_delta" and r.path == path:
                evidence.append(EvidenceRef(r.id, "cst_delta", "measures"))
            if len(evidence) >= 10:
                break
        frames.append(
            DeliberationFrame(
                id=f"frame:risk:{fp.get('id')}",
                claim=str(fp.get("title") or fp.get("id")),
                stance="risk",
                confidence=0.6 if fp.get("severity") in {"high", "critical"} else 0.45,
                evidence=evidence[:10],
                falsifier="Risk signal clears after targeted refactor without regressing coupling/reverts",
                measure=f"risk.failure_points[{fp.get('id')}]",
                suggested_questions=[
                    "What provenance deltas created this hotspot?",
                    "Does blast radius / CST delta justify containment before edit?",
                    "Is this clade heating or cooling?",
                ],
                context_paths=[path] if path else [],
                context_clades=[cid] if cid else [],
            )
        )

    # Global stage frame
    eco = report.get("ecology") or {}
    cal = eco.get("calibration") or {}
    if eco.get("global_stage"):
        evidence = []
        for r in records:
            is_anchor = "anchor" in (r.tags or [])
            if r.kind == "stage_segment" or (r.kind in {"lifecycle_event", "changepoint"} and is_anchor):
                evidence.append(EvidenceRef(r.id, r.kind, "supports"))
            elif r.kind == "lifecycle_event" and len(evidence) < 4:
                evidence.append(EvidenceRef(r.id, r.kind, "context"))
            if len(evidence) >= 8:
                break
        frames.insert(
            0,
            DeliberationFrame(
                id="frame:stage",
                claim=f"Repository ecological stage is {eco.get('global_stage')}",
                stance="weak" if (cal.get("method") == "heuristic_fallback") else "support",
                confidence=float(cal.get("confidence") or 0.4),
                evidence=evidence,
                falsifier="New major/security/revert_storm event or large opposing changepoint within 45 days",
                measure="ecology.calibration",
                suggested_questions=[
                    "Which anchor most justifies this stage?",
                    "Would typed-branch heating contradict maturity/consolidation?",
                ],
            ),
        )

    # Typed-branch heating/cooling frames
    for br in (ht.get("branch_trends") or [])[:8]:
        if not isinstance(br, dict):
            continue
        bid = str(br.get("type_key") or br.get("branch") or br.get("id") or "")
        if not bid:
            continue
        evidence = []
        for r in records:
            if r.kind in {"code_type", "clade", "commit_delta"} and (
                bid in (r.label or "") or bid in (r.summary or "") or bid in (r.path or "")
            ):
                evidence.append(EvidenceRef(r.id, r.kind, "supports"))
            if len(evidence) >= 6:
                break
        trend = str(br.get("trend") or "open")
        frames.append(
            DeliberationFrame(
                id=f"frame:branch:{bid}"[:120],
                claim=str(
                    br.get("narrative")
                    or f"Typed branch {bid} is {trend} (churn={br.get('churn')})"
                ),
                stance=trend,
                confidence=0.55 if trend in {"heating", "cooling"} else 0.4,
                evidence=evidence,
                falsifier="Churn direction reverses over next measurement window",
                measure="hierarchy_trends.branch_trends",
                suggested_questions=[
                    f"What lifecycle events coincide with {bid} {trend}?",
                    "Which lineages carry most of this branch's churn?",
                ],
                context_paths=[bid] if "/" in bid else [],
                context_clades=[bid] if bid.startswith("clade_") else [],
            )
        )

    # Basin occupancy frame
    basins = [r for r in records if r.kind == "regime_basin"]
    if basins:
        top = max(basins, key=lambda r: float(r.confidence or 0.0))
        traj = next((r for r in records if r.kind == "trajectory"), None)
        evidence = [EvidenceRef(top.id, "regime_basin", "supports")]
        if traj:
            evidence.append(EvidenceRef(traj.id, "trajectory", "measures"))
        for r in records:
            if r.kind == "state_sample":
                evidence.append(EvidenceRef(r.id, r.kind, "measures"))
            if len(evidence) >= 8:
                break
        frames.insert(
            0 if not any(f.id == "frame:stage" for f in frames) else 1,
            DeliberationFrame(
                id="frame:basin",
                claim=f"Trajectory occupies {top.label} basin (occupancy={top.confidence})",
                stance="insufficient" if "insufficient" in (traj.tags if traj else []) else "support",
                confidence=float(top.confidence or 0.4),
                evidence=evidence[:10],
                falsifier="Basin occupancy drops >25% relative or opposing changepoint within 45 days",
                measure="dynamics.basins",
                suggested_questions=[
                    "Is occupancy rising or falling over the last 6 months?",
                    "Which impulse responses pushed the trajectory toward this basin?",
                ],
            ),
        )

    # Impulse response frames
    for r in records:
        if r.kind != "impulse_response":
            continue
        frames.append(
            DeliberationFrame(
                id=f"frame:response:{r.label}"[:120],
                claim=r.summary or f"Impulse after {r.label}",
                stance="open",
                confidence=float(r.confidence or 0.5),
                evidence=[EvidenceRef(r.id, "impulse_response", "measures")],
                falsifier="Post-horizon state returns to pre-event mean within noise",
                measure="dynamics.impulses",
                suggested_questions=[
                    "Did instability rise faster than churn after this shock?",
                    "Is this response consistent with prior similar events?",
                ],
            )
        )
        if sum(1 for f in frames if f.id.startswith("frame:response:")) >= 6:
            break

    # Inter-report delta frame
    deltas = [r for r in records if r.kind == "report_delta"]
    if deltas:
        worse = [r for r in deltas if "worsened" in r.tags]
        better = [r for r in deltas if "improved" in r.tags]
        frames.append(
            DeliberationFrame(
                id="frame:delta:report",
                claim=(
                    f"Since previous report: {len(better)} improved, {len(worse)} worsened signals"
                ),
                stance="risk" if len(worse) > len(better) else ("support" if better else "open"),
                confidence=0.55,
                evidence=[EvidenceRef(r.id, "report_delta", "supports") for r in deltas[:8]],
                falsifier="Re-analyze with same window shows no material deltas",
                measure="diff",
                suggested_questions=[
                    "Which worsened signals share a common clade or path?",
                    "Did a lifecycle event land between the two reports?",
                ],
            )
        )

    # Selection pressure frame
    sel_signal = next((r for r in records if r.id == _rid("signal", "selection_pressure")), None)
    if sel_signal:
        issues = [r for r in records if r.kind == "selection_item" and "issue" in r.tags][:5]
        evidence = [EvidenceRef(sel_signal.id, "signal", "supports")]
        evidence.extend(EvidenceRef(i.id, "selection_item", "context") for i in issues)
        frames.append(
            DeliberationFrame(
                id="frame:selection",
                claim=sel_signal.summary,
                stance="risk" if (sel_signal.confidence or 0) >= 0.55 else "open",
                confidence=float(sel_signal.confidence or 0.4),
                evidence=evidence,
                falsifier="Open bug backlog and reopen-like rate fall while merge rate rises",
                measure="selection.pressure_score",
                suggested_questions=[
                    "Which open issues touch heating typed branches?",
                    "Are merged PRs acting as anti-regressive control?",
                ],
            )
        )

    # Enrich stage frame with trajectory measures
    for f in frames:
        if f.id != "frame:stage":
            continue
        for r in records:
            if r.kind in {"trajectory", "regime_basin", "state_sample"}:
                f.evidence.append(EvidenceRef(r.id, r.kind, "measures"))
            if len(f.evidence) >= 12:
                break

    # Dedup by id
    seen: set[str] = set()
    uniq: list[DeliberationFrame] = []
    for f in frames:
        if f.id in seen:
            continue
        seen.add(f.id)
        uniq.append(f)
    return uniq[:50]


def query_provenance(
    report_or_ledger: dict[str, Any] | ProvenanceLedger,
    **filters: Any,
) -> dict[str, Any]:
    """Query helper for CLI/API — accepts report dict or ledger."""
    if isinstance(report_or_ledger, ProvenanceLedger):
        ledger = report_or_ledger
    else:
        ledger = build_provenance_ledger(report_or_ledger)

    if filters.get("resolve"):
        return ledger.resolve(
            str(filters["resolve"]),
            depth=int(filters.get("depth") or 2),
        )
    if filters.get("frame"):
        expanded = ledger.expand_frame(str(filters["frame"]))
        return expanded or {"error": f"frame not found: {filters['frame']}", "frames": [f.id for f in ledger.frames]}
    if filters.get("timeline"):
        return {
            "summary": ledger.summary,
            "timeline": ledger.timeline(
                path=filters.get("path"),
                clade=filters.get("clade"),
                limit=int(filters.get("limit") or 60),
            ),
        }
    if filters.get("path_pack") or (filters.get("path") and filters.get("pack") and filters.get("path_only")):
        path = str(filters.get("path_pack") or filters.get("path") or "")
        return ledger.path_pack(path, clade=filters.get("clade"))
    if filters.get("pack"):
        return ledger.deliberation_pack(
            path=filters.get("path"),
            clade=filters.get("clade"),
            max_frames=int(filters.get("max_frames") or 12),
            max_records=int(filters.get("max_records") or 40),
        )
    rows = ledger.query(
        path=filters.get("path"),
        clade=filters.get("clade"),
        kind=filters.get("kind"),
        since=filters.get("since"),
        until=filters.get("until"),
        tag=filters.get("tag"),
        limit=int(filters.get("limit") or 80),
    )
    return {
        "summary": ledger.summary,
        "count": len(rows),
        "records": [r.to_dict() for r in rows],
        "frames": [f.to_dict() for f in ledger.frames[:15]],
        "indexes": ledger.to_dict().get("indexes"),
    }
