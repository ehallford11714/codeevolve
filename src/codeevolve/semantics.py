"""Semantic trends + hierarchy taxonomy via embeddings."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.embeddings import cosine, embed_text, mean_embed
from codeevolve.gitlog import CommitRecord


# Hierarchy levels for path taxonomy
LAYER_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("tests", re.compile(r"(^|/)(tests?|spec|__tests__)(/|$)", re.I)),
    ("docs", re.compile(r"(^|/)(docs?|documentation)(/|$)", re.I)),
    ("ci", re.compile(r"(^|/)(\.github|\.gitlab|ci|scripts)(/|$)", re.I)),
    ("frontend", re.compile(r"(^|/)(frontend|web|ui|client|src/components)(/|$)", re.I)),
    ("backend", re.compile(r"(^|/)(backend|server|api|services)(/|$)", re.I)),
    ("core", re.compile(r"(^|/)(src|lib|core|pkg)(/|$)", re.I)),
    ("config", re.compile(r"(^|/)(\.env|config|deploy|infra|ops)(/|$)", re.I)),
    ("deps", re.compile(r"(package\.json|pyproject|requirements|Cargo\.toml|go\.mod)", re.I)),
]


THEME_PROTOTYPES = {
    "feature": "add implement feature new support introduce capability",
    "fix": "fix bugfix patch resolve crash error regression",
    "refactor": "refactor cleanup restructure rename simplify modular",
    "docs": "docs documentation readme comment changelog",
    "test": "test coverage unit e2e assert mock fixture",
    "chore": "chore deps dependency bump ci build release version",
    "perf": "perf performance optimize speed memory latency",
    "security": "security auth vulnerability cve sanitize privilege",
}


@dataclass
class TaxonomyNode:
    name: str
    count: int = 0
    children: dict[str, "TaxonomyNode"] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "children": [c.to_dict() for c in sorted(self.children.values(), key=lambda x: -x.count)],
        }


@dataclass
class SemanticReport:
    theme_distribution: dict[str, float]
    theme_timeline: list[dict[str, Any]]
    hierarchy: dict[str, Any]
    semantic_drift: float
    cluster_labels: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme_distribution": dict(self.theme_distribution),
            "theme_timeline": list(self.theme_timeline),
            "hierarchy": self.hierarchy,
            "semantic_drift": self.semantic_drift,
            "cluster_labels": list(self.cluster_labels),
        }


def _layer_for_path(path: str) -> str:
    for name, pat in LAYER_RULES:
        if pat.search(path):
            return name
    return "other"


def _theme_for_text(text: str) -> str:
    v = embed_text(text)
    best, score = "chore", -1.0
    for theme, proto in THEME_PROTOTYPES.items():
        s = cosine(v, embed_text(proto))
        if s > score:
            best, score = theme, s
    return best


def build_hierarchy(commits: list[CommitRecord]) -> TaxonomyNode:
    root = TaxonomyNode(name="repo")
    for c in commits:
        for path in c.files or ["(unknown)"]:
            layer = _layer_for_path(path)
            parts = path.replace("\\", "/").split("/")
            top = parts[0] if parts else "(root)"
            root.count += 1
            if layer not in root.children:
                root.children[layer] = TaxonomyNode(name=layer)
            node = root.children[layer]
            node.count += 1
            if top not in node.children:
                node.children[top] = TaxonomyNode(name=top)
            node.children[top].count += 1
    return root


def analyze_semantics(commits: list[CommitRecord], *, buckets: int = 8) -> SemanticReport:
    if not commits:
        return SemanticReport({}, [], TaxonomyNode("repo").to_dict(), 0.0, [])

    themes: dict[str, int] = defaultdict(int)
    labeled: list[tuple[CommitRecord, str]] = []
    for c in commits:
        theme = _theme_for_text(f"{c.subject} {c.body}")
        themes[theme] += 1
        labeled.append((c, theme))

    total = sum(themes.values()) or 1
    dist = {k: round(v / total, 4) for k, v in sorted(themes.items(), key=lambda x: -x[1])}

    chronological = sorted(commits, key=lambda c: c.timestamp)
    # semantic drift: cosine distance between early and late mean embeddings
    cut = max(1, len(chronological) // 4)
    early = mean_embed(f"{c.subject} {c.body}" for c in chronological[:cut])
    late = mean_embed(f"{c.subject} {c.body}" for c in chronological[-cut:])
    drift = round(1.0 - cosine(early, late), 4)

    # timeline theme mix
    t0 = chronological[0].timestamp
    t1 = chronological[-1].timestamp
    span = max((t1 - t0).total_seconds(), 1.0)
    width = span / buckets
    timeline: list[dict[str, Any]] = []
    for i in range(buckets):
        start = t0.timestamp() + i * width
        end = start + width
        bucket_commits = [
            (c, th)
            for c, th in labeled
            if start <= c.timestamp.timestamp() < end or (i == buckets - 1 and c.timestamp.timestamp() <= end)
        ]
        counts: dict[str, int] = defaultdict(int)
        for _, th in bucket_commits:
            counts[th] += 1
        btotal = sum(counts.values()) or 1
        timeline.append(
            {
                "bucket": i,
                "commits": len(bucket_commits),
                "themes": {k: round(v / btotal, 3) for k, v in counts.items()},
            }
        )

    # simple nearest-prototype "clusters"
    clusters = [{"theme": k, "share": v, "prototype": THEME_PROTOTYPES[k]} for k, v in dist.items()]

    return SemanticReport(
        theme_distribution=dist,
        theme_timeline=timeline,
        hierarchy=build_hierarchy(commits).to_dict(),
        semantic_drift=drift,
        cluster_labels=clusters,
    )
