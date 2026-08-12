"""Interactive 3D phylogeny builder (self-contained canvas, no extra deps)."""

from __future__ import annotations

import json
from html import escape as _esc
from typing import Any

from codeevolve.viz.colors import clade_color, intent_color, stage_color
from codeevolve.viz.intent import INTENT_COLORS, INTENT_ORDER, intent_rank
from codeevolve.viz.layout import layout_layered_dag
from codeevolve.viz.model import VizModel

_STAGES = ("pioneer", "growth", "disturbance", "consolidation", "maturity", "decline")


def builder_payload(model: VizModel) -> dict[str, Any]:
    ids = [c.sha for c in model.commits]
    parents = {c.sha: list(c.parents) for c in model.commits}
    children = {c.sha: list(c.children) for c in model.commits}
    generation = {c.sha: c.generation for c in model.commits}
    clade_of = {c.sha: c.clade_id for c in model.commits}
    lay = layout_layered_dag(
        ids,
        parents=parents,
        children=children,
        generation=generation,
        roots=model.roots,
        clade_of=clade_of,
    )
    clades = sorted({c.clade_id for c in model.commits if c.clade_id})
    clade_z = {cid: i for i, cid in enumerate(clades)}
    id_set = set(ids)
    short = {s[:7]: s for s in ids}

    def resolve(p: str) -> str | None:
        if p in id_set:
            return p
        return short.get((p or "")[:7])

    nodes = []
    for c in model.commits:
        n = lay.nodes.get(c.sha)
        if not n or n.hidden:
            continue
        nodes.append(
            {
                "id": c.sha,
                "sha": c.sha[:7],
                "subject": c.subject,
                "generation": c.generation,
                "x": n.x,
                "y": n.y,
                "zIntent": intent_rank(c.intent) * 48.0,
                "zClade": clade_z.get(c.clade_id, 0) * 48.0,
                "zAnalysis": c.analysis_score * 240.0,
                "zStage": (_STAGES.index(c.stage) if c.stage in _STAGES else 0) * 48.0,
                "parents": [resolve(p) for p in c.parents if resolve(p)],
                "clade_id": c.clade_id,
                "clade_label": c.clade_label,
                "clade_color": clade_color(c.clade_id),
                "stage": c.stage,
                "stage_color": stage_color(c.stage),
                "intent": c.intent,
                "intent_color": intent_color(c.intent),
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
                "tree_parent": model.tree_parent.get(c.sha),
            }
        )
    edges = []
    for c in model.commits:
        for p in c.parents:
            src = resolve(p)
            if not src:
                continue
            kind = "tree" if src == model.tree_parent.get(c.sha) else "merge"
            if c.parsimony_change and kind == "tree":
                kind = "parsimony"
            edges.append({"source": src, "target": c.sha, "kind": kind})
    frames = []
    for f in model.frames:
        frames.append(
            {
                "id": f.get("id"),
                "claim": f.get("claim"),
                "stance": f.get("stance"),
                "confidence": f.get("confidence"),
                "falsifier": f.get("falsifier"),
                "measure": f.get("measure"),
                "context_clades": list(f.get("context_clades") or [])[:8],
            }
        )
    return {
        "repo": model.repo,
        "meta": {
            "node_count": model.node_count,
            "drawn": len(nodes),
            "truncated": model.truncated,
            "max_generation": model.max_generation,
            "merge_count": model.merge_count,
            "branch_factor": model.branch_factor,
            "current_stage": model.current_stage,
            "intent_counts": dict(model.intent_counts),
            "parsimony": {
                "steps": model.parsimony.steps,
                "ci": model.parsimony.consistency_index,
                "ri": model.parsimony.retention_index,
            },
        },
        "analysis": dict(model.analysis),
        "intents": [{"id": k, "color": INTENT_COLORS[k]} for k in INTENT_ORDER],
        "nodes": nodes,
        "edges": edges,
        "frames": frames,
        "gene_flow": list(model.gene_flow)[:40],
        "axes": {
            "x": "generation (time)",
            "y": "lineage rank",
            "z": "intent | clade | analysis | stage",
        },
    }


def render_builder_inner(model: VizModel) -> str:
    payload = json.dumps(builder_payload(model), ensure_ascii=True, default=str).replace("<", "\\u003c")
    return _INNER.replace("__PAYLOAD__", payload)


def render_builder_page(model: VizModel) -> str:
    title = _esc(model.repo or "repo")
    inner = render_builder_inner(model)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>CodeEvolve 3D phylogeny — {title}</title>
<style>{_CSS}</style>
</head>
<body class="builder-page">
<header class="builder-head">
  <h1>CodeEvolve 3D phylogeny builder</h1>
  <div class="meta">{title} · drag to orbit · wheel zoom · click a node for intent + analysis</div>
