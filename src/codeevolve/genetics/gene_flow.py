"""Cross-clade gene flow and hybridization / HGT heuristics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.taxonomy.tree import TaxonomyReport


def compute_gene_flow(
    commits: list[CommitRecord],
    taxonomy: TaxonomyReport,
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
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
        {
            "source_clade": a,
            "target_clade": b,
            "weight": w,
            "kind": "cochange" if w < 5 else "merge_bridge",
        }
        for (a, b), w in sorted(flow.items(), key=lambda x: -x[1])[:80]
    ]
    return edges, hybrids, hgt[:30]
