"""Live write-back of decision/pivot traces into `.codeevolve/graph/`."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codeevolve.graph.model import ContextGraph, node_id
from codeevolve.graph.policy import decision_rel, outcome_from_round, policy_for_outcome


def graph_dir(out_dir: Path | str | None) -> Path:
    root = Path(out_dir) if out_dir else Path(".codeevolve")
    if root.name == "graph":
        return root
    if root.name == "agent":
        return root.parent / "graph"
    return root / "graph"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def write_pivot(
    graph: ContextGraph | None,
    event: dict[str, Any],
    out_dir: Path | str | None,
) -> dict[str, Any]:
    """Append a pivot (and optional decision) so the next parse sees traces."""
    dest = graph_dir(out_dir)
    row = dict(event)
    row.setdefault("ts", _now())
    kind = str(row.get("kind") or "pivot")
    if kind == "decision":
        _append_jsonl(dest / "decisions.jsonl", row)
        if graph is not None:
            _materialize_decision(graph, row)
    else:
        row["kind"] = "pivot"
        _append_jsonl(dest / "pivots.jsonl", row)
        if graph is not None:
            _materialize_pivot(graph, row)
    return {"ok": True, "dir": str(dest), "id": row.get("id"), "kind": kind}


def write_round_traces(
    rnd: dict[str, Any],
    *,
    out_dir: Path | str | None,
    report: dict[str, Any] | None = None,
    graph: ContextGraph | None = None,
) -> list[dict[str, Any]]:
    """Write decision + coding-pivot events for one agent round."""
    index = int(rnd.get("index") or 0)
    ts = _now()
    outcome = outcome_from_round(rnd)
    prop = rnd.get("proposal") if isinstance(rnd.get("proposal"), dict) else {}
    stance = str((prop or {}).get("stance") or "")
    frames = list((prop or {}).get("frame_ids") or [])
    paths = []
    for prev in (prop or {}).get("edit_previews") or []:
        if isinstance(prev, dict) and prev.get("path"):
            paths.append(str(prev["path"]))
    cog = rnd.get("cognition") if isinstance(rnd.get("cognition"), dict) else {}
    refl = cog.get("reflection") if isinstance(cog.get("reflection"), dict) else {}
    focus = str(refl.get("next_focus") or (paths[0] if paths else "") or "")
    kernels = list(refl.get("spawn_kernels") or [])
    joins = [f if str(f).startswith("frame:") else node_id("frame", f) for f in frames]
    joins.extend(node_id("path", p) for p in paths[:8])
    if focus:
        joins.append(node_id("path", focus))
    joins.extend(node_id("kernel", k) for k in kernels[:6])
    joins.extend(policy_for_outcome(outcome, stance))
    eco = (report or {}).get("ecology") or {}
    if eco.get("global_stage"):
        joins.append("window:ecology")

    decision = {
        "id": node_id("decision", index),
        "kind": "decision",
        "label": f"decision:{outcome}",
        "text": str((prop or {}).get("summary") or rnd.get("step_id") or "")[:300],
        "round": index,
        "stance": stance,
        "outcome": outcome,
        "accepted": rnd.get("accepted"),
        "applied": rnd.get("applied"),
        "frame_ids": frames,
        "paths": paths,
        "joins": joins,
        "source": "agent.round",
        "confidence": 0.7 if stance and stance != "insufficient" else 0.4,
        "authority": "authority:codeevolve",
        "valid_from": ts,
        "rel": decision_rel(outcome),
        "ts": ts,
        "impasse": rnd.get("impasse") if isinstance(rnd.get("impasse"), dict) else {},
    }
    written = [write_pivot(graph, decision, out_dir)]

    try:
        from codeevolve.graph.control import (
            chunk_from_traces,
            close_validity_windows,
            ingest_chunks,
            persist_closed_windows,
        )
        from codeevolve.graph.parse import parse_context

        host = graph if graph is not None else parse_context(agent_dir=out_dir, report=report)
        closed = close_validity_windows(
            host,
            paths=paths,
            frame_ids=frames,
            now=ts,
            except_id=str(decision["id"]),
        )
        persist_closed_windows(out_dir, closed, now=ts)
        store_rows = (load_graph_store(out_dir).get("decisions") or []) if out_dir else [decision]
        prefs = chunk_from_traces(store_rows)
        ingest_chunks(host, prefs)
        for pref in prefs:
            written.append(
                write_pivot(
                    host,
                    {**pref, "kind": "pivot", "pivot_type": "preference", "label": pref.get("preference")},
                    out_dir,
                )
            )
    except Exception:  # noqa: BLE001 — fail closed
        pass

    pivot_specs = [
        ("choose_path", "sense", focus or ",".join(paths[:3]), paths),
        ("propose", "deliberate", str((prop or {}).get("summary") or stance), frames),
        ("apply_or_dry_run", "act", outcome, []),
        ("score", "verify", str((rnd.get("score_after") or {}).get("summary") or ""), []),
    ]
    if kernels:
        pivot_specs.append(("spawn", "act", ",".join(str(k) for k in kernels), kernels))
    notes = " ".join(str(x) for x in (rnd.get("notes") or [])).lower()
    if "rolled back" in notes or outcome == "overridden":
        pivot_specs.append(("rollback", "verify", "rollback", []))

    prev_pid = ""
    for ptype, stage, text, extra in pivot_specs:
        pid = node_id("pivot", index, ptype)
        ev = {
            "id": pid,
            "kind": "pivot",
            "pivot_type": ptype,
            "stage": stage,
            "label": ptype,
            "text": str(text)[:240],
            "round": index,
            "joins": list(dict.fromkeys(joins + [node_id("path", x) if "/" in str(x) or str(x).endswith(".py") else str(x) for x in extra])),
            "decision": decision["id"],
            "source": "agent.round",
            "confidence": decision["confidence"],
            "authority": "authority:codeevolve",
            "valid_from": ts,
            "prev": prev_pid,
            "ts": ts,
        }
        written.append(write_pivot(graph, ev, out_dir))
        prev_pid = pid
    return written


def load_graph_store(path: Path | str | None) -> dict[str, list[dict[str, Any]]]:
    dest = graph_dir(path) if path else None
    out: dict[str, list[dict[str, Any]]] = {"decisions": [], "pivots": []}
    if dest is None or not dest.is_dir():
        return out
    for key, name in (("decisions", "decisions.jsonl"), ("pivots", "pivots.jsonl")):
        fp = dest / name
        if not fp.is_file():
            continue
        try:
            for line in fp.read_text(encoding="utf-8").splitlines()[:400]:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    out[key].append(row)
        except (OSError, json.JSONDecodeError):
            continue
    return out


def ingest_store(g: ContextGraph, store: dict[str, list[dict[str, Any]]]) -> None:
    for row in store.get("decisions") or []:
        _materialize_decision(g, row)
    prev = ""
    for row in store.get("pivots") or []:
        _materialize_pivot(g, row)
        pid = str(row.get("id") or "")
        if prev and pid:
            g.add_edge(prev, pid, "next_pivot")
        prev = pid or prev


def _materialize_decision(g: ContextGraph, row: dict[str, Any]) -> None:
    did = str(row.get("id") or node_id("decision", row.get("round"), row.get("ts")))
    g.add_node(
        did,
        "decision",
        label=str(row.get("label") or row.get("outcome") or "decision"),
        stage="deliberate",
        family="decision",
        text=str(row.get("text") or ""),
        source=str(row.get("source") or "agent.write_back"),
        confidence=row.get("confidence"),
        authority=str(row.get("authority") or "authority:codeevolve"),
        valid_from=str(row.get("valid_from") or row.get("ts") or ""),
        valid_to=str(row.get("valid_to") or ""),
        meta={
            "outcome": row.get("outcome"),
            "stance": row.get("stance"),
            "round": row.get("round"),
            "impasse": (row.get("impasse") or {}),
        },
    )
    rel = str(row.get("rel") or decision_rel(str(row.get("outcome") or "")))
    for fid in row.get("frame_ids") or []:
        fn = fid if str(fid).startswith("frame:") else node_id("frame", fid)
        g.add_node(fn, "frame", label=str(fid), stage="deliberate", family="knowledge")
        g.add_edge(did, fn, "allowed_because" if rel == "allowed_because" else rel)
        g.add_edge(did, fn, "cites")
    for pid in policy_for_outcome(str(row.get("outcome") or ""), str(row.get("stance") or "")):
        if pid in g.nodes:
            g.add_edge(did, pid, rel)
    rnd = row.get("round")
    if rnd is not None:
        rid = node_id("round", rnd)
        if rid in g.nodes:
            g.add_edge(rid, did, "proposed")
            g.add_edge(rid, did, "precedes")


def _materialize_pivot(g: ContextGraph, row: dict[str, Any]) -> None:
    pid = str(row.get("id") or node_id("pivot", row.get("round"), row.get("pivot_type")))
    ptype = str(row.get("pivot_type") or row.get("label") or "pivot")
    g.add_node(
        pid,
        "pivot",
        label=ptype,
        stage=str(row.get("stage") or ""),
        family="pivot",
        text=str(row.get("text") or ""),
        source=str(row.get("source") or "agent.write_back"),
        confidence=row.get("confidence"),
        authority=str(row.get("authority") or "authority:codeevolve"),
        valid_from=str(row.get("valid_from") or row.get("ts") or ""),
        valid_to=str(row.get("valid_to") or ""),
        meta={"pivot_type": ptype, "round": row.get("round")},
    )
    rnd = row.get("round")
    if rnd is not None:
        rid = node_id("round", rnd)
        if rid not in g.nodes:
            g.add_node(rid, "round", label=f"round {rnd}", stage="act", family="flow")
        g.add_edge(rid, pid, "pivots")
    did = str(row.get("decision") or "")
    if did:
        if did not in g.nodes:
            g.add_node(did, "decision", label="decision", stage="deliberate", family="decision")
        g.add_edge(pid, did, "joins")
    prev = str(row.get("prev") or "")
    if prev and prev in g.nodes:
        g.add_edge(prev, pid, "next_pivot")
    for jid in row.get("joins") or []:
        jid = str(jid)
        if jid not in g.nodes:
            kind = jid.split(":", 1)[0] if ":" in jid else "context"
            g.add_node(jid, kind if kind in {"path", "frame", "policy", "kernel", "window", "type"} else "context", label=jid)
        g.add_edge(pid, jid, "joins")
