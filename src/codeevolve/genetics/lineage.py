"""File lineage, gene flow across clades, and module fitness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codeevolve.genetics.fitness import file_fitness_map, mean_fitness
from codeevolve.genetics.gene_flow import compute_gene_flow
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
    prior_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "first_sha": self.first_sha,
            "last_sha": self.last_sha,
            "appearances": self.appearances,
            "clade_id": self.clade_id,
            "fitness": self.fitness,
            "prior_paths": list(self.prior_paths),
        }


@dataclass
class GeneFlowEdge:
    source_clade: str
    target_clade: str
    weight: int
    kind: str

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
    rename_events: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lineages": [x.to_dict() for x in self.lineages[:200]],
            "lineage_count": len(self.lineages),
            "gene_flow": [g.to_dict() for g in self.gene_flow[:80]],
            "hybridization_events": self.hybridization_events,
            "hgt_suspects": list(self.hgt_suspects[:30]),
            "mean_fitness": self.mean_fitness,
            "rename_events": self.rename_events,
        }


def analyze_genetics(commits: list[CommitRecord], taxonomy: TaxonomyReport) -> GeneticsReport:
    ordered = sorted(commits, key=lambda c: c.timestamp)
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    counts: dict[str, int] = {}
    priors: dict[str, list[str]] = {}
    rename_events = 0

    # Track renames: map current identity through history
    alias: dict[str, str] = {}  # old -> canonical latest name as we go forward

    for c in ordered:
        for old, new in c.renames:
            rename_events += 1
            canon = alias.get(old, old)
            alias[old] = new
            alias[new] = new
            priors.setdefault(new, [])
            if canon not in priors[new] and canon != new:
                priors[new].append(canon)
            if old in priors and old != new:
                for p in priors[old]:
                    if p not in priors[new]:
                        priors[new].append(p)
        for f in c.files:
            path = alias.get(f, f)
            counts[path] = counts.get(path, 0) + 1
            if path not in first:
                first[path] = c.sha
            last[path] = c.sha

    fitness = file_fitness_map(commits)
    lineages: list[FileLineage] = []
    for path, n in counts.items():
        fit = fitness.get(path, {}).get("fitness")
        if fit is None:
            # try prior names
            for p in priors.get(path, []):
                if p in fitness:
                    fit = fitness[p]["fitness"]
                    break
            fit = fit if fit is not None else 0.5
        lineages.append(
            FileLineage(
                path=path,
                first_sha=first[path],
                last_sha=last[path],
                appearances=n,
                clade_id=taxonomy.path_to_clade.get(path, "clade_unknown"),
                fitness=float(fit),
                prior_paths=list(priors.get(path, [])),
            )
        )
    lineages.sort(key=lambda x: x.fitness)

    edges_raw, hybrids, hgt = compute_gene_flow(commits, taxonomy)
    edges = [GeneFlowEdge(**e) for e in edges_raw]
    return GeneticsReport(
        lineages=lineages,
        gene_flow=edges,
        hybridization_events=hybrids,
        hgt_suspects=hgt,
        mean_fitness=mean_fitness(fitness),
        rename_events=rename_events,
    )
