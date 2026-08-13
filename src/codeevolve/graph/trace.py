"""Decision traces and coding-pivot nodes built from agent rounds."""

from __future__ import annotations

from typing import Any

from codeevolve.graph.families import PIVOT_TYPES, join_families
from codeevolve.graph.model import ContextGraph, node_id
from codeevolve.graph.policy import AUTHORITY_ID, claim_id, decision_rel, outcome_from_round, policy_for_outcome


def ingest_round_traces(
    g: ContextGraph,
    rnd: dict[str, Any],
    *,
    index: int,
    round_id: str,
) -> str:
    """Create decision + pivots for one round; join family neighborhoods. Returns decision id."""
    prop = rnd.get("proposal") if isinstance(rnd.get("proposal"), dict) else {}
    stance = str((prop or {}).get("stance") or "")
    outcome = outcome_from_round(rnd)
    did = node_id("decision", index)
    g.add_node(
        did,
        "decision",
        label=f"decision:{outcome}",
        stage="deliberate",
        family="decision",
        text=str((prop or {}).get("summary") or rnd.get("step_id") or "")[:300],
        source="report.agent.round" if not rnd.get("cognition") else "agent.round",
        confidence=0.7 if stance and stance != "insufficient" else 0.4,
        authority=AUTHORITY_ID,
        meta={"outcome": outcome, "stance": stance, "round": index, "accepted": rnd.get("accepted")},
    )
    g.add_edge(round_id, did, "proposed")
    rel = decision_rel(outcome)
    frame_ids = list((prop or {}).get("frame_ids") or [])
    for fid in frame_ids:
        fn = fid if str(fid).startswith("frame:") else node_id("frame", fid)
        g.add_node(fn, "frame", label=str(fid), stage="deliberate", family="knowledge")
        g.add_edge(did, fn, rel)
        g.add_edge(did, fn, "cites")
        cid = claim_id(fn)
        claim_text = str((prop or {}).get("claim") or "")
        if claim_text or fn in g.nodes:
            g.add_node(
                cid,
                "claim",
                label=str(fid),
                stage="deliberate",
                family="knowledge",
                text=claim_text or str(g.nodes[fn].text if fn in g.nodes else ""),
                source="frame",
            )
            g.add_edge(fn, cid, "cites")
        fals = g.nodes[fn].meta.get("falsifier") if fn in g.nodes else None
        if fals:
            rid = node_id("record", "falsifier", fid)
            g.add_node(rid, "record", label="falsifier", stage="deliberate", family="knowledge", text=str(fals))
            g.add_edge(fn, rid, "falsified_by")
    for pid in policy_for_outcome(outcome, stance):
        if pid in g.nodes:
            g.add_edge(did, pid, rel)
            g.add_edge(did, pid, "constrained_by")
    if AUTHORITY_ID in g.nodes:
        g.add_edge(did, AUTHORITY_ID, "constrained_by")

    pid_prop = node_id("proposal", index)
    if pid_prop in g.nodes:
        g.add_edge(did, pid_prop, "precedes")
        g.add_edge(did, pid_prop, rel)

    sid = node_id("score", index)
    if sid in g.nodes:
        g.add_edge(did, sid, "scored")

    paths = []
    for prev in (prop or {}).get("edit_previews") or []:
        if isinstance(prev, dict) and prev.get("path"):
            paths.append(str(prev["path"]))
    cog = rnd.get("cognition") if isinstance(rnd.get("cognition"), dict) else {}
    refl = cog.get("reflection") if isinstance(cog.get("reflection"), dict) else {}
    focus = str(refl.get("next_focus") or (paths[0] if paths else ""))
    kernels = list(refl.get("spawn_kernels") or [])

    joins: list[str] = [did, *frame_ids]
    joins.extend(node_id("path", p) for p in paths[:8])
    if focus:
        joins.append(node_id("path", focus))
        fid_focus = node_id("focus", index)
        g.add_node(fid_focus, "focus", label=focus, stage="sense", family="context", text=focus)
        g.add_node(node_id("path", focus), "path", label=focus, stage="context", family="taxon")
        g.add_edge(fid_focus, node_id("path", focus), "focuses")
        joins.append(fid_focus)
    if paths:
        fence_id = node_id("fence", index)
        g.add_node(
            fence_id,
            "fence",
            label="path-fence",
            stage="act",
            family="context",
            text=",".join(paths[:8]),
            source="agent.round",
        )
        if "policy:path-fence" in g.nodes:
            g.add_edge(fence_id, "policy:path-fence", "fenced_by")
        for p in paths[:8]:
            g.add_node(node_id("path", p), "path", label=p, stage="context", family="taxon")
            g.add_edge(fence_id, node_id("path", p), "fenced_by")
        joins.append(fence_id)

    notes = " ".join(str(x) for x in (rnd.get("notes") or [])).lower()
    specs: list[tuple[str, str, str]] = [
        ("choose_path", "sense", focus or ",".join(paths[:3])),
        ("propose", "deliberate", str((prop or {}).get("summary") or stance)),
        ("apply_or_dry_run", "act", outcome),
        ("score", "verify", str((rnd.get("score_after") or {}).get("summary") or "")),
    ]
    if kernels:
        specs.append(("spawn", "act", ",".join(str(k) for k in kernels)))
    if "rolled back" in notes or outcome == "overridden":
        specs.append(("rollback", "verify", "rollback"))
    if cog.get("rag") or any(
        (r.get("result") or r).get("name") == "rag_query"
        for r in ((cog.get("actions") or {}).get("results") or [])
        if isinstance(r, dict)
    ):
        specs.append(("sense", "sense", "rag"))
    if refl:
        specs.append(("deliberate", "deliberate", str(refl.get("stance") or "")))

    prev_pivot = ""
    for ptype, stage, text in specs:
        if ptype not in PIVOT_TYPES and ptype not in {"sense", "deliberate", "act", "verify"}:
            continue
        pid = node_id("pivot", index, ptype)
        g.add_node(
            pid,
            "pivot",
            label=ptype,
            stage=stage,
            family="pivot",
            text=str(text)[:240],
            source="agent.round",
            confidence=0.6,
            authority=AUTHORITY_ID,
            meta={"pivot_type": ptype, "round": index},
        )
        g.add_edge(round_id, pid, "pivots")
        join_families(g, pid, joins)
        if did in g.nodes:
            g.add_edge(pid, did, "joins")
        if prev_pivot:
            g.add_edge(prev_pivot, pid, "next_pivot")
        prev_pivot = pid
        if ptype == "spawn":
            for k in kernels[:6]:
                kid = node_id("kernel", k)
                g.add_node(kid, "kernel", label=str(k), stage="deliberate", family="flow")
                g.add_edge(pid, kid, "joins")
    return did


def ingest_flow_pivots(g: ContextGraph, *, parent: str, index: str = "cycle") -> None:
    """Stage pivots for a cognition cycle (sense→deliberate→act→verify)."""
    prev = ""
    for stage in ("sense", "deliberate", "act", "verify"):
        pid = node_id("pivot", index, stage)
        g.add_node(
            pid,
            "pivot",
            label=stage,
            stage=stage,
            family="pivot",
            text=stage,
            source="agent.cognition",
            meta={"pivot_type": stage},
        )
        if parent in g.nodes:
            g.add_edge(parent, pid, "pivots")
        if prev:
            g.add_edge(prev, pid, "next_pivot")
        prev = pid
        for n in g.nodes.values():
            if n.stage == stage and n.kind != "pivot":
                g.add_edge(pid, n.id, "joins")
                if n.kind in {"rag", "morpheme", "memory", "tool", "kernel", "reflection", "score", "test"}:
                    if sum(1 for e in g.out_edges(pid, "joins")) >= 12:
                        break
