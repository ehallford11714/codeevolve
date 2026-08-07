"""Temporal / change coupling (co-change + ticket-id coupling)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.gitlog import CommitRecord

_TICKET_RE = re.compile(
    r"(?:#(\d+)|(?:JIRA|TICKET|ISSUE|GH|PR)[-_ ]?(\d+)|([A-Z]{2,10}-\d+))",
    re.I,
)


@dataclass
class CouplingEdge:
    a: str
    b: str
    weight: int
    kind: str  # commit | ticket

    def to_dict(self) -> dict[str, Any]:
        return {"a": self.a, "b": self.b, "weight": self.weight, "kind": self.kind}


@dataclass
class CouplingReport:
    edges: list[CouplingEdge] = field(default_factory=list)
    sum_of_coupling: dict[str, int] = field(default_factory=dict)
    ticket_groups: list[dict[str, Any]] = field(default_factory=list)
    filtered_large_commits: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": [e.to_dict() for e in self.edges[:80]],
            "edge_count": len(self.edges),
            "sum_of_coupling": dict(list(self.sum_of_coupling.items())[:40]),
            "ticket_groups": list(self.ticket_groups[:30]),
            "filtered_large_commits": self.filtered_large_commits,
            "summary": self.summary,
        }


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _tickets(c: CommitRecord) -> list[str]:
    blob = f"{c.subject}\n{c.body}"
    out: list[str] = []
    for m in _TICKET_RE.finditer(blob):
        if m.group(3):
            out.append(m.group(3).upper())
        else:
            num = m.group(1) or m.group(2)
            if num:
                out.append(f"#{num}")
    return list(dict.fromkeys(out))


def analyze_coupling(
    commits: list[CommitRecord],
    *,
    max_files_per_commit: int = 12,
    min_weight: int = 2,
) -> CouplingReport:
    """Build co-change coupling with large-commit filter + ticket coupling."""
    pair_w: dict[tuple[str, str], int] = defaultdict(int)
    filtered = 0
    ticket_files: dict[str, set[str]] = defaultdict(set)

    for c in commits:
        files = [f for f in c.files if f][:80]
        churn = c.insertions + c.deletions
        # Large-commit filter (CodeScene-style): skip noisy mega-changesets
        if len(files) > max_files_per_commit or churn > 2500:
            filtered += 1
        else:
            uniq = sorted(set(files))
            for i, a in enumerate(uniq):
                for b in uniq[i + 1 :]:
                    pair_w[_pair_key(a, b)] += 1

        for t in _tickets(c):
            for f in files[:40]:
                ticket_files[t].add(f)

    ticket_pair_w: dict[tuple[str, str], int] = defaultdict(int)
    ticket_groups: list[dict[str, Any]] = []
    for t, fs in ticket_files.items():
        fl = sorted(fs)
        if len(fl) < 2:
            continue
        ticket_groups.append({"ticket": t, "files": fl[:20], "file_count": len(fl)})
        for i, a in enumerate(fl[:30]):
            for b in fl[i + 1 : 30]:
                ticket_pair_w[_pair_key(a, b)] += 1

    edges: list[CouplingEdge] = []
    soc: dict[str, int] = defaultdict(int)
    for (a, b), w in pair_w.items():
        if w < min_weight:
            continue
        edges.append(CouplingEdge(a, b, w, "commit"))
        soc[a] += w
        soc[b] += w
    for (a, b), w in ticket_pair_w.items():
        if w < min_weight:
            continue
        edges.append(CouplingEdge(a, b, w, "ticket"))
        soc[a] += w
        soc[b] += w

    edges.sort(key=lambda e: (-e.weight, e.kind, e.a))
    ticket_groups.sort(key=lambda g: -g["file_count"])
    top = ", ".join(f"{e.a}↔{e.b}({e.weight})" for e in edges[:3]) or "none"
    return CouplingReport(
        edges=edges,
        sum_of_coupling=dict(sorted(soc.items(), key=lambda x: -x[1])),
        ticket_groups=ticket_groups,
        filtered_large_commits=filtered,
        summary=f"{len(edges)} coupling edges (filtered {filtered} large commits); top {top}",
    )
