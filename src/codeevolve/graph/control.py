"""Working-memory bus: sense coalition, Soar-lite impasse, chunks, validity windows.

Honest scope: GWT/LIDA-style broadcast cap (~12 nodes), typed impasses, Park-style
recency×relevance×importance retrieval, agent-trace chunking. Not a cognitive-architecture
port, not GraphRAG, not Kumar P@5/MTT. Silent records stay insufficient.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codeevolve.graph.families import at_pivot, family_of, family_slice
from codeevolve.graph.model import ContextGraph, GraphNode, node_id
from codeevolve.graph.traverse import spreading_rank, steiner_join


COALITION_CAP = 12

IMPASSE_INSUFFICIENT = "insufficient"
IMPASSE_VERIFY_FAIL = "verify_fail"
IMPASSE_NO_GAIN = "accepted_no_gain"
IMPASSE_FENCE = "fence_refuse"
IMPASSE_PATH_TIE = "path_tie"


def window_open(node: GraphNode | dict[str, Any] | None) -> bool:
    """True when valid_to is unset. Expired windows are ignored by precedent/attention."""
    if node is None:
        return False
    if isinstance(node, GraphNode):
        return not bool(node.valid_to)
    return not bool(node.get("valid_to"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _age_decay(valid_from: str, *, tau_hours: float = 24.0) -> float:
    if not valid_from:
        return 1.0
    try:
        raw = str(valid_from).replace("Z", "+00:00")
        vf = datetime.fromisoformat(raw)
        now = datetime.now(vf.tzinfo or timezone.utc)
        hours = max(0.0, (now - vf).total_seconds() / 3600.0)
        return 1.0 / (1.0 + hours / max(1.0, tau_hours))
    except (TypeError, ValueError):
        return 1.0


def sense_graph_crossings(
    current: dict[str, Any] | None,
    previous: dict[str, Any] | Path | str | None,
    *,
    memory: Any = None,
    limit: int = 8,
) -> list[str]:
    """Surface delta crossings into cognition notes. Fail closed; never invent metrics."""
    if not current or previous is None:
        return []
    prev_r: dict[str, Any] | None
    if isinstance(previous, dict):
        prev_r = previous
    else:
        try:
            path = Path(previous)
            if not path.is_file():
                return []
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return []
        if not isinstance(loaded, dict):
            return []
        prev_r = loaded
    try:
        from codeevolve.graph.delta import delta_detect, proactive_surface

        host = ContextGraph(source="loop:sense")
        events = delta_detect(prev_r, current, into=host)
        surface = proactive_surface(host, limit=limit) if events else []
    except Exception:  # noqa: BLE001 — fail closed
        return []
    rows = surface or events[: max(1, limit)]
    notes: list[str] = []
    for row in rows[: max(1, limit)]:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "")
        label = str(row.get("label") or "")
        tag = label if kind in {"", "delta"} else kind
        text = str(row.get("text") or "")
        if not tag and not text:
            continue
        notes.append(f"graph-sense {tag or 'delta'}: {text}".strip())
    if memory is not None and notes:
        try:
            memory.add(
                "graph crossings: " + "; ".join(notes[:6]),
                kind="working",
                tags=["graph", "sense", "delta"],
                score=1.2,
                meta={"graph_ids": [str(r.get("id") or "") for r in rows[:6] if isinstance(r, dict)]},
            )
        except Exception:  # noqa: BLE001
            pass
    return notes


def sense_note_from_output(output: Any) -> str:
    """Working-memory line from graph_search output. Empty → insufficient."""
    if not isinstance(output, dict):
        return "graph_search: insufficient"
    hits = [h for h in (output.get("hits") or []) if isinstance(h, dict)]
    if not hits and not output.get("flow") and not output.get("precedent") and not output.get("delta"):
        if int(output.get("node_count") or 0) == 0:
            return "graph_search: insufficient"
    ids = [str(h.get("id") or h.get("label") or "") for h in hits[:8]]
    ids = [x for x in ids if x]
    fams = sorted({str(h.get("family") or family_of(str(h.get("kind") or ""))) for h in hits if h.get("kind") or h.get("family")})
    pivots = [str(h.get("id") or "") for h in hits if str(h.get("kind") or "") == "pivot"][:4]
    flow = output.get("flow") if isinstance(output.get("flow"), dict) else {}
    flow_sum = str(flow.get("summary") or "")
    bits = [f"graph:{len(hits)} hits"]
    if ids:
        bits.append("[" + ",".join(ids) + "]")
    if fams:
        bits.append("family=" + ",".join(fams[:4]))
    if pivots:
        bits.append("pivot=" + ",".join(x for x in pivots if x))
    if flow_sum:
        bits.append("flow=" + flow_sum[:80])
    if not hits and not flow_sum:
        bits.append("insufficient")
    return " ".join(bits)


def coalition_pack(
    graph: ContextGraph,
    *,
    hits: list[dict[str, Any]] | None = None,
    path: str | None = None,
    last_decision: str | None = None,
    frame_ids: list[str] | None = None,
    limit: int = COALITION_CAP,
) -> dict[str, Any]:
    """Broadcast one ~12-node pack (attention_rank + steiner + knowledge + propose). Fail closed."""
    cap = max(4, min(int(limit), COALITION_CAP))
    ids: list[str] = []
    cited: list[str] = [str(f) for f in (frame_ids or []) if f]
    for h in hits or []:
        hid = str(h.get("id") or "") if isinstance(h, dict) else str(h)
        if hid and hid in graph.nodes and window_open(graph.nodes[hid]):
            ids.append(hid)
        if hid.startswith("frame:") or (isinstance(h, dict) and str(h.get("kind") or "") == "frame"):
            cited.append(hid)
    if path:
        pid = path if str(path).startswith("path:") else node_id("path", path)
        if pid in graph.nodes:
            ids.append(pid)
    ranked = attention_rank(
        graph,
        path=path,
        frame_ids=cited,
        last_decision=last_decision,
        hops=3,
        per_family=4,
        limit=cap,
    )
    for row in ranked:
        rid = str(row.get("id") or "")
        if rid and rid in graph.nodes and window_open(graph.nodes[rid]):
            ids.append(rid)
    ids = list(dict.fromkeys(ids))
    connected = steiner_join(graph, ids[:8], max_nodes=cap) if ids else {"nodes": [], "count": 0}
    node_ids = [str(n) for n in (connected.get("nodes") or []) if n in graph.nodes][:cap]
    know = family_slice(graph, "knowledge", max_nodes=cap)
    for n in know.nodes.values():
        if window_open(n) and n.id not in node_ids:
            node_ids.append(n.id)
        if len(node_ids) >= cap:
            break
    propose_rows = at_pivot(graph, "propose", limit=4)
    for row in propose_rows:
        pid = str((row.get("pivot") or {}).get("id") or row.get("id") or "")
        if pid and pid in graph.nodes and pid not in node_ids:
            node_ids.append(pid)
        for nid in (row.get("nodes") or [])[:4]:
            sid = str(nid.get("id") if isinstance(nid, dict) else nid)
            if sid in graph.nodes and sid not in node_ids:
                node_ids.append(sid)
        if len(node_ids) >= cap:
            break
    node_ids = node_ids[:cap]
    if not node_ids:
        return {
            "node_ids": [],
            "frame_ids": [],
            "decision_ids": [],
            "falsifiers": [],
            "allowed_because": [],
            "overridden": [],
            "insufficient": True,
            "stance": "insufficient",
            "count": 0,
            "attention": ranked[:cap],
        }
    frames: list[str] = []
    decisions: list[str] = []
    falsifiers: list[str] = []
    allowed: list[str] = []
    overridden: list[str] = []
    for nid in node_ids:
        n = graph.nodes[nid]
        if n.kind == "frame":
            frames.append(nid)
            fals = n.meta.get("falsifier")
            if fals:
                falsifiers.append(str(fals)[:240])
        if n.kind == "decision":
            decisions.append(nid)
        for e in graph.out_edges(nid, "allowed_because") + graph.in_edges(nid, "allowed_because"):
            other = e.target if e.source == nid else e.source
            allowed.append(other)
        for e in graph.out_edges(nid, "overridden") + graph.in_edges(nid, "overridden"):
            other = e.target if e.source == nid else e.source
            overridden.append(other)
        if n.kind == "record" and "falsifier" in (n.label or "").lower():
            falsifiers.append(n.text[:240] or n.id)
    return {
        "node_ids": node_ids,
        "frame_ids": list(dict.fromkeys(frames))[:8],
        "decision_ids": list(dict.fromkeys(decisions))[:8],
        "falsifiers": list(dict.fromkeys(x for x in falsifiers if x))[:6],
        "allowed_because": list(dict.fromkeys(allowed))[:8],
        "overridden": list(dict.fromkeys(overridden))[:8],
        "insufficient": False,
        "stance": "support",
        "count": len(node_ids),
        "connected": {"count": connected.get("count"), "seed": connected.get("seed")},
        "attention": ranked[:cap],
    }


def classify_impasse(
    round_result: dict[str, Any] | None,
    *,
    coalition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Soar-lite typed impasse. Does not port chunking language."""
    empty_coalition = bool(coalition and coalition.get("insufficient"))
    if round_result is None:
        return {
            "type": IMPASSE_INSUFFICIENT,
            "kernel": "investigate",
            "spawn": True,
            "precedent": False,
            "objective": None,
        }
    prop = round_result.get("proposal") if isinstance(round_result.get("proposal"), dict) else {}
    notes = " ".join(str(x) for x in (round_result.get("notes") or [])).lower()
    stance = str((prop or {}).get("stance") or "").lower()
    if stance == "insufficient" or "stance=insufficient" in notes or empty_coalition:
        return {"type": IMPASSE_INSUFFICIENT, "kernel": "investigate", "spawn": True, "precedent": False, "objective": None}
    if round_result.get("verify_ok") is False or "verify/tests failed" in notes or "verify failed" in notes:
        return {"type": IMPASSE_VERIFY_FAIL, "kernel": "stabilize", "spawn": True, "precedent": False, "objective": None}
    if "refused apply" in notes or "refused apply:" in notes or ("blast" in notes and "refuse" in notes):
        return {
            "type": IMPASSE_FENCE,
            "kernel": "stabilize",
            "spawn": True,
            "precedent": False,
            "objective": "stabilize_path",
        }
    score_after = round_result.get("score_after") if isinstance(round_result.get("score_after"), dict) else {}
    if round_result.get("accepted") and score_after.get("improved") is False:
        return {"type": IMPASSE_NO_GAIN, "kernel": "contain", "spawn": True, "precedent": False, "objective": None}
    paths = [p for p in (prop or {}).get("paths") or [] if p]
    edits = (prop or {}).get("edits") or (prop or {}).get("edit_previews") or []
    if len(paths) >= 2 and not edits:
        return {"type": IMPASSE_PATH_TIE, "kernel": None, "spawn": False, "precedent": True, "objective": None}
    return {"type": "", "kernel": None, "spawn": False, "precedent": False, "objective": None}


