"""Niche occupancy / overcrowding heuristics for clades."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codeevolve.taxonomy.tree import TaxonomyReport


@dataclass
class NicheReport:
    niches: list[dict[str, Any]]
    overcrowded: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"niches": list(self.niches), "overcrowded": list(self.overcrowded)}


def analyze_niches(taxonomy: TaxonomyReport) -> NicheReport:
    total_churn = sum(c.churn for c in taxonomy.clades) or 1
    niches: list[dict[str, Any]] = []
    overcrowded: list[str] = []
    for c in taxonomy.clades:
        share = c.churn / total_churn
        utility = c.layer == "utility"
        overcrowded_flag = utility and (share > 0.25 or c.file_count > 40)
        if share > 0.4:
            overcrowded_flag = True
        niches.append(
            {
                "clade_id": c.id,
                "label": c.label,
                "layer": c.layer,
                "churn_share": round(share, 4),
                "file_count": len(c.files),
                "overcrowded": overcrowded_flag,
            }
        )
        if overcrowded_flag:
            overcrowded.append(c.id)
    return NicheReport(niches=niches, overcrowded=overcrowded)
