"""Newick export of a spanning phylogeny tree."""

from __future__ import annotations

import re

_BAD = re.compile(r"[(),:;\s\[\]]+")


def nwk_escape(name: str) -> str:
    s = _BAD.sub("_", (name or "").strip()) or "n"
    return s[:48]


def to_newick(
    children: dict[str, list[str]],
    roots: list[str],
    labels: dict[str, str] | None = None,
    *,
    lengths: dict[str, float] | None = None,
) -> str:
    """Serialize a rooted forest. Multiple roots are wrapped as ``(r1,r2)root``."""
    labels = labels or {}
    lengths = lengths or {}

    def rec(nid: str) -> str:
        kids = children.get(nid) or []
        name = nwk_escape(labels.get(nid) or nid[:7])
        length = lengths.get(nid)
        tail = f":{length:g}" if length is not None else ""
        if not kids:
            return f"{name}{tail}"
        inner = ",".join(rec(c) for c in kids)
        return f"({inner}){name}{tail}"

    usable = [r for r in roots if r]
    if not usable:
        return ";"
    if len(usable) == 1:
        return rec(usable[0]) + ";"
    inner = ",".join(rec(r) for r in usable)
    return f"({inner})root;"