def should_escalate_llm(
    coalition: dict[str, Any] | None,
    impasse: dict[str, Any] | None,
    last_round: dict[str, Any] | None,
) -> bool:
    """System-1 heuristic unless coalition empty, impasse typed, or last round overridden."""
    if not coalition or coalition.get("insufficient") or not coalition.get("node_ids"):
        return True
    if impasse and impasse.get("type"):
        return True
    if last_round:
        notes = " ".join(str(x) for x in (last_round.get("notes") or [])).lower()
        if last_round.get("verify_ok") is False or "rolled back" in notes:
            return True
        prop = last_round.get("proposal") if isinstance(last_round.get("proposal"), dict) else {}
        if str((prop or {}).get("backend") or "").find("overridden") >= 0:
            return True
    return False


def attention_rank(
    graph: ContextGraph,
    *,
    path: str | None = None,
    frame_ids: list[str] | None = None,
    last_decision: str | None = None,
    hops: int = 3,
    per_family: int = 4,
    limit: int = COALITION_CAP,
) -> list[dict[str, Any]]:
    """Spreading attention from path + cited frames + last decision. Caps per family; skips expired."""
    seeds: dict[str, float] = {}
    if path:
        pid = path if str(path).startswith("path:") else node_id("path", path)
        if pid in graph.nodes:
            seeds[pid] = 1.0
        for n in graph.by_kind("path"):
            if path in n.id or n.label == path:
                seeds[n.id] = 1.0
    for fid in frame_ids or []:
        fn = fid if str(fid).startswith("frame:") else node_id("frame", fid)
        if fn in graph.nodes:
            seeds[fn] = 1.0
    if last_decision and last_decision in graph.nodes:
        seeds[last_decision] = 1.2
    if not seeds:
        return []
    ranks = spreading_rank(graph, seeds, iterations=max(2, hops), decay=0.5, max_nodes=80)
    scored: list[tuple[float, GraphNode]] = []
    for nid, sc in ranks.items():
        n = graph.nodes.get(nid)
        if not n or not window_open(n):
            continue
        scored.append((float(sc) * _age_decay(n.valid_from), n))
    scored.sort(key=lambda x: -x[0])
    by_fam: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for sc, n in scored:
        fam = n.family or family_of(n.kind) or n.kind
        by_fam[fam] = by_fam.get(fam, 0) + 1
        if by_fam[fam] > max(1, per_family):
            continue
        row = n.to_dict()
        row["attention"] = round(sc, 4)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def close_validity_windows(
    graph: ContextGraph,
    *,
    paths: list[str] | None = None,
    frame_ids: list[str] | None = None,
    now: str | None = None,
    except_id: str | None = None,
) -> list[str]:
    """Set valid_to on prior decision/context/fence nodes sharing path or frame."""
    ts = now or _now()
    closed: list[str] = []
    path_keys = {str(p) for p in (paths or []) if p}
    path_keys.update(node_id("path", p) for p in list(path_keys))
    frame_keys = {str(f) for f in (frame_ids or []) if f}
    kinds = ("decision", "context", "fence", "focus")
    for kind in kinds:
        for n in graph.by_kind(kind):
            if except_id and n.id == except_id:
                continue
            if n.valid_to:
                continue
            blob = n.blob()
            hit = any(k.lower() in blob or k in n.id for k in path_keys) or any(
                k.lower() in blob or k in n.id for k in frame_keys
            )
            if not hit:
                continue
            n.valid_to = ts
            closed.append(n.id)
    return closed


