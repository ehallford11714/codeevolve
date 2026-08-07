"""File lineage, gene flow across clades, and module fitness."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.taxonomy.tree import TaxonomyReport


@dataclass
class FileLineage:
    path: str
    first_sha: str
    last_sha: str
    appearances: int
    clade_id: str
    fitness: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "first_sha": self.first_sha,
            "last_sha": self.last_sha,
            "appearances": self.appearances,
            "clade_id": self.clade_id,
            "fitness": self.fitness,
        }


@dataclass
class GeneFlowEdge:
    source_clade: str
    target_clade: str
    weight: int
    kind: str  # cochange | merge_bridge | hgt_suspect

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_clade": self.source_clade,
            "target_clade": self.target_clade,
            "weight": self.weight,
            "kind": self.kind,
        }


@dataclass
class GeneticsReport:
    lineages: list[FileLineage]
    gene_flow: list[GeneFlowEdge]
    hybridization_events: int
    hgt_suspects: list[dict[str, Any]]
    mean_fitness: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "lineages": [x.to_dict() for x in self.lineages[:200]],
            "lineage_count": len(self.lineages),
            "gene_flow": [g.to_dict() for g in self.gene_flow[:80]],
            "hybridization_events": self.hybridization_events,
            "hgt_suspects": list(self.hgt_suspects[:30]),
            "mean_fitness": self.mean_fitness,
        }


def analyze_genetics(commits: list[CommitRecord], taxonomy: TaxonomyReport) -> GeneticsReport:
    # commits often newest-first; walk oldest→newest for birth
    ordered = sorted(commits, key=lambda c: c.timestamp)
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    counts: dict[str, int] = defaultdict(int)
    revert_touch: dict[str, int] = defaultdict(int)
    churn: dict[str, int] = defaultdict(int)

    for c in ordered:
        share = (c.insertions + c.deletions) / max(1, len(c.files))
        for f in c.files:
            counts[f] += 1
            churn[f] += int(share)
            if f not in first:
                first[f] = c.sha
            last[f] = c.sha
            if c.is_revert:
                revert_touch[f] += 1

    lineages: list[FileLineage] = []
    for path, n in counts.items():
        # fitness: inverse of revert density and relative churn
        rr = revert_touch[path] / max(1, n)
        fitness = 1.0 / (1.0 + 2.0 * rr + 0.001 * churn[path] / max(1, n))
        lineages.append(
            FileLineage(
                path=path,
                first_sha=first[path],
                last_sha=last[path],
                appearances=n,
                clade_id=taxonomy.path_to_clade.get(path, "clade_unknown"),
                fitness=round(fitness, 4),
            )
        )
    lineages.sort(key=lambda x: x.fitness)

    flow: dict[tuple[str, str], int] = defaultdict(int)
    hybrids = 0
    hgt: list[dict[str, Any]] = []
    for c in commits:
        clades = {taxonomy.path_to_clade.get(f, "clade_unknown") for f in c.files}
        clades.discard("clade_unknown")
        if len(c.parents) > 1:
            hybrids += 1
        if len(clades) >= 2:
            cl = sorted(clades)
            for i, a in enumerate(cl):
                for b in cl[i + 1 :]:
                    flow[(a, b)] += 1
            # HGT suspect: many files across clades with high churn in one commit
            if len(c.files) >= 8 and (c.insertions + c.deletions) > 400:
                hgt.append(
                    {
                        "sha": c.sha,
                        "subject": c.subject,
                        "clades": cl,
                        "files": len(c.files),
                        "churn": c.insertions + c.deletions,
                        "kind": "hgt_suspect",
                    }
                )

    edges = [
        GeneFlowEdge(a, b, w, "cochange" if w < 5 else "merge_bridge")
        for (a, b), w in sorted(flow.items(), key=lambda x: -x[1])[:80]
    ]
    mean_f = sum(x.fitness for x in lineages) / len(lineages) if lineages else 0.0
    return GeneticsReport(
        lineages=lineages,
        gene_flow=edges,
        hybridization_events=hybrids,
        hgt_suspects=hgt[:30],
        mean_fitness=round(mean_f, 4),
    )
