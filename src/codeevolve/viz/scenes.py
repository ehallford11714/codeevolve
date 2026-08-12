"""SVG scenes: phylogeny DAG, clade tree, parsimony tree, gene-flow."""

from __future__ import annotations

from codeevolve.viz.colors import clade_color, stage_color
from codeevolve.viz.layout import GraphLayout, layout_circle, layout_layered_dag, layout_tree, nearest_visible_ancestor
from codeevolve.viz.model import VizModel
from codeevolve.viz.svg import Svg


def render_phylogeny_svg(model: VizModel, *, collapse_unary: bool = False) -> str:
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
        collapse_unary=collapse_unary,
        clade_of=clade_of,
    )
    svg = Svg(lay.width, lay.height, title=f"Phylogeny {model.repo}")
    for c in model.commits:
        if lay.nodes[c.sha].hidden:
            continue
        for p in c.parents:
            src = p if p in lay.nodes else next((k for k in lay.nodes if k.startswith(p[:7])), None)
            if not src or src not in lay.nodes:
                continue
            if lay.nodes[src].hidden:
                vis = nearest_visible_ancestor(c.sha, model.tree_parent, lay.hidden)
                if not vis:
                    continue
                src = vis
            a, b = lay.nodes[src], lay.nodes[c.sha]
            tree_p = model.tree_parent.get(c.sha)
            is_tree = bool(tree_p) and (src == tree_p or src.startswith(tree_p[:7]) or tree_p.startswith(src[:7]))
            svg.line(
                a.x,
                a.y,
                b.x,
                b.y,
                stroke="#f0a35e" if not is_tree else "#3a4a5c",
                dashed=not is_tree,
                width=1.6 if not is_tree else 1.15,
            )
    for c in model.commits:
        n = lay.nodes[c.sha]
        if n.hidden:
            continue
        svg.circle(
            n.x,
            n.y,
            6.5,
            fill=stage_color(c.stage),
            stroke=clade_color(c.clade_id),
            title=f"{c.sha[:7]} {c.subject}\nclade={c.clade_label or c.clade_id or '?'} stage={c.stage}",
        )
        svg.text(n.x + 9, n.y + 3.5, c.sha[:7], size=9, fill="#8b9aab")
    _legend_stages(svg, lay)
    return svg.tostring()


def render_parsimony_svg(model: VizModel, *, collapse_unary: bool = False) -> str:
    ids = [c.sha for c in model.commits]
    parents = {c.sha: ([model.tree_parent[c.sha]] if c.sha in model.tree_parent else []) for c in model.commits}
    children = {k: list(v) for k, v in model.tree_children.items()}
    generation = {c.sha: c.generation for c in model.commits}
    rec = model.parsimony.reconstructed
    clade_of = {c.sha: rec.get(c.sha) or c.clade_id for c in model.commits}
    lay = layout_layered_dag(
        ids,
        parents=parents,
        children=children,
        generation=generation,
        roots=model.roots,
        collapse_unary=collapse_unary,
        clade_of=clade_of,
    )
    svg = Svg(lay.width, lay.height, title="Fitch parsimony (clade)")
    for child, par in model.tree_parent.items():
        if child not in lay.nodes or par not in lay.nodes:
            continue
        a, b = lay.nodes[par], lay.nodes[child]
        if a.hidden or b.hidden:
            vis = nearest_visible_ancestor(child, model.tree_parent, lay.hidden)
            if not vis or vis not in lay.nodes:
                continue
            a = lay.nodes[vis]
            par = vis
        changed = rec.get(par) != rec.get(child) or (par, child) in model.parsimony.change_edges
        svg.line(a.x, a.y, b.x, b.y, stroke="#e07a9a" if changed else "#3a4a5c", width=2.2 if changed else 1.15)
    by = {c.sha: c for c in model.commits}
    for c in model.commits:
        n = lay.nodes[c.sha]
        if n.hidden:
            continue
        state = rec.get(c.sha) or c.clade_id
        svg.circle(
            n.x,
            n.y,
            6.5,
            fill=clade_color(state),
            stroke="#e07a9a" if any(e[1] == c.sha for e in model.parsimony.change_edges) else "#0f1419",
            title=f"{c.sha[:7]} reconstructed={state}\nobserved={c.clade_id or '—'}",
        )
        svg.text(n.x + 9, n.y + 3.5, (by[c.sha].clade_label or state or c.sha[:7])[:18], size=9, fill="#c5d0dc")
    p = model.parsimony
    svg.text(
        0,
        lay.height + 8,
        f"Fitch steps={p.steps}  CI={p.consistency_index}  RI={p.retention_index}  "
        f"m={p.min_steps}  extra={max(0, p.steps - p.min_steps)}  states={p.n_states}",
        size=11,
        fill="#3dd6c6",
    )
    return svg.tostring()


def render_clades_svg(model: VizModel) -> str:
    if model.hierarchy and (model.hierarchy.get("children") or model.hierarchy.get("name")):
        return _hierarchy_svg(model.hierarchy, title=f"Keyword clade tree — {model.repo}")
    return _clade_forest_svg(model)