def persist_closed_windows(
    out_dir: Path | str | None,
    closed_ids: list[str],
    *,
    now: str | None = None,
) -> None:
    """Append valid_to onto decisions.jsonl (append-only). Fail closed."""
    if not out_dir or not closed_ids:
        return
    from codeevolve.graph.store import graph_dir, write_pivot

    ts = now or _now()
    dest = graph_dir(out_dir)
    for cid in closed_ids[:40]:
        if not str(cid).startswith("decision:"):
            continue
        write_pivot(
            None,
            {"id": cid, "kind": "decision", "valid_to": ts, "ts": ts, "source": "agent.window_close"},
            dest,
        )


def chunk_from_traces(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compile fence/blast preferences from repeated (path, frame_ids, outcome). Agent traces only."""
    counts: dict[tuple[Any, ...], int] = {}
    samples: dict[tuple[Any, ...], dict[str, Any]] = {}
    for d in decisions:
        if not isinstance(d, dict):
            continue
        if str(d.get("source") or "").startswith("report.phylogeny"):
            continue
        paths = tuple(sorted(str(p) for p in (d.get("paths") or []) if p))
        frames = tuple(sorted(str(f) for f in (d.get("frame_ids") or []) if f))
        outcome = str(d.get("outcome") or "")
        if not paths or not outcome:
            continue
        key = (paths, frames, outcome)
        counts[key] = counts.get(key, 0) + 1
        samples[key] = d
    prefs: list[dict[str, Any]] = []
    for key, n in counts.items():
        if n < 2:
            continue
        paths, frames, outcome = key
        if outcome in {"overridden", "refused"}:
            pref = "refuse_blast"
        elif outcome in {"applied", "dry-run", "allowed"}:
            pref = "prefer_fence"
        else:
            continue
        prefs.append(
            {
                "id": node_id("preference", pref, paths[0] if paths else "any"),
                "kind": "policy",
                "preference": pref,
                "paths": list(paths),
                "frame_ids": list(frames),
                "outcome": outcome,
                "count": n,
                "source": "agent.chunk",
                "stance": "support",
                "text": f"{pref} after {n}× ({outcome}) on {','.join(paths[:4])}",
            }
        )
    return prefs


def ingest_chunks(graph: ContextGraph, prefs: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for pref in prefs:
        nid = str(pref.get("id") or "")
        if not nid:
            continue
        graph.add_node(
            nid,
            "policy",
            label=str(pref.get("preference") or "preference"),
            stage="deliberate",
            family="knowledge",
            text=str(pref.get("text") or ""),
            source="agent.chunk",
            confidence=min(0.9, 0.4 + 0.1 * int(pref.get("count") or 2)),
            meta={"count": pref.get("count"), "paths": pref.get("paths"), "frame_ids": pref.get("frame_ids")},
        )
        ids.append(nid)
        for fid in (pref.get("frame_ids") or [])[:4]:
            fn = fid if str(fid).startswith("frame:") else node_id("frame", fid)
            graph.add_node(fn, "frame", label=str(fid), stage="deliberate", family="knowledge")
            graph.add_edge(nid, fn, "cites")
    return ids


def write_failure_reflection(
    graph: ContextGraph | None,
    rnd: dict[str, Any],
    *,
    memory: Any = None,
    out_dir: Path | str | None = None,
) -> str | None:
    """Episodic note + reflection node linked overridden / falsified_by. Next sense can retrieve it."""
    notes = " ".join(str(x) for x in (rnd.get("notes") or [])).lower()
    verify_fail = rnd.get("verify_ok") is False
    rolled = "rolled back" in notes or "rollback" in notes
    if not verify_fail and not rolled:
        return None
    index = int(rnd.get("index") or 0)
    rid = node_id("reflect", "fail", index)
    prop = rnd.get("proposal") if isinstance(rnd.get("proposal"), dict) else {}
    text = "; ".join(str(x) for x in (rnd.get("notes") or [])[:6]) or "verify/rollback failure"
    if memory is not None:
        try:
            memory.add(
                f"reflexion overridden: {text[:400]}",
                kind="episodic",
                tags=["overridden", "graph", "reflexion", "falsified"],
                score=1.8,
                meta={
                    "outcome": "overridden",
                    "graph_ids": [rid],
                    "frame_ids": list((prop or {}).get("frame_ids") or []),
                },
            )
        except Exception:  # noqa: BLE001
            pass
    if graph is not None:
        graph.add_node(
            rid,
            "reflection",
            label="reflect:overridden",
            stage="deliberate",
            family="decision",
            text=text[:300],
            source="agent.reflexion",
            confidence=0.7,
            meta={"outcome": "overridden", "round": index},
        )
        did = node_id("decision", index)
        if did not in graph.nodes:
            graph.add_node(did, "decision", label="decision:overridden", stage="deliberate", family="decision")
        graph.add_edge(rid, did, "overridden")
        for fid in (prop or {}).get("frame_ids") or []:
            fn = fid if str(fid).startswith("frame:") else node_id("frame", fid)
            graph.add_node(fn, "frame", label=str(fid), stage="deliberate", family="knowledge")
            graph.add_edge(rid, fn, "falsified_by")
    if out_dir is not None:
        from codeevolve.graph.store import write_pivot

        write_pivot(
            graph,
            {
                "id": rid,
                "kind": "pivot",
                "pivot_type": "rollback",
                "stage": "verify",
                "label": "reflect:overridden",
                "text": text[:240],
                "round": index,
                "source": "agent.reflexion",
                "decision": node_id("decision", index),
            },
            out_dir,
        )
    return rid


def merge_live_reflections(host: ContextGraph, live: ContextGraph | None) -> int:
    """Copy in-memory reflection nodes (overridden / falsified_by) so next sense sees them."""
    if live is None or live is host:
        return 0
    copied = 0
    for node in live.by_kind("reflection"):
        if node.id not in host.nodes:
            host.add_node(
                node.id,
                node.kind,
                label=node.label,
                stage=node.stage,
                family=node.family,
                text=node.text,
                source=node.source,
                confidence=node.confidence,
                meta=dict(node.meta),
            )
            copied += 1
        for e in list(live.out_edges(node.id)) + list(live.in_edges(node.id)):
            if e.rel not in {"overridden", "falsified_by"}:
                continue
            other = e.target if e.source == node.id else e.source
            on = live.nodes.get(other)
            if on is not None and other not in host.nodes:
                host.add_node(
                    on.id,
                    on.kind,
                    label=on.label,
                    stage=on.stage,
                    family=on.family,
                    text=on.text,
                    source=on.source,
                    meta=dict(on.meta),
                )
            host.add_edge(e.source, e.target, e.rel)
    return copied