</header>
{inner}
</body>
</html>
"""


_CSS = """
:root { --bg:#0f1419; --fg:#e7ecf1; --muted:#8b9aab; --accent:#3dd6c6; --card:#161d27; --line:#243041; --warn:#f0a35e; }
.builder-page { margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--fg); }
.builder-head { padding:1rem 1.5rem .6rem; border-bottom:1px solid var(--line); }
.builder-head h1 { margin:0; font-size:1.2rem; }
.builder-head .meta { color:var(--muted); margin-top:.35rem; font-size:.85rem; }
.phy3d { display:grid; grid-template-columns:1fr 320px; gap:0; min-height:70vh; background:#121822; border:1px solid var(--line); border-radius:12px; overflow:hidden; }
.phy3d-stage { position:relative; min-height:560px; }
.phy3d-stage canvas { display:block; width:100%; height:100%; cursor:grab; background:radial-gradient(ellipse at 50% 40%, #1a2433, #0c1016 70%); }
.phy3d-stage canvas:active { cursor:grabbing; }
.phy3d-toolbar { position:absolute; left:10px; top:10px; display:flex; flex-wrap:wrap; gap:6px; max-width:72%; }
.phy3d-toolbar label, .phy3d-toolbar select, .phy3d-toolbar button, .phy3d-toolbar input {
  font:12px/1.2 "Segoe UI",system-ui,sans-serif; background:#161d27; color:var(--fg); border:1px solid var(--line);
  border-radius:6px; padding:4px 8px;
}
.phy3d-side { border-left:1px solid var(--line); background:var(--card); padding:12px 14px; overflow:auto; font-size:.82rem; }
.phy3d-side h2 { margin:0 0 .5rem; font-size:.95rem; color:var(--accent); }
.phy3d-side h3 { margin:1rem 0 .35rem; font-size:.8rem; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
.phy3d-side .kv { display:grid; grid-template-columns:88px 1fr; gap:4px 8px; }
.phy3d-side .kv span { color:var(--muted); }
.phy3d-side .frame { border:1px solid var(--line); border-radius:8px; padding:8px; margin:.45rem 0; }
.phy3d-side .stance { color:var(--warn); }
.phy3d-side .hint { color:var(--muted); font-size:.75rem; margin-top:.75rem; }
.swatch { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; vertical-align:middle; }
@media (max-width:900px) { .phy3d { grid-template-columns:1fr; } .phy3d-side { border-left:0; border-top:1px solid var(--line); max-height:40vh; } }
"""

_INNER = """
<style>
""" + _CSS + """
</style>
<div class="phy3d" id="phy3d">
  <div class="phy3d-stage">
    <canvas id="phy3d-canvas" width="960" height="640"></canvas>
    <div class="phy3d-toolbar">
      <label>color <select id="phy3d-color">
        <option value="intent">intent</option>
        <option value="clade">clade</option>
        <option value="stage">stage</option>
        <option value="parsimony">parsimony</option>
      </select></label>
      <label>Z <select id="phy3d-z">
        <option value="zIntent">intent</option>
        <option value="zClade">clade</option>
        <option value="zAnalysis">analysis</option>
        <option value="zStage">stage</option>
      </select></label>
      <label><input type="checkbox" id="phy3d-tree" checked/> tree</label>
      <label><input type="checkbox" id="phy3d-merge" checked/> merges</label>
      <label><input type="checkbox" id="phy3d-pars" checked/> parsimony</label>
      <input id="phy3d-q" placeholder="filter sha / subject / intent" size="22"/>
    </div>
  </div>
  <aside class="phy3d-side" id="phy3d-side"></aside>
</div>
<script>
(function(){
  const DATA = __PAYLOAD__;
  const cv = document.getElementById("phy3d-canvas");
  const side = document.getElementById("phy3d-side");
  if (!cv || !DATA) return;
  const ctx = cv.getContext("2d");
  const cam = { yaw: 0.55, pitch: 0.42, dist: 720, panX: 0, panY: 40 };
  let dragging = false, lastX=0, lastY=0, downX=0, downY=0, selected=null;
  DATA.nodes.forEach(function(n){ /* index */ });
  function zOf(n){
    const k = document.getElementById("phy3d-z").value;
    return n[k] || 0;
  }
  function colorOf(n){
    const m = document.getElementById("phy3d-color").value;
    if (m === "clade") return n.clade_color;
    if (m === "stage") return n.stage_color;
    if (m === "parsimony") return n.parsimony_change ? "#e07a9a" : "#3a4a5c";
    return n.intent_color;
  }
  function query(){
    return (document.getElementById("phy3d-q").value || "").trim().toLowerCase();
  }
  function visible(n){
    const q = query();
    if (!q) return true;
    return (n.sha+" "+n.subject+" "+n.intent+" "+(n.clade_label||"")).toLowerCase().indexOf(q) >= 0;
  }
  function cx0(){
    let sx=0,sy=0,sz=0,n=DATA.nodes.length||1;
    DATA.nodes.forEach(function(p){ sx+=p.x; sy+=p.y; sz+=zOf(p); });
    return {x:sx/n, y:sy/n, z:sz/n};
  }
  function project(p){
    const c = cx0();
    let x = p.x - c.x, y = p.y - c.y, z = zOf(p) - c.z;
    const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
    const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
    let x1 = x*cy + z*sy;
    let z1 = -x*sy + z*cy;
    let y1 = y*cp - z1*sp;
    let z2 = y*sp + z1*cp;
    const f = 520 / (cam.dist + z2 + 0.001);
    return {
      x: cv.width/2 + (x1 + cam.panX) * f,
      y: cv.height/2 + (y1 + cam.panY) * f,
      z: z2, f: f, r: Math.max(3.2, 7.5 * f)
    };
  }
  function draw(){
    const w = cv.clientWidth || 960, h = cv.clientHeight || 640;
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    ctx.clearRect(0,0,cv.width,cv.height);
    const showTree = document.getElementById("phy3d-tree").checked;
    const showMerge = document.getElementById("phy3d-merge").checked;
    const showPars = document.getElementById("phy3d-pars").checked;
    const proj = {};
    DATA.nodes.forEach(function(n){ if (visible(n)) proj[n.id] = project(n); });
    DATA.edges.forEach(function(e){
      const a = proj[e.source], b = proj[e.target];
      if (!a || !b) return;
      if (e.kind === "tree" && !showTree) return;
      if (e.kind === "merge" && !showMerge) return;
      if (e.kind === "parsimony" && !showPars) return;
      ctx.beginPath();
      ctx.strokeStyle = e.kind === "parsimony" ? "#e07a9a" : (e.kind === "merge" ? "#f0a35e" : "#3a4a5c");
      ctx.globalAlpha = e.kind === "tree" ? 0.55 : 0.8;
      ctx.lineWidth = e.kind === "parsimony" ? 2.2 : 1.15;
      if (e.kind === "merge") ctx.setLineDash([5,4]); else ctx.setLineDash([]);
      ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha = 1;
    });
    const order = DATA.nodes.filter(function(n){ return proj[n.id]; }).sort(function(a,b){ return proj[a.id].z - proj[b.id].z; });
    order.forEach(function(n){
      const p = proj[n.id];
      ctx.beginPath();
      ctx.fillStyle = colorOf(n);
      ctx.strokeStyle = (selected && selected.id === n.id) ? "#e7ecf1" : "#0f1419";
      ctx.lineWidth = (selected && selected.id === n.id) ? 2.4 : 1.2;
      ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
      ctx.fill(); ctx.stroke();
    });
    ctx.fillStyle = "#8b9aab";
    ctx.font = "11px Segoe UI,system-ui,sans-serif";
    const zlab = document.getElementById("phy3d-z").selectedOptions[0].text;
    ctx.fillText("X generation    Y lineage    Z "+zlab, 12, cv.height-12);
  }
  function inspect(n){
    selected = n;
    const meta = DATA.meta || {};
    const an = DATA.analysis || {};
    if (!n) {
      const counts = Object.entries(meta.intent_counts||{}).map(function(kv){ return kv[0]+":"+kv[1]; }).join(" · ");
      const gids = an.global_frame_ids || [];
      const gf = (DATA.frames||[]).filter(function(f){ return gids.indexOf(f.id)>=0; });
      side.innerHTML = "<h2>Analysis</h2><div class='kv'>"
        +"<span>repo</span><div>"+esc(DATA.repo||"")+"</div>"
        +"<span>nodes</span><div>"+(meta.drawn||0)+" / "+(meta.node_count||0)+"</div>"
        +"<span>stage</span><div>"+esc(an.stage||meta.current_stage||"")+"</div>"
        +"<span>basin</span><div>"+esc(an.basin||"—")+"</div>"
        +"<span>Fitch</span><div>steps "+((meta.parsimony||{}).steps)+" · CI "+((meta.parsimony||{}).ci)+" · RI "+((meta.parsimony||{}).ri)+"</div>"
        +"<span>debt</span><div>"+esc(String(an.debt_score==null?"—":an.debt_score))+"</div>"
        +"<span>risk</span><div>"+esc(String(an.risk_count||0))+" failure points</div>"
        +"<span>intent</span><div>"+esc(counts)+"</div></div>"
        +"<h3>Repo frames</h3>"+gf.map(frameHtml).join("")
        +"<p class='hint'>"+esc(an.note||"")+"</p>";
      draw(); return;
    }
    const frames = (DATA.frames||[]).filter(function(f){ return (n.frame_ids||[]).indexOf(f.id)>=0; });
    side.innerHTML = "<h2>"+esc(n.sha)+" · "+esc(n.intent)+"</h2><div class='kv'>"
      +"<span>subject</span><div>"+esc(n.subject||"")+"</div>"
      +"<span>intent</span><div><i class='swatch' style='background:"+n.intent_color+"'></i>"
      +esc(n.intent)+" · "+esc(n.intent_stance)+" · conf "+n.intent_confidence
      +(n.intent_evidence&&n.intent_evidence.length? " · "+esc(n.intent_evidence.join(", ")):"")+"</div>"
      +"<span>clade</span><div>"+esc(n.clade_label||n.clade_id||"—")+"</div>"
      +"<span>reconstructed</span><div>"+esc(n.reconstructed||"—")+"</div>"
      +"<span>stage</span><div>"+esc(n.stage||"—")+"</div>"
      +"<span>generation</span><div>"+n.generation+"</div>"
      +"<span>churn</span><div>"+n.churn+"</div>"
      +"<span>risk</span><div>"+n.risk+"</div>"
      +"<span>debt</span><div>"+n.debt+"</div>"
      +"<span>analysis</span><div>"+n.analysis_score+(n.merge?" · merge":"")+(n.parsimony_change?" · parsimony change":"")+"</div>"
      +"</div><h3>Frames</h3>"
      +(frames.length? frames.map(frameHtml).join("") : "<p class='hint'>No clade/sha-linked frames. Repo-level frames stay in the empty-selection panel.</p>");
    draw();
  }
  function frameHtml(f){
    return "<div class='frame'><strong>"+esc(f.id||"")+"</strong> <span class='stance'>"+esc(f.stance||"")+"</span>"
      +"<div>"+esc(f.claim||"")+"</div>"
      +(f.falsifier? "<div class='hint'>falsifier: "+esc(f.falsifier)+"</div>":"")
      +(f.measure? "<div class='hint'>measure: "+esc(f.measure)+"</div>":"")
      +"</div>";
  }
  function esc(s){
    return String(s==null?"":s).replace(/[&<>"']/g, function(c){
      if (c === "&") return "&amp;";
      if (c === "<") return "&lt;";
      if (c === ">") return "&gt;";
      if (c === '"') return "&quot;";
      return "&#39;";
    });
  }
  function hit(mx, my){
    let best=null, bd=14;
    DATA.nodes.forEach(function(n){
      if (!visible(n)) return;
      const p = project(n);
      const d = Math.hypot(p.x-mx, p.y-my);
      if (d < Math.max(bd, p.r+4)) { bd=d; best=n; }
    });
    return best;
  }
  cv.addEventListener("mousedown", function(e){ dragging=true; lastX=e.offsetX; lastY=e.offsetY; downX=e.offsetX; downY=e.offsetY; });
  window.addEventListener("mouseup", function(){ dragging=false; });
  cv.addEventListener("mousemove", function(e){
    if (!dragging) return;
    const dx=e.offsetX-lastX, dy=e.offsetY-lastY;
    lastX=e.offsetX; lastY=e.offsetY;
    if (e.shiftKey) { cam.panX += dx; cam.panY += dy; }
    else { cam.yaw += dx*0.01; cam.pitch = Math.max(-1.2, Math.min(1.2, cam.pitch+dy*0.01)); }
    draw();
  });
  cv.addEventListener("wheel", function(e){ e.preventDefault(); cam.dist = Math.max(180, Math.min(2400, cam.dist + e.deltaY*0.6)); draw(); }, {passive:false});
  cv.addEventListener("click", function(e){
    if (Math.abs(e.offsetX-downX)+Math.abs(e.offsetY-downY) > 8) return;
    inspect(hit(e.offsetX, e.offsetY));
  });
  ["phy3d-color","phy3d-z","phy3d-tree","phy3d-merge","phy3d-pars","phy3d-q"].forEach(function(id){
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", draw);
    if (el) el.addEventListener("change", draw);
  });
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(function(){ draw(); });
    ro.observe(cv.parentElement || cv);
  }
  document.querySelectorAll("input[name=viztab]").forEach(function(r){ r.addEventListener("change", function(){ setTimeout(draw, 30); }); });
  inspect(null);
})();
</script>
"""
