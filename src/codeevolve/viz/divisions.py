"""Semantic taxonomy divisions for phylogeny splits.

Each commit is a vote over allocated paths: keyword ``type_path``
(domain/family/kind/specialty) plus optional semantic niche. Fitch at
each ontology depth reconstructs the taxon on every internal division.
Silent paths stay unlabeled — we do not invent a type.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from codeevolve.viz.parsimony import ParsimonyResult, fitch_parsimony


@dataclass
class SemanticDivision:
    type_path: list[str] = field(default_factory=list)
    type_key: str = ""
    niche_id: str = ""
    niche_label: str = ""
    key: str = ""
    source: str = "insufficient"

    def prefix(self, depth: int) -> str:
        if not self.type_path:
            return self.key
        return "/".join(self.type_path[: max(1, depth)])


def path_type_lookup(tax: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    kw = tax.get("keyword_taxonomy") or {}
    if isinstance(kw, dict):
        for path, hit in (kw.get("path_types") or {}).items():
            tp: list[str] = []
            if isinstance(hit, dict):
                raw = hit.get("type_path") or []
                tp = [str(x) for x in raw if x]
                if not tp and hit.get("type_key"):
                    tp = [p for p in str(hit["type_key"]).split("/") if p]
            if tp and tp != ["unknown"]:
                out[str(path)] = tp
    for c in tax.get("clades") or []:
        if not isinstance(c, dict):
            continue
        tp = [str(x) for x in (c.get("type_path") or []) if x]
        if not tp and c.get("code_type"):
            tp = [p for p in str(c.get("code_type")).split("/") if p]
        for f in c.get("files") or []:
            out.setdefault(str(f), tp)
    return out


def niche_lookup(tax: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    sem = tax.get("semantic") or {}
    if not isinstance(sem, dict):
        return {}, {}
    path_to = {str(k): str(v) for k, v in (sem.get("path_to_niche") or {}).items() if k and v}
    labels: dict[str, str] = {}
    for n in sem.get("niches") or []:
        if isinstance(n, dict) and n.get("id"):
            labels[str(n["id"])] = str(n.get("label") or n["id"])
    return path_to, labels


def divisions_by_sha(
    allocations: list[dict[str, Any]],
    *,
    path_types: dict[str, list[str]],
    path_to_niche: dict[str, str],
    niche_labels: dict[str, str],
    clade_types: dict[str, list[str]],
) -> dict[str, SemanticDivision]:
    type_votes: dict[str, Counter[str]] = {}
    niche_votes: dict[str, Counter[str]] = {}
    clade_votes: dict[str, Counter[str]] = {}
    for a in allocations:
        sha = str(a.get("sha") or "")
        path = str(a.get("path") or "")
        cid = str(a.get("clade_id") or "")
        if not sha:
            continue
        w = int(a.get("insertions") or 0) + int(a.get("deletions") or 0) or 1
        tp = path_types.get(path) or (clade_types.get(cid) if cid else None)
        if tp:
            type_votes.setdefault(sha, Counter())["/".join(tp)] += w
        nid = path_to_niche.get(path) or ""
        if nid:
            niche_votes.setdefault(sha, Counter())[nid] += w
        if cid:
            clade_votes.setdefault(sha, Counter())[cid] += w

    out: dict[str, SemanticDivision] = {}
    shas = set(type_votes) | set(niche_votes) | set(clade_votes)
    for sha in shas:
        type_key = type_votes[sha].most_common(1)[0][0] if sha in type_votes else ""
        niche_id = niche_votes[sha].most_common(1)[0][0] if sha in niche_votes else ""
        clade_id = clade_votes[sha].most_common(1)[0][0] if sha in clade_votes else ""
        type_path = [p for p in type_key.split("/") if p] if type_key else []
        if type_key:
            key, source = type_key, "keyword"
        elif niche_id:
            key, source = niche_id, "niche"
        elif clade_id:
            key, source = clade_id, "clade"
        else:
            key, source = "", "insufficient"
        out[sha] = SemanticDivision(
            type_path=type_path,
            type_key=type_key,
            niche_id=niche_id,
            niche_label=niche_labels.get(niche_id, niche_id),
            key=key,
            source=source,
        )
    return out


def fitch_by_depth(
    children: dict[str, list[str]],
    roots: list[str],
    divisions: dict[str, SemanticDivision],
    *,
    max_depth: int = 4,
) -> dict[int, ParsimonyResult]:
    """Fitch on type_path prefixes so each ontology rank is a tree character."""
    deepest = max((len(d.type_path) for d in divisions.values()), default=0)
    n = min(max_depth, max(1, deepest))
    out: dict[int, ParsimonyResult] = {}
    for depth in range(1, n + 1):
        states = {}
        for sha, div in divisions.items():
            pref = div.prefix(depth)
            if pref:
                states[sha] = pref
        if not states:
            continue
        out[depth] = fitch_parsimony(
            children,
            roots,
            states,
            character=f"type_path:{depth}",
        )
    return out
