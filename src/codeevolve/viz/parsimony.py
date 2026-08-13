"""Fitch parsimony on a spanning tree (unordered characters).

Default phylogeny character is the commit's semantic type_path (keyword
ontology), falling back to dominant clade when types are silent. Tips drive
the Fitch down-pass; when internals are also coded, tree length is the count
of first-parent edges whose observed states differ.

Consistency index CI = m / s  (m = n_states − 1, s = observed steps).
Retention index RI = (g − s) / (g − m)  (g = n_coded − f_max).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsimonyResult:
    steps: int
    min_steps: int
    max_steps: int
    consistency_index: float
    retention_index: float
    n_states: int
    n_terminals: int
    reconstructed: dict[str, str]
    sets: dict[str, list[str]]
    change_edges: list[tuple[str, str]]
    character: str = "clade"
    method: str = "fitch"

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "character": self.character,
            "steps": self.steps,
            "min_steps": self.min_steps,
            "max_steps": self.max_steps,
            "consistency_index": self.consistency_index,
            "retention_index": self.retention_index,
            "n_states": self.n_states,
            "n_terminals": self.n_terminals,
            "homoplasy_extra": max(0, self.steps - self.min_steps),
            "reconstructed": dict(self.reconstructed),
            "change_edges": [{"parent": a, "child": b} for a, b in self.change_edges],
        }


def indices(steps: int, states: list[str]) -> tuple[int, int, float, float, int, int]:
    counts = Counter(s for s in states if s)
    n_states = len(counts)
    n_term = len(states)
    m = max(0, n_states - 1)
    g = max(m, n_term - (max(counts.values()) if counts else 0))
    s = steps
    if s == 0:
        ci = 1.0
    else:
        ci = round(m / s, 4) if s else 1.0
    ri = 1.0 if g == m else round((g - s) / (g - m), 4)
    return m, g, max(0.0, min(1.0, ci)), max(0.0, min(1.0, ri)), n_states, n_term


def observed_tree_length(
    parent: dict[str, str],
    states: dict[str, str],
) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for child, par in parent.items():
        a = (states.get(par) or "").strip()
        b = (states.get(child) or "").strip()
        if a and b and a != b:
            edges.append((par, child))
    return edges


def fitch_parsimony(
    children: dict[str, list[str]],
    roots: list[str],
    leaf_state: dict[str, str],
    *,
    character: str = "clade",
) -> ParsimonyResult:
    """Unordered Fitch on a rooted forest. ``leaf_state`` may omit internals."""
    post = _postorder(children, roots)
    sets: dict[str, set[str]] = {}
    steps = 0
    parent_of = _parents_from_children(children)

    for nid in post:
        kids = list(children.get(nid) or [])
        if not kids:
            st = (leaf_state.get(nid) or "").strip()
            sets[nid] = {st} if st else set()
            continue
        known = []
        for ch in kids:
            cs = sets.get(ch)
            if cs is None:
                st = (leaf_state.get(ch) or "").strip()
                cs = {st} if st else set()
                sets[ch] = cs
            if cs:
                known.append(cs)
        if not known:
            st = (leaf_state.get(nid) or "").strip()
            sets[nid] = {st} if st else set()
            continue
        inter = set.intersection(*known)
        if inter:
            sets[nid] = inter
        else:
            sets[nid] = set.union(*known)
            steps += 1

    reconstructed: dict[str, str] = {}
    pre = list(reversed(post))
    for nid in pre:
        opts = sets.get(nid) or set()
        if not opts:
            reconstructed[nid] = (leaf_state.get(nid) or "") or "?"
            continue
        p = parent_of.get(nid)
        if p and reconstructed.get(p) in opts:
            reconstructed[nid] = reconstructed[p]
        else:
            observed = (leaf_state.get(nid) or "").strip()
            reconstructed[nid] = observed if observed in opts else sorted(opts)[0]

    change_edges: list[tuple[str, str]] = []
    for child, par in parent_of.items():
        a = reconstructed.get(par) or ""
        b = reconstructed.get(child) or ""
        if a and b and a != b and a != "?" and b != "?":
            change_edges.append((par, child))

    obs = observed_tree_length(parent_of, leaf_state)
    if obs:
        change_edges = obs
        steps = len(obs)

    coded = [s for s in leaf_state.values() if (s or "").strip()]
    m, g, ci, ri, n_states, n_term = indices(steps, coded)

    return ParsimonyResult(
        steps=steps,
        min_steps=m,
        max_steps=g,
        consistency_index=ci,
        retention_index=ri,
        n_states=n_states,
        n_terminals=n_term,
        reconstructed=reconstructed,
        sets={k: sorted(v) for k, v in sets.items()},
        change_edges=change_edges,
        character=character,
    )


def spanning_tree(
    nodes: list[dict[str, Any]],
    roots: list[str],
) -> tuple[dict[str, list[str]], dict[str, str], list[str]]:
    """First-parent tree of a commit DAG. Returns children, parent, roots."""
    by_sha = {str(n.get("sha") or ""): n for n in nodes if n.get("sha")}
    short = {sha[:7]: sha for sha in by_sha}

    def resolve(p: str) -> str | None:
        if p in by_sha:
            return p
        return short.get((p or "")[:7])

    parent: dict[str, str] = {}
    children: dict[str, list[str]] = defaultdict(list)
    for sha, n in by_sha.items():
        pars = [resolve(str(p)) for p in (n.get("parent_shas") or n.get("parents") or [])]
        pars = [p for p in pars if p]
        if pars:
            parent[sha] = pars[0]
            children[pars[0]].append(sha)

    tree_roots = [r for r in roots if r in by_sha] or [s for s in by_sha if s not in parent]
    if not tree_roots and by_sha:
        tree_roots = [next(iter(by_sha))]
    return dict(children), parent, tree_roots


def _postorder(children: dict[str, list[str]], roots: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def visit(nid: str) -> None:
        if nid in seen:
            return
        seen.add(nid)
        for ch in children.get(nid) or []:
            visit(ch)
        out.append(nid)

    for r in roots:
        visit(r)
    for nid in list(children):
        visit(nid)
        for ch in children.get(nid) or []:
            visit(ch)
    return out


def _parents_from_children(children: dict[str, list[str]]) -> dict[str, str]:
    parent: dict[str, str] = {}
    for p, kids in children.items():
        for c in kids:
            parent.setdefault(c, p)
    return parent