def render_gene_flow_svg(model: VizModel) -> str:
    ids: list[str] = []
    labels: dict[str, str] = {}
    for c in model.clades:
        cid = str(c.get("id") or "")
        if cid:
            ids.append(cid)
            labels[cid] = str(c.get("label") or cid)
    for e in model.gene_flow:
        for k in ("source_clade", "target_clade"):
            cid = str(e.get(k) or "")
            if cid and cid not in labels:
                ids.append(cid)
                labels[cid] = cid
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    if not uniq:
        svg = Svg(400, 120, title="Gene flow")
        svg.text(8, 40, "No gene-flow edges in this report.", size=13, fill="#8b9aab")
        return svg.tostring()
    lay = layout_circle(uniq, cx=240, cy=240, radius=170)
    svg = Svg(lay.width, lay.height, title="Gene flow between clades")
    weights = [int(e.get("weight") or 1) for e in model.gene_flow] or [1]
    wmax = max(weights)
    cx, cy = 240.0, 240.0
    for e in model.gene_flow:
        a = str(e.get("source_clade") or "")
        b = str(e.get("target_clade") or "")
        if a not in lay.nodes or b not in lay.nodes or a == b:
            continue
        pa, pb = lay.nodes[a], lay.nodes[b]
        w = int(e.get("weight") or 1)
        d = f"M {pa.x + svg.pad:.1f} {pa.y + svg.pad:.1f} Q {cx + svg.pad:.1f} {cy + svg.pad:.1f} {pb.x + svg.pad:.1f} {pb.y + svg.pad:.1f}"
        svg.path(d, stroke=clade_color(a), width=1.0 + 4.0 * (w / wmax), opacity=0.35 + 0.5 * (w / wmax))
    for cid in uniq:
        n = lay.nodes[cid]
        svg.circle(n.x, n.y, 10, fill=clade_color(cid), stroke="#e7ecf1", title=labels.get(cid, cid))
        svg.text(n.x, n.y - 16, (labels.get(cid) or cid)[:22], size=10, fill="#e7ecf1", anchor="middle")
    return svg.tostring()


def _hierarchy_svg(node: dict, *, title: str) -> str:
    children: dict[str, list[str]] = {}
    meta: dict[str, dict] = {}

    def walk(n: dict, path: str) -> str:
        name = str(n.get("name") or "root")
        nid = path or name
        meta[nid] = n
        kids = []
        for i, ch in enumerate(n.get("children") or []):
            if isinstance(ch, dict):
                cid = walk(ch, f"{nid}/{ch.get('name') or i}")
                kids.append(cid)
        children[nid] = kids
        return nid

    root = walk(node, "")
    lay = layout_tree(children, root, x_gap=148, y_gap=20)
    svg = Svg(max(lay.width, 420), max(lay.height, 80), title=title)
    for nid, kids in children.items():
        if nid not in lay.nodes:
            continue
        a = lay.nodes[nid]
        for k in kids:
            if k not in lay.nodes:
                continue
            b = lay.nodes[k]
            svg.line(a.x, a.y, b.x, b.y, stroke="#3a4a5c")
    for nid, n in lay.nodes.items():
        info = meta.get(nid) or {}
        stage = str(info.get("ecology_stage") or "")
        label = str(info.get("name") or nid.split("/")[-1])
        count = info.get("count")
        svg.circle(n.x, n.y, 5.5, fill=stage_color(stage) if stage else "#3dd6c6", stroke="#0f1419")
        bit = f"{label}" + (f"  n={count}" if count else "")
        svg.text(n.x + 10, n.y + 3.5, bit[:42], size=10, fill="#e7ecf1")
    return svg.tostring()


def _clade_forest_svg(model: VizModel) -> str:
    children: dict[str, list[str]] = {"clades": []}
    meta: dict[str, dict] = {"clades": {"name": "clades", "count": len(model.clades)}}
    for c in model.clades:
        cid = str(c.get("id") or "")
        if not cid:
            continue
        children["clades"].append(cid)
        children[cid] = []
        meta[cid] = {"name": c.get("label") or cid, "count": c.get("touch_count") or len(c.get("files") or []), "ecology_stage": ""}
    lay = layout_tree(children, "clades")
    svg = Svg(max(lay.width, 360), max(lay.height, 80), title="Clades")
    for nid, kids in children.items():
        if nid not in lay.nodes:
            continue
        a = lay.nodes[nid]
        for k in kids:
            if k in lay.nodes:
                svg.line(a.x, a.y, lay.nodes[k].x, lay.nodes[k].y, stroke="#3a4a5c")
    for nid, n in lay.nodes.items():
        info = meta.get(nid) or {}
        fill = clade_color(nid) if nid != "clades" else "#8b9aab"
        svg.circle(n.x, n.y, 6, fill=fill)
        svg.text(n.x + 10, n.y + 3.5, f"{info.get('name') or nid}  n={info.get('count') or 0}"[:40], size=10)
    return svg.tostring()


def _legend_stages(svg: Svg, lay: GraphLayout) -> None:
    from codeevolve.viz.colors import STAGE_COLORS

    x = 0.0
    y = lay.height + 18
    svg.text(x, y, "stage", size=9, fill="#8b9aab")
    x += 40
    for name, color in STAGE_COLORS.items():
        svg.circle(x, y - 3, 5, fill=color, stroke="#0f1419", sw=1)
        svg.text(x + 8, y, name, size=9, fill="#8b9aab")
        x += 78
