"""Layered DAG, tidy tree, and circular layouts (no extra deps)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class LaidOut:
    id: str
    x: float
    y: float
    z: float = 0.0
    depth: int = 0
    hidden: bool = False


@dataclass
class GraphLayout:
    nodes: dict[str, LaidOut]
    width: float
    height: float
    hidden: set[str] = field(default_factory=set)
    pad: float = 36.0

    def visible(self) -> list[LaidOut]:
        return [n for n in self.nodes.values() if not n.hidden]


def layout_layered_dag(
    node_ids: list[str],
    *,
    parents: dict[str, list[str]],
    children: dict[str, list[str]],
    generation: dict[str, int],
    roots: list[str],
    x_gap: float = 92.0,
    y_gap: float = 28.0,
    collapse_unary: bool = False,
    clade_of: dict[str, str] | None = None,
    order_of: dict[str, str] | None = None,
    max_visible: int = 480,
) -> GraphLayout:
    """Place commits on a generation × DFS-order grid.

    Extra parents (merges) are ignored for y-order; callers still draw them.
    Unary chains with a stable semantic type can be collapsed for large histories.
    """
    id_set = set(node_ids)
    hidden: set[str] = set()
    if collapse_unary:
        hidden = _unary_collapse(node_ids, parents, children, clade_of)

    order = _dfs_order(node_ids, children, roots, order_key=order_of or clade_of)
    if len(order) - len(hidden) > max_visible:
        # keep roots, leaves, merges, and a stride sample of the rest
        keep = _priority_keep(node_ids, parents, children, roots, max_visible)
        hidden |= {i for i in node_ids if i not in keep}

    y_rank: dict[str, int] = {}
    rank = 0
    for nid in order:
        if nid in hidden:
            continue
        y_rank[nid] = rank
        rank += 1
    if not y_rank:
        for nid in node_ids:
            y_rank[nid] = 0
            hidden.discard(nid)

    max_gen = max((generation.get(i, 0) for i in node_ids), default=0)
    laid: dict[str, LaidOut] = {}
    for nid in node_ids:
        gen = generation.get(nid, 0)
        yr = y_rank.get(nid, 0)
        laid[nid] = LaidOut(
            id=nid,
            x=gen * x_gap,
            y=yr * y_gap,
            depth=gen,
            hidden=nid in hidden,
        )
    width = max_gen * x_gap + 80
    height = max(y_gap, (max(y_rank.values(), default=0) + 1) * y_gap)
    return GraphLayout(nodes=laid, width=width, height=height, hidden=hidden)


def layout_tree(
    children: dict[str, list[str]],
    root: str,
    *,
    x_gap: float = 150.0,
    y_gap: float = 22.0,
) -> GraphLayout:
    """Simple tidy tree: leaves get sequential y; internals sit at the mean."""
    y_leaf = [0]
    pos: dict[str, tuple[float, float, int]] = {}

    def walk(nid: str, depth: int) -> float:
        kids = [c for c in (children.get(nid) or []) if c]
        if not kids:
            y = y_leaf[0]
            y_leaf[0] += 1
            pos[nid] = (depth * x_gap, y * y_gap, depth)
            return y
        ys = [walk(c, depth + 1) for c in kids]
        y = sum(ys) / len(ys)
        pos[nid] = (depth * x_gap, y * y_gap, depth)
        return y

    if root:
        walk(root, 0)
    laid = {
        nid: LaidOut(id=nid, x=x, y=y, depth=d, hidden=False)
        for nid, (x, y, d) in pos.items()
    }
    width = max((n.x for n in laid.values()), default=0) + 80
    height = max((n.y for n in laid.values()), default=0) + y_gap
    return GraphLayout(nodes=laid, width=width, height=height)


def layout_circle(
    ids: list[str],
    *,
    cx: float = 220.0,
    cy: float = 220.0,
    radius: float = 160.0,
) -> GraphLayout:
    n = max(1, len(ids))
    laid: dict[str, LaidOut] = {}
    for i, nid in enumerate(ids):
        ang = (2 * math.pi * i / n) - math.pi / 2
        laid[nid] = LaidOut(
            id=nid,
            x=cx + radius * math.cos(ang),
            y=cy + radius * math.sin(ang),
            depth=0,
        )
    return GraphLayout(nodes=laid, width=cx * 2, height=cy * 2)


def layout_phylogeny_3d(
    node_ids: list[str],
    *,
    parents: dict[str, list[str]],
    children: dict[str, list[str]],
    generation: dict[str, int],
    roots: list[str],
    z_of: dict[str, float],
    collapse_unary: bool = False,
    clade_of: dict[str, str] | None = None,
    x_gap: float = 92.0,
    y_gap: float = 28.0,
    z_scale: float = 48.0,
) -> GraphLayout:
    """Generation × lineage × analysis/intent. ``z_of`` is already in world units or 0..n ranks."""
    lay = layout_layered_dag(
        node_ids,
        parents=parents,
        children=children,
        generation=generation,
        roots=roots,
        x_gap=x_gap,
        y_gap=y_gap,
        collapse_unary=collapse_unary,
        clade_of=clade_of,
        order_of=clade_of,
    )
    zmax = 0.0
    for nid, n in lay.nodes.items():
        n.z = float(z_of.get(nid, 0.0)) * z_scale
        zmax = max(zmax, abs(n.z))
    lay.width = max(lay.width, zmax + 80)
    return lay


def nearest_visible_ancestor(nid: str, parent: dict[str, str], hidden: set[str]) -> str | None:
    cur = parent.get(nid)
    while cur is not None:
        if cur not in hidden:
            return cur
        cur = parent.get(cur)
    return None


def _dfs_order(
    node_ids: list[str],
    children: dict[str, list[str]],
    roots: list[str],
    order_key: dict[str, str] | None = None,
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    id_set = set(node_ids)

    def visit(nid: str) -> None:
        if nid in seen or nid not in id_set:
            return
        seen.add(nid)
        out.append(nid)
        kids = [c for c in (children.get(nid) or []) if c]
        if order_key:
            kids.sort(key=lambda c: (order_key.get(c) or "", c))
        for ch in kids:
            visit(ch)

    for r in roots:
        visit(r)
    for nid in node_ids:
        visit(nid)
    return out


def _unary_collapse(
    node_ids: list[str],
    parents: dict[str, list[str]],
    children: dict[str, list[str]],
    clade_of: dict[str, str] | None,
) -> set[str]:
    hidden: set[str] = set()
    id_set = set(node_ids)
    for nid in node_ids:
        pars = [p for p in (parents.get(nid) or []) if p in id_set]
        kids = [c for c in (children.get(nid) or []) if c in id_set]
        if len(pars) != 1 or len(kids) != 1:
            continue
        if clade_of:
            mine = clade_of.get(nid) or ""
            if mine and (clade_of.get(pars[0]) != mine or clade_of.get(kids[0]) != mine):
                continue
        hidden.add(nid)
    return hidden


def _priority_keep(
    node_ids: list[str],
    parents: dict[str, list[str]],
    children: dict[str, list[str]],
    roots: list[str],
    budget: int,
) -> set[str]:
    id_set = set(node_ids)
    keep: set[str] = set(roots)
    for nid in node_ids:
        pars = [p for p in (parents.get(nid) or []) if p in id_set]
        kids = [c for c in (children.get(nid) or []) if c in id_set]
        if len(pars) > 1 or len(kids) != 1 or not kids:
            keep.add(nid)
    if len(keep) >= budget:
        return set(list(keep)[:budget])
    remaining = [i for i in node_ids if i not in keep]
    stride = max(1, len(remaining) // max(1, budget - len(keep)))
    for i, nid in enumerate(remaining):
        if i % stride == 0:
            keep.add(nid)
            if len(keep) >= budget:
                break
    return keep
