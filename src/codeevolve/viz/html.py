"""HTML gallery wrapping 3D builder + phylogeny / clade / parsimony / gene-flow SVGs."""

from __future__ import annotations

from html import escape as _esc

from codeevolve.viz.builder import render_builder_inner
from codeevolve.viz.model import VizModel
from codeevolve.viz.newick import to_newick
from codeevolve.viz.scenes import (
    render_clades_svg,
    render_gene_flow_svg,
    render_parsimony_svg,
    render_phylogeny_svg,
)

SVG_KINDS = ("phylogeny", "clades", "parsimony", "gene-flow")
KINDS = ("3d",) + SVG_KINDS


def scene_svg(model: VizModel, kind: str, *, collapse_unary: bool = False) -> str:
    if kind in {"3d", "builder"}:
        return ""
    if kind == "clades":
        return render_clades_svg(model)
    if kind == "parsimony":
        return render_parsimony_svg(model, collapse_unary=collapse_unary)
    if kind in {"gene-flow", "gene_flow"}:
        return render_gene_flow_svg(model)
    return render_phylogeny_svg(model, collapse_unary=collapse_unary)


def newick_of(model: VizModel) -> str:
    labels = {c.sha: f"{c.sha[:7]}_{c.clade_id}" if c.clade_id else c.sha[:7] for c in model.commits}
    return to_newick(model.tree_children, model.roots, labels)


def render_gallery(model: VizModel, *, collapse_unary: bool = False) -> str:
    title = _esc(model.repo or "repo")
    p = model.parsimony
    trunc = " · phylogeny.nodes capped in JSON — re-run analyze --viz-out for the full DAG" if model.truncated else ""
    stats = (
        f"{model.node_count} commits · gen {model.max_generation} · "
        f"merges {model.merge_count} · branch-factor {model.branch_factor} · "
        f"stage {model.current_stage} · Fitch steps {p.steps} (CI {p.consistency_index}, RI {p.retention_index})"
        f"{trunc}"
    )
    panels = []
    radios = []
    labels = []
    names = {
        "3d": "3D builder",
        "phylogeny": "Phylogeny",
        "clades": "Clades",
        "parsimony": "Parsimony",
        "gene-flow": "Gene flow",
    }
    for i, kind in enumerate(KINDS):
        checked = " checked" if i == 0 else ""
        radios.append(f'<input type="radio" name="viztab" id="tab-{kind}"{checked}/>')
        labels.append(f'<label for="tab-{kind}">{names[kind]}</label>')
        if kind == "3d":
            panels.append(f'<section class="panel" id="panel-{kind}">{render_builder_inner(model)}</section>')
        else:
            svg = scene_svg(model, kind, collapse_unary=collapse_unary)
            panels.append(f'<section class="panel" id="panel-{kind}">{svg}</section>')
    nwk = _esc(newick_of(model))
    radio_css = "\n".join(
        f"#tab-{k}:checked ~ .wrap #panel-{k} {{ display:block; }}\n"
        f"#tab-{k}:checked ~ nav label[for='tab-{k}'] {{ color:var(--accent); border-bottom-color:var(--accent); }}"
        for k in KINDS
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>CodeEvolve phylogeny — {title}</title>
<style>
  :root {{ --bg:#0f1419; --fg:#e7ecf1; --muted:#8b9aab; --accent:#3dd6c6; --card:#161d27; --line:#243041; }}
  body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--fg); }}
  header {{ padding:1.25rem 1.75rem 0.75rem; border-bottom:1px solid var(--line); }}
  h1 {{ margin:0; font-size:1.25rem; }}
  .meta {{ color:var(--muted); margin-top:.4rem; font-size:.88rem; max-width:90rem; }}
  input[type=radio] {{ display:none; }}
  nav {{ display:flex; gap:0; padding:0 1.75rem; border-bottom:1px solid var(--line); }}
  nav label {{ padding:.7rem 1rem; cursor:pointer; color:var(--muted); border-bottom:2px solid transparent; }}
  .wrap {{ padding:1rem 1.5rem 2rem; }}
  .panel {{ display:none; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:.75rem; overflow:auto; max-height:78vh; }}
  {radio_css}
  details {{ margin:1rem 1.75rem 2rem; color:var(--muted); }}
  pre {{ white-space:pre-wrap; word-break:break-all; background:#121822; padding:1rem; border-radius:8px; color:var(--fg); font-size:.78rem; }}
  .hint {{ font-size:.8rem; color:var(--muted); margin:0 1.75rem 1rem; }}
</style>
</head>
<body>
{''.join(radios)}
<header>
  <h1>CodeEvolve phylogeny</h1>
  <div class="meta">{title} · { _esc(stats) }</div>
</header>
<nav>{''.join(labels)}</nav>
<p class="hint">3D builder: X = generation, Y = lineage, Z = intent / clade / analysis / stage.
Color and Z are switchable. Intent is classified from the commit subject (insufficient if silent).
Click a node for analysis + deliberation frames. 2D tabs: fill = stage or reconstructed clade; dashed orange = merges; pink = Fitch changes.</p>
<div class="wrap">{''.join(panels)}</div>
<details>
  <summary>Newick (first-parent spanning tree)</summary>
  <pre>{nwk}</pre>
</details>
</body>
</html>
"""
