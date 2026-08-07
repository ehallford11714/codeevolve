"""Reticulate phylogeny via AST / token fingerprint distances."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.gitlog import CommitRecord, show_file_at

_TOKEN_RE = re.compile(r"[A-Za-z_][\w]*|[(){}\[\];]|==|!=|<=|>=|&&|\|\||.")


@dataclass
class ReticulationReport:
    edges: list[dict[str, Any]] = field(default_factory=list)
    distance_samples: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": list(self.edges[:40]),
            "distance_samples": list(self.distance_samples[:40]),
            "summary": self.summary,
        }


def _fingerprint(text: str) -> list[str]:
    """AST-lite fingerprint: identifier stems + structure tokens."""
    toks = []
    for t in _TOKEN_RE.findall(text[:12_000]):
        if t.isidentifier():
            # stem-ish: drop trailing digits
            toks.append(re.sub(r"\d+$", "", t.lower())[:24])
        elif t in {"(", ")", "{", "}", "[", "]", ";", "==", "!=", "&&", "||"}:
            toks.append(t)
    # bag-of-shingles
    if len(toks) < 8:
        return toks
    shingles = []
    for i in range(0, min(len(toks) - 2, 400)):
        shingles.append("|".join(toks[i : i + 3]))
    return shingles


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def analyze_reticulation(
    repo: Path | str,
    commits: list[CommitRecord],
    *,
    max_paths: int = 30,
    min_similarity: float = 0.55,
) -> ReticulationReport:
    """Find non-vertical similarity edges (imports / copy merges)."""
    if not commits:
        return ReticulationReport(summary="No commits")

    ordered = sorted(commits, key=lambda c: c.timestamp)
    touches: dict[str, int] = defaultdict(int)
    for c in ordered:
        for f in c.files:
            if Path(f).suffix.lower() in {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"}:
                touches[f] += 1
    paths = [p for p, _ in sorted(touches.items(), key=lambda x: -x[1])[:max_paths]]
    head = ordered[-1].sha
    mid = ordered[len(ordered) // 2].sha if len(ordered) > 2 else head

    fps: dict[str, list[str]] = {}
    for path in paths:
        text = show_file_at(repo, head, path) or show_file_at(repo, mid, path)
        if text:
            fps[path] = _fingerprint(text)

    edges: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    keys = list(fps.keys())
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            sim = _jaccard(fps[a], fps[b])
            dist = round(1.0 - sim, 4)
            if sim < 0.25:
                continue
            samples.append({"a": a, "b": b, "similarity": round(sim, 4), "distance": dist})
            # Reticulation suspect: high similarity but different path prefixes / layers
            same_dir = Path(a).parent == Path(b).parent
            if sim >= min_similarity and not same_dir:
                edges.append(
                    {
                        "a": a,
                        "b": b,
                        "similarity": round(sim, 4),
                        "kind": "reticulation",
                        "note": "High AST-lite similarity across directories — possible import/copy",
                    }
                )

    # Also compare mid vs head of same path for vertical distance baseline
    for path in paths[:15]:
        t0 = show_file_at(repo, mid, path)
        t1 = show_file_at(repo, head, path)
        if not t0 or not t1:
            continue
        sim = _jaccard(_fingerprint(t0), _fingerprint(t1))
        samples.append(
            {
                "a": f"{path}@mid",
                "b": f"{path}@head",
                "similarity": round(sim, 4),
                "distance": round(1.0 - sim, 4),
                "kind": "vertical",
            }
        )

    edges.sort(key=lambda e: -e["similarity"])
    samples.sort(key=lambda s: -s["similarity"])
    return ReticulationReport(
        edges=edges,
        distance_samples=samples,
        summary=f"{len(edges)} reticulation edges; {len(samples)} distance samples",
    )


def fingerprint_hash(text: str) -> str:
    return hashlib.sha1("|".join(_fingerprint(text)).encode()).hexdigest()[:16]
