"""Parse report.json, AgentRun, cognition, and agent dirs into a ContextGraph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codeevolve.graph.families import FLOW_RELS
from codeevolve.graph.model import ContextGraph, node_id
from codeevolve.graph.policy import ingest_policies
from codeevolve.graph.store import ingest_store, load_graph_store
from codeevolve.graph.trace import ingest_flow_pivots, ingest_round_traces

_nid = node_id

_STAGE = {
    "commit": "taxon",
    "clade": "taxon",
    "type": "taxon",
    "niche": "taxon",
    "path": "context",
    "frame": "deliberate",
    "record": "deliberate",
    "run": "act",
    "round": "act",
    "kernel": "deliberate",
    "subagent": "act",
    "tool": "act",
    "proposal": "act",
    "patch": "act",
    "reflection": "deliberate",
    "rag": "sense",
    "memory": "sense",
    "morpheme": "sense",
    "score": "verify",
    "test": "verify",
    "decision": "deliberate",
    "pivot": "act",
    "policy": "deliberate",
    "authority": "deliberate",
    "claim": "deliberate",
    "context": "context",
    "window": "context",
    "focus": "sense",
    "fence": "act",
    "blast": "context",
    "delta": "context",
}


def parse_context(
    *,
    report: dict[str, Any] | None = None,
    agent: dict[str, Any] | None = None,
    cognition: dict[str, Any] | None = None,
    agent_dir: Path | str | None = None,
    source: str = "",
) -> ContextGraph:
    """Merge phylogeny/provenance context with agentic flow traces."""
    g = ContextGraph(source=source or "context")
    ingest_policies(g)
    loaded: dict[str, Any] = {}
    store_root: Path | None = None
    if agent_dir:
        loaded = load_agent_dir(agent_dir)
        report = report or loaded.get("report")
        agent = agent or loaded.get("run")
        cognition = cognition or loaded.get("cognition")
        store_root = Path(agent_dir)
    if report:
        ingest_report(g, report)
    if agent:
        ingest_agent_run(g, agent)
    if cognition:
        if "run:latest" not in g.nodes:
            g.add_node("run:latest", "run", label="cognition", stage="act", text="cognition cycle")
        ingest_cognition(g, cognition, parent="run:latest")
        if not agent:
            ingest_flow_pivots(g, parent="run:latest")
    for sub in loaded.get("subagents") or []:
        if "run:latest" not in g.nodes:
            g.add_node("run:latest", "run", label="agent", stage="act")
        _ingest_subagent(g, sub, parent="run:latest")
    if store_root is not None:
        ingest_store(g, load_graph_store(store_root))
    else:
        guess = Path(".codeevolve") / "graph"
        if guess.is_dir():
            ingest_store(g, load_graph_store(guess))
    return g


def load_agent_dir(path: Path | str) -> dict[str, Any]:
    root = Path(path)
    out: dict[str, Any] = {"subagents": []}
    if root.is_file():
        data = _read_json(root)
        if isinstance(data, dict) and "rounds" in data:
            out["run"] = data
        elif isinstance(data, dict) and "reflection" in data and "actions" in data:
            out["cognition"] = data
        return out
    for name, key in (("run.json", "run"), ("cognition.json", "cognition"), ("session.json", "session")):
        fp = root / name
        if fp.is_file():
            data = _read_json(fp)
            if isinstance(data, dict):
                out[key] = data
    sub = root / "subagents"
    if sub.is_dir():
        for fp in sorted(sub.glob("*.json"))[:40]:
            data = _read_json(fp)
            if isinstance(data, dict) and data.get("kernel"):
                out["subagents"].append(data)
    report = root.parent / "report.json"
    if report.is_file():
        data = _read_json(report)
        if isinstance(data, dict):
            out["report"] = data
    return out


def ingest_report(g: ContextGraph, report: dict[str, Any]) -> None:
    repo = str(report.get("repo") or "")
    g.add_node(_nid("repo", repo or "local"), "path", label=repo or "repo", stage="context", text=repo)

    phy = report.get("phylogeny") or {}
    nodes = list(phy.get("nodes") or [])[:240]
    by_sha = {str(n.get("sha") or ""): n for n in nodes if n.get("sha")}
    for n in nodes:
        sha = str(n.get("sha") or "")
        if not sha:
            continue
        g.add_node(
            _nid("commit", sha),
            "commit",
            label=sha[:7],
            stage="taxon",
            text=str(n.get("subject") or ""),
            source="report.phylogeny",
            meta={"generation": n.get("generation"), "subject": n.get("subject")},
        )
    for n in nodes:
        sha = str(n.get("sha") or "")
        for p in n.get("parent_shas") or n.get("parents") or []:
            full = str(p)
            if full not in by_sha:
                full = next((s for s in by_sha if s.startswith(str(p)[:7])), "")
            if full:
                g.add_edge(_nid("commit", full), _nid("commit", sha), "parent_of")

    tax = report.get("taxonomy") or {}
    for c in (tax.get("clades") or [])[:40]:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        cid = str(c["id"])
        tp = c.get("type_path") or []
        tkey = "/".join(str(x) for x in tp if x) if isinstance(tp, list) else str(c.get("code_type") or "")
        g.add_node(
            _nid("clade", cid),
            "clade",
            label=str(c.get("label") or cid),
            stage="taxon",
            text=tkey or str(c.get("role") or ""),
            meta={"type_path": tp, "role": c.get("role")},
        )
        if tkey:
            tid = _nid("type", tkey)
            g.add_node(tid, "type", label=tkey, stage="taxon", text=tkey)
            g.add_edge(_nid("clade", cid), tid, "typed_as")
        for f in (c.get("files") or [])[:12]:
            pid = _nid("path", f)
            g.add_node(pid, "path", label=str(f), stage="context", text=str(f))
            g.add_edge(_nid("clade", cid), pid, "contains")

    kw = tax.get("keyword_taxonomy") or {}
    if isinstance(kw, dict):
        for path, hit in list((kw.get("path_types") or {}).items())[:200]:
            tkey = ""
            if isinstance(hit, dict):
                raw = hit.get("type_path") or []
                tkey = "/".join(str(x) for x in raw if x) if isinstance(raw, list) else str(hit.get("type_key") or "")
            if not tkey:
                continue
            tid = _nid("type", tkey)
            g.add_node(tid, "type", label=tkey, stage="taxon", text=tkey)
            pid = _nid("path", path)
            g.add_node(pid, "path", label=str(path), stage="context", text=str(path))
            g.add_edge(pid, tid, "typed_as")

    sem = tax.get("semantic") or {}
    if isinstance(sem, dict):
        labels = {str(n.get("id")): str(n.get("label") or n.get("id")) for n in (sem.get("niches") or []) if isinstance(n, dict) and n.get("id")}
        for path, nid in list((sem.get("path_to_niche") or {}).items())[:200]:
            kid = _nid("niche", nid)
            g.add_node(kid, "niche", label=labels.get(str(nid), str(nid)), stage="taxon", text=str(nid))
            pid = _nid("path", path)
            g.add_node(pid, "path", label=str(path), stage="context")
            g.add_edge(pid, kid, "in_niche")

    for a in (tax.get("allocations") or [])[:300]:
        if not isinstance(a, dict):
            continue
        sha = str(a.get("sha") or "")
        path = str(a.get("path") or "")
        cid = str(a.get("clade_id") or "")
        if sha and path:
            g.add_node(_nid("commit", sha), "commit", label=sha[:7], stage="taxon")
            g.add_node(_nid("path", path), "path", label=path, stage="context")
            g.add_edge(_nid("commit", sha), _nid("path", path), "touches")
        if sha and cid:
            g.add_node(_nid("clade", cid), "clade", label=cid, stage="taxon")
            g.add_edge(_nid("commit", sha), _nid("clade", cid), "in_clade")

    prov = report.get("provenance") or {}
    for f in (prov.get("frames") or [])[:40]:
        if not isinstance(f, dict) or not f.get("id"):
            continue
        fid = str(f["id"])
        g.add_node(
            fid if fid.startswith("frame:") else _nid("frame", fid),
            "frame",
            label=fid,
            stage="deliberate",
            text=str(f.get("claim") or ""),
            meta={"stance": f.get("stance"), "falsifier": f.get("falsifier"), "measure": f.get("measure")},
            source="report.provenance",
            confidence=0.9 if f.get("stance") and f.get("stance") != "insufficient" else 0.3,
        )
        for cid in (f.get("context_clades") or [])[:6]:
            g.add_node(_nid("clade", cid), "clade", label=str(cid), stage="taxon")
            g.add_edge(fid if fid.startswith("frame:") else _nid("frame", fid), _nid("clade", cid), "cites")
        for ev in (f.get("evidence") or [])[:6]:
            if not isinstance(ev, dict):
                continue
            rid = str(ev.get("record_id") or "")
            if not rid:
                continue
            g.add_node(_nid("record", rid), "record", label=rid, stage="deliberate", text=str(ev.get("kind") or ""))
            g.add_edge(fid if fid.startswith("frame:") else _nid("frame", fid), _nid("record", rid), "cites")

    for e in ((report.get("genetics") or {}).get("gene_flow") or [])[:40]:
        if not isinstance(e, dict):
            continue
        a = str(e.get("source_clade") or "")
        b = str(e.get("target_clade") or "")
        if a and b:
            g.add_node(_nid("clade", a), "clade", label=a, stage="taxon")
            g.add_node(_nid("clade", b), "clade", label=b, stage="taxon")
            g.add_edge(_nid("clade", a), _nid("clade", b), "gene_flow", weight=float(e.get("weight") or 1))

    _ingest_report_signals(g, report)


def _ingest_report_signals(g: ContextGraph, report: dict[str, Any]) -> None:
    """Ecology/debt/risk/blast from the report only — do not invent GitLab MRs or pipelines."""
    eco = report.get("ecology") if isinstance(report.get("ecology"), dict) else {}
    stage = str(eco.get("global_stage") or "")
    if stage:
        g.add_node(
            "window:ecology",
            "window",
            label=f"stage:{stage}",
            stage="context",
            family="context",
            text=str(eco.get("stage_rationale") or stage),
            source="report.ecology",
            confidence=0.8,
            meta={"stage": stage},
        )
        g.add_edge("window:ecology", _nid("repo", str(report.get("repo") or "local")), "in_window")
        for cs in (eco.get("clade_stages") or [])[:20]:
            if not isinstance(cs, dict):
                continue
            cid = str(cs.get("clade_id") or "")
            if cid:
                g.add_node(_nid("clade", cid), "clade", label=str(cs.get("label") or cid), stage="taxon")
                g.add_edge(_nid("clade", cid), "window:ecology", "in_window")

    debt = report.get("debt") if isinstance(report.get("debt"), dict) else {}
    if debt:
        g.add_node(
            "context:debt",
            "context",
            label=f"debt:{debt.get('score')}",
            stage="context",
            family="context",
            text=str(debt.get("summary") or debt.get("score") or ""),
            source="report.debt",
            confidence=0.7,
            meta={"score": debt.get("score")},
        )

    risk = report.get("risk") if isinstance(report.get("risk"), dict) else {}
    if risk:
        g.add_node(
            "context:risk",
            "context",
            label="risk",
            stage="context",
            family="context",
            text=str(risk.get("summary") or ""),
            source="report.risk",
            confidence=0.7,
        )
        for fp in (risk.get("failure_points") or [])[:12]:
            if not isinstance(fp, dict):
                continue
            path = str(fp.get("path") or "")
            bid = _nid("blast", fp.get("id") or path or fp.get("kind"))
            g.add_node(
                bid,
                "blast",
                label=str(fp.get("title") or fp.get("kind") or "blast"),
                stage="context",
                family="context",
                text=str(fp.get("title") or ""),
                source="report.risk",
                meta={"severity": fp.get("severity"), "kind": fp.get("kind")},
            )
            g.add_edge("context:risk", bid, "blast_of")
            if path:
                g.add_node(_nid("path", path), "path", label=path, stage="context")
                g.add_edge(bid, _nid("path", path), "blast_of")

    blast = report.get("blast_radius") or []
    if isinstance(blast, dict):
        blast = blast.get("rows") or blast.get("paths") or []
    for i, row in enumerate(list(blast)[:12]):
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        if not path:
            continue
        bid = _nid("blast", "radius", path)
        g.add_node(
            bid,
            "blast",
            label=path,
            stage="context",
            family="context",
            text=str(row.get("blast_score") or ""),
            source="report.blast_radius",
        )
        g.add_node(_nid("path", path), "path", label=path, stage="context")
        g.add_edge(bid, _nid("path", path), "blast_of")


def ingest_agent_run(g: ContextGraph, run: dict[str, Any]) -> None:
    obj = run.get("objective") if isinstance(run.get("objective"), dict) else {"kind": run.get("objective")}
    kind = str((obj or {}).get("kind") or "follow_refactor")
    rid = _nid("run", "latest")
    g.add_node(
        rid,
        "run",
        label=f"agent:{kind}",
        stage="act",
        text=str(run.get("summary") or kind),
        meta={"status": run.get("status"), "objective": kind, "repo": run.get("repo")},
    )
    prev = rid
    for i, rnd in enumerate(run.get("rounds") or []):
        if not isinstance(rnd, dict):
            continue
        rnode = _ingest_round(g, rnd, index=i, parent=rid)
        g.add_edge(prev, rnode, "next")
        prev = rnode
        cog = rnd.get("cognition")
        if isinstance(cog, dict):
            ingest_cognition(g, cog, parent=rnode)
    cog = run.get("cognition")
    if isinstance(cog, dict):
        ingest_cognition(g, cog, parent=rid)
    tests = run.get("tests")
    if isinstance(tests, dict) and tests:
        tid = _nid("test", "run")
        g.add_node(
            tid,
            "test",
            label="tests",
            stage="verify",
            text=str(tests.get("summary") or tests.get("ok") or ""),
            meta=tests if len(str(tests)) < 800 else {},
        )
        g.add_edge(rid, tid, "scored")


def ingest_cognition(g: ContextGraph, cog: dict[str, Any], *, parent: str | None = None) -> None:
    host = parent if parent and parent in g.nodes else None
    refl = cog.get("reflection") if isinstance(cog.get("reflection"), dict) else {}
    if refl:
        nid = _nid("reflect", host or "cycle", refl.get("stance") or "open")
        g.add_node(
            nid,
            "reflection",
            label=f"reflect:{refl.get('stance') or '?'}",
            stage="deliberate",
            text=" ".join(str(x) for x in (refl.get("insights") or [])[:4]),
            meta={"stance": refl.get("stance"), "next_focus": refl.get("next_focus")},
        )
        if host:
            g.add_edge(host, nid, "reflects")
        for k in refl.get("spawn_kernels") or []:
            kid = _nid("kernel", k)
            g.add_node(kid, "kernel", label=str(k), stage="deliberate", text=str(k))
            g.add_edge(nid, kid, "spawned")

    actions = cog.get("actions") if isinstance(cog.get("actions"), dict) else {}
    results = list(actions.get("results") or [])
    plan = (actions.get("plan") or {}).get("actions") or []
    seq_parent = host
    for i, row in enumerate(results[:24]):
        if not isinstance(row, dict):
            continue
        res = row.get("result") if isinstance(row.get("result"), dict) else row
        name = str(res.get("name") or row.get("name") or "tool")
        tid = _nid("tool", name, i)
        g.add_node(
            tid,
            "tool",
            label=name,
            stage="act",
            text=str(res.get("error") or "") or _brief(res.get("output")),
            meta={"ok": res.get("ok"), "tool": name},
        )
        if seq_parent:
            g.add_edge(seq_parent, tid, "invoked" if i == 0 or seq_parent == host else "next")
        seq_parent = tid
        if name == "rag_query":
            _ingest_rag_hits(g, res.get("output"), parent=tid)
        if name == "provenance_hint":
            _ingest_hint_frames(g, res.get("output"), parent=tid)
        if name == "graph_search":
            _ingest_graph_search(g, res.get("output"), parent=tid)

    for i, act in enumerate(plan[:12]):
        if not isinstance(act, dict):
            continue
        name = str(act.get("name") or act.get("kind") or "")
        if not name:
            continue
        # skip if already materialized from results
        if any(n.kind == "tool" and n.meta.get("tool") == name for n in g.by_kind("tool")):
            continue
        tid = _nid("tool", "plan", name, i)
        g.add_node(tid, "tool", label=name, stage="act", text=str(act.get("rationale") or ""), meta={"planned": True})
        if host:
            g.add_edge(host, tid, "invoked")

    for k in cog.get("kernels") or []:
        if not isinstance(k, dict):
            continue
        name = str(k.get("name") or "")
        if not name:
            continue
        kid = _nid("kernel", name)
        g.add_node(kid, "kernel", label=name, stage="deliberate", text=str(k.get("description") or name))
        if host:
            g.add_edge(host, kid, "spawned")

    for sub in cog.get("subagents") or []:
        if isinstance(sub, dict):
            _ingest_subagent(g, sub, parent=host)

    morph = cog.get("morphemes") if isinstance(cog.get("morphemes"), dict) else {}
    if morph.get("morpheme_count"):
        mid = _nid("morpheme", "cycle")
        g.add_node(
            mid,
            "morpheme",
            label="morphemes",
            stage="sense",
            text=str(morph.get("summary") or f"n={morph.get('morpheme_count')}"),
        )
        if host:
            g.add_edge(host, mid, "retrieved")

    mem = cog.get("memory") if isinstance(cog.get("memory"), dict) else {}
    notes = mem.get("notes") or mem.get("items") or []
    for i, note in enumerate(notes[:12]):
        if not isinstance(note, dict):
            continue
        nid = _nid("memory", note.get("id") or i)
        g.add_node(
            nid,
            "memory",
            label=str(note.get("kind") or "note"),
            stage="sense",
            text=str(note.get("content") or note.get("text") or "")[:240],
        )
        if host:
            g.add_edge(host, nid, "retrieved")


def _ingest_round(g: ContextGraph, rnd: dict[str, Any], *, index: int, parent: str) -> str:
    rid = _nid("round", index)
    g.add_node(
        rid,
        "round",
        label=f"round {index}",
        stage="act",
        text=str(rnd.get("step_id") or ""),
        seq=index,
        meta={"accepted": rnd.get("accepted"), "applied": rnd.get("applied"), "step_id": rnd.get("step_id")},
    )
    g.add_edge(parent, rid, "next")
    prop = rnd.get("proposal")
    if isinstance(prop, dict):
        pid = _nid("proposal", index)
        g.add_node(
            pid,
            "proposal",
            label=str(prop.get("stance") or "proposal"),
            stage="act",
            text=str(prop.get("summary") or prop.get("claim") or "")[:300],
            meta={"stance": prop.get("stance"), "frame_ids": prop.get("frame_ids")},
        )
        g.add_edge(rid, pid, "proposed")
        for fid in prop.get("frame_ids") or []:
            fn = fid if str(fid).startswith("frame:") else _nid("frame", fid)
            g.add_node(fn, "frame", label=str(fid), stage="deliberate")
            g.add_edge(pid, fn, "cites")
        for prev in prop.get("edit_previews") or []:
            path = prev.get("path") if isinstance(prev, dict) else None
            if path:
                g.add_node(_nid("path", path), "path", label=str(path), stage="context")
                g.add_edge(pid, _nid("path", path), "focuses")
    patch = rnd.get("patch")
    if isinstance(patch, dict) and patch:
        nid = _nid("patch", index)
        g.add_node(nid, "patch", label="patch", stage="act", text=str(patch.get("summary") or "")[:200])
        g.add_edge(rid, nid, "proposed")
    after = rnd.get("score_after")
    if isinstance(after, dict) and after:
        sid = _nid("score", index)
        g.add_node(
            sid,
            "score",
            label="score",
            stage="verify",
            text=str(after.get("summary") or after.get("improved") or ""),
            meta={"accepted": rnd.get("accepted")},
        )
        g.add_edge(rid, sid, "scored")
    ingest_round_traces(g, rnd, index=index, round_id=rid)
    return rid


def _ingest_subagent(g: ContextGraph, sub: dict[str, Any], *, parent: str | None) -> None:
    sid = str(sub.get("id") or "sub")
    nid = _nid("subagent", sid)
    ker = sub.get("kernel") if isinstance(sub.get("kernel"), dict) else {}
    kname = str(ker.get("name") or sub.get("kernel") or "kernel")
    g.add_node(
        nid,
        "subagent",
        label=f"sub:{kname}",
        stage="act",
        text=" ".join(str(x) for x in (sub.get("findings") or [])[:4]),
        meta={"status": sub.get("status"), "kernel": kname},
    )
    kid = _nid("kernel", kname)
    g.add_node(kid, "kernel", label=kname, stage="deliberate", text=str(ker.get("description") or kname))
    g.add_edge(nid, kid, "kernel_of")
    if parent and parent in g.nodes:
        g.add_edge(parent, nid, "spawned")
        g.add_edge(parent, kid, "spawned")
    refl = sub.get("reflection")
    if isinstance(refl, dict) and refl:
        rid = _nid("reflect", "sub", sid)
        g.add_node(
            rid,
            "reflection",
            label=f"reflect:{refl.get('stance') or '?'}",
            stage="deliberate",
            text=str(refl.get("next_focus") or ""),
        )
        g.add_edge(nid, rid, "reflects")
    actions = sub.get("actions") if isinstance(sub.get("actions"), dict) else {}
    prev = nid
    for i, row in enumerate((actions.get("results") or sub.get("tool_outputs") or [])[:16]):
        if not isinstance(row, dict):
            continue
        res = row.get("result") if isinstance(row.get("result"), dict) else row
        name = str(res.get("name") or row.get("name") or "tool")
        tid = _nid("tool", "sub", sid, name, i)
        g.add_node(tid, "tool", label=name, stage="act", text=_brief(res.get("output")), meta={"ok": res.get("ok")})
        g.add_edge(prev, tid, "invoked" if i == 0 else "next")
        prev = tid
        if name == "graph_search":
            _ingest_graph_search(g, res.get("output"), parent=tid)


def _ingest_rag_hits(g: ContextGraph, output: Any, *, parent: str) -> None:
    hits = output if isinstance(output, list) else (output.get("hits") if isinstance(output, dict) else []) or []
    for i, h in enumerate(hits[:8]):
        if not isinstance(h, dict):
            continue
        hid = _nid("rag", h.get("chunk_id") or h.get("path") or i)
        path = str(h.get("path") or "")
        g.add_node(hid, "rag", label=path or "chunk", stage="sense", text=str(h.get("text") or "")[:240])
        g.add_edge(parent, hid, "retrieved")
        if path:
            g.add_node(_nid("path", path), "path", label=path, stage="context")
            g.add_edge(hid, _nid("path", path), "focuses")


def _ingest_hint_frames(g: ContextGraph, output: Any, *, parent: str) -> None:
    frames = []
    if isinstance(output, dict):
        frames = list(output.get("frames") or [])
    for fr in frames[:8]:
        if not isinstance(fr, dict) or not fr.get("id"):
            continue
        fid = str(fr["id"])
        nid = fid if fid.startswith("frame:") else _nid("frame", fid)
        g.add_node(nid, "frame", label=fid, stage="deliberate", text=str(fr.get("claim") or ""))
        g.add_edge(parent, nid, "cites")


def _ingest_graph_search(g: ContextGraph, output: Any, *, parent: str) -> None:
    """Ingest graph_search hits/flow/precedent. Silent/empty output is a no-op."""
    if not isinstance(output, dict):
        return
    for h in (output.get("hits") or [])[:12]:
        if not isinstance(h, dict):
            continue
        hid = str(h.get("id") or "")
        if not hid:
            continue
        kind = str(h.get("kind") or "context")
        g.add_node(
            hid,
            kind,
            label=str(h.get("label") or hid),
            stage=str(h.get("stage") or "sense"),
            text=str(h.get("text") or "")[:240],
            family=str(h.get("family") or ""),
        )
        g.add_edge(parent, hid, "retrieved")
    flow = output.get("flow") if isinstance(output.get("flow"), dict) else None
    if flow:
        summary = str(flow.get("summary") or "")
        if summary or flow.get("steps"):
            fid = _nid("flow", parent)
            g.add_node(
                fid,
                "context",
                label="flow",
                stage="sense",
                family="flow",
                text=summary[:240],
            )
            g.add_edge(parent, fid, "retrieved")
        for step in (flow.get("steps") or [])[:8]:
            if not isinstance(step, dict) or not step.get("id"):
                continue
            sid = str(step["id"])
            g.add_node(
                sid,
                str(step.get("kind") or "tool"),
                label=str(step.get("label") or sid),
                stage=str(step.get("stage") or "act"),
            )
            g.add_edge(parent, sid, "retrieved")
    for p in (output.get("precedent") or [])[:8]:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        pid = str(p["id"])
        g.add_node(
            pid,
            str(p.get("kind") or "decision"),
            label=str(p.get("label") or pid),
            stage="deliberate",
            text=str(p.get("text") or "")[:240],
        )
        g.add_edge(parent, pid, "cites")


def _brief(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, list):
        return f"n={len(value)}"
    if isinstance(value, dict):
        return ",".join(list(value.keys())[:6])
    return str(value)[:160]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
