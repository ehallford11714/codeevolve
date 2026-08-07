"""Lightweight HTML canvas dashboard for clade × drift × fatigue."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def render_dashboard(report: dict[str, Any]) -> str:
    clades = (report.get("taxonomy") or {}).get("clades") or []
    drift = (report.get("drift") or {}).get("clade_drift") or []
    weekly = (report.get("fatigue") or {}).get("weekly") or []
    stab = report.get("stability") or {}
    title = html.escape(str(report.get("repo") or "repo"))

    drift_by = {d.get("clade_id"): d.get("drift", 0) for d in drift}
    points = []
    for c in clades[:20]:
        points.append(
            {
                "id": c.get("id"),
                "label": c.get("label"),
                "churn": c.get("churn") or 0,
                "drift": drift_by.get(c.get("id"), 0),
                "layer": c.get("layer"),
            }
        )

    frames = ((report.get("provenance") or {}).get("frames") or [])[:10]
    dyn = report.get("dynamics") or {}
    data = {
        "points": points,
        "weekly": weekly[-16:],
        "stability": stab,
        "fatigue": (report.get("fatigue") or {}).get("fatigue_score"),
        "stage": (report.get("ecology") or {}).get("global_stage"),
        "frames": [
            {
                "id": f.get("id"),
                "stance": f.get("stance"),
                "confidence": f.get("confidence"),
                "claim": f.get("claim"),
            }
            for f in frames
            if isinstance(f, dict)
        ],
        "dynamics_summary": dyn.get("summary"),
        "state_months": [s.get("month") for s in (dyn.get("samples") or [])[-12:] if isinstance(s, dict)],
    }
    payload = json.dumps(data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>CodeEvolve — {title}</title>
<style>
  :root {{ --bg:#0f1419; --fg:#e7ecf1; --muted:#8b9aab; --accent:#3dd6c6; --warn:#f0a35e; }}
  body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--fg); }}
  header {{ padding:1.5rem 2rem; border-bottom:1px solid #243041; }}
  h1 {{ margin:0; font-size:1.35rem; letter-spacing:.02em; }}
  .meta {{ color:var(--muted); margin-top:.4rem; font-size:.9rem; }}
  main {{ display:grid; grid-template-columns:1.2fr 1fr; gap:1.25rem; padding:1.25rem 2rem 2rem; }}
  section {{ background:#161d27; border:1px solid #243041; border-radius:12px; padding:1rem; }}
  h2 {{ margin:0 0 .75rem; font-size:1rem; color:var(--accent); }}
  canvas {{ width:100%; height:320px; background:linear-gradient(180deg,#121822,#0f1419); border-radius:8px; }}
  .bars {{ display:flex; align-items:flex-end; gap:6px; height:160px; }}
  .bar {{ flex:1; background:linear-gradient(180deg,var(--accent),#1f6f68); border-radius:4px 4px 0 0; min-width:8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
  td,th {{ padding:.35rem .4rem; border-bottom:1px solid #243041; text-align:left; }}
  @media (max-width:900px) {{ main {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
  <h1>CodeEvolve dashboard</h1>
  <div class="meta">{title} · stage <span id="stage"></span> · fatigue <span id="fat"></span> · stability <span id="stab"></span></div>
</header>
<main>
  <section>
    <h2>Clade map — churn × drift</h2>
    <canvas id="scatter" width="800" height="320"></canvas>
  </section>
  <section>
    <h2>Weekly intensity</h2>
    <div class="bars" id="bars"></div>
  </section>
  <section style="grid-column:1/-1">
    <h2>Clades</h2>
    <table><thead><tr><th>ID</th><th>Label</th><th>Layer</th><th>Churn</th><th>Drift</th></tr></thead>
    <tbody id="rows"></tbody></table>
  </section>
  <section style="grid-column:1/-1">
    <h2>Deliberation frames</h2>
    <div class="meta" id="dyn"></div>
    <table><thead><tr><th>Frame</th><th>Stance</th><th>Conf</th><th>Claim</th></tr></thead>
    <tbody id="frames"></tbody></table>
  </section>
</main>
<script>
const DATA = {payload};
document.getElementById('stage').textContent = DATA.stage ?? '—';
document.getElementById('fat').textContent = DATA.fatigue ?? '—';
document.getElementById('stab').textContent = (DATA.stability && DATA.stability.composite) ?? '—';
const rows = document.getElementById('rows');
for (const p of DATA.points) {{
  rows.insertAdjacentHTML('beforeend', `<tr><td>${{p.id}}</td><td>${{p.label}}</td><td>${{p.layer}}</td><td>${{p.churn}}</td><td>${{(p.drift||0).toFixed(3)}}</td></tr>`);
}}
const bars = document.getElementById('bars');
const maxI = Math.max(1, ...DATA.weekly.map(w => w.intensity || 0));
for (const w of DATA.weekly) {{
  const h = Math.max(4, Math.round(140 * ((w.intensity||0)/maxI)));
  const d = document.createElement('div');
  d.className = 'bar'; d.style.height = h + 'px'; d.title = w.week + ': ' + w.intensity;
  bars.appendChild(d);
}}
const cv = document.getElementById('scatter');
const ctx = cv.getContext('2d');
const W = cv.width, H = cv.height;
ctx.strokeStyle = '#243041'; ctx.strokeRect(40,20,W-60,H-50);
const maxC = Math.max(1, ...DATA.points.map(p => p.churn||0));
const maxD = Math.max(0.01, ...DATA.points.map(p => p.drift||0));
for (const p of DATA.points) {{
  const x = 40 + ((p.churn||0)/maxC) * (W-60);
  const y = (H-30) - ((p.drift||0)/maxD) * (H-50);
  ctx.fillStyle = '#3dd6c6';
  ctx.beginPath(); ctx.arc(x,y,6,0,Math.PI*2); ctx.fill();
  ctx.fillStyle = '#8b9aab'; ctx.font = '11px sans-serif';
  ctx.fillText(p.id, x+8, y+3);
}}
ctx.fillStyle = '#8b9aab'; ctx.fillText('churn →', W/2, H-8); ctx.save();
ctx.translate(14, H/2); ctx.rotate(-Math.PI/2); ctx.fillText('drift →', 0, 0); ctx.restore();
document.getElementById('dyn').textContent = DATA.dynamics_summary || '';
const fr = document.getElementById('frames');
for (const f of (DATA.frames || [])) {{
  fr.insertAdjacentHTML('beforeend', `<tr><td>${{f.id||''}}</td><td>${{f.stance||''}}</td><td>${{f.confidence??''}}</td><td>${{(f.claim||'').replace(/</g,'')}}</td></tr>`);
}}
</script>
</body>
</html>
"""


def write_dashboard(report: dict[str, Any], path: Path | str) -> Path:
    p = Path(path)
    p.write_text(render_dashboard(report), encoding="utf-8")
    return p
