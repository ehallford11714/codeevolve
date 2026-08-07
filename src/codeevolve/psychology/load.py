"""Cognitive-load proxies from structure + change patterns."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.risk.blast_radius import cochange_degrees
from codeevolve.taxonomy.tree import TaxonomyReport


@dataclass
class CognitiveLoadReport:
    context_switch_rate: float
    attention_entropy: float
    ownership_stress: float
    load_index: float
    hot_load_paths: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_switch_rate": self.context_switch_rate,
            "attention_entropy": self.attention_entropy,
            "ownership_stress": self.ownership_stress,
            "load_index": self.load_index,
            "hot_load_paths": list(self.hot_load_paths),
            "summary": self.summary,
        }


def _entropy(counts: list[int]) -> float:
    import math

    total = sum(counts)
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log(p + 1e-12, 2)
    return h


def analyze_cognitive_load(
    commits: list[CommitRecord],
    taxonomy: TaxonomyReport,
) -> CognitiveLoadReport:
    if not commits:
        return CognitiveLoadReport(0, 0, 0, 0, summary="No commits")

    switches = 0
    for c in commits:
        clades = {taxonomy.path_to_clade.get(f, "?") for f in c.files}
        switches += max(0, len(clades) - 1)
    context_switch_rate = switches / len(commits)

    file_counts: dict[str, int] = defaultdict(int)
    authors: dict[str, set[str]] = defaultdict(set)
    for c in commits:
        for f in c.files:
            file_counts[f] += 1
            authors[f].add(c.author)
    attention_entropy = _entropy(list(file_counts.values()))
    # normalize roughly
    attention_norm = min(1.0, attention_entropy / 6.0)

    deg = cochange_degrees(commits)
    single_owner_hot = 0
    hot_paths: list[dict[str, Any]] = []
    for path, touches in sorted(file_counts.items(), key=lambda x: -x[1])[:20]:
        owners = len(authors.get(path, ()))
        blast = deg.get(path, 0)
        if owners == 1 and blast >= 3:
            single_owner_hot += 1
        hot_paths.append(
            {
                "path": path,
                "touches": touches,
                "owners": owners,
                "co_changers": blast,
                "load": round(min(1.0, touches / max(1, len(commits)) + blast / 40.0), 3),
            }
        )
    ownership_stress = min(1.0, single_owner_hot / 8.0)
    overcrowded = len((getattr(taxonomy, "clades", None) and []) or [])
    # use niche overcrowding if present on ecology later; here approximate utility share
    utility_files = sum(1 for c in taxonomy.clades if c.layer == "utility")
    util_pressure = min(1.0, utility_files / max(1, len(taxonomy.clades)))

    load_index = min(
        1.0,
        0.3 * min(1.0, context_switch_rate / 2.0)
        + 0.25 * attention_norm
        + 0.25 * ownership_stress
        + 0.2 * util_pressure,
    )
    summary = (
        f"Cognitive load={load_index:.2f}; switches/commit={context_switch_rate:.2f}, "
        f"ownership_stress={ownership_stress:.2f}"
    )
    return CognitiveLoadReport(
        context_switch_rate=round(context_switch_rate, 4),
        attention_entropy=round(attention_entropy, 4),
        ownership_stress=round(ownership_stress, 4),
        load_index=round(load_index, 4),
        hot_load_paths=sorted(hot_paths, key=lambda x: -x["load"])[:12],
        summary=summary,
    )
