"""Per-clade genetic / semantic drift metrics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.embeddings import cosine, embed_text
from codeevolve.gitlog import CommitRecord
from codeevolve.taxonomy.tree import TaxonomyReport


@dataclass
class DriftReport:
    global_drift: float
    clade_drift: list[dict[str, Any]] = field(default_factory=list)
    neutral_churn: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_drift": self.global_drift,
            "clade_drift": list(self.clade_drift),
            "neutral_churn": self.neutral_churn,
            "summary": self.summary,
        }


def analyze_drift(commits: list[CommitRecord], taxonomy: TaxonomyReport) -> DriftReport:
    if not commits:
        return DriftReport(0.0, summary="No commits")

    ordered = sorted(commits, key=lambda c: c.timestamp)
    mid = max(1, len(ordered) // 2)
    early, late = ordered[:mid], ordered[mid:]

    def _mean_embed(items: list[CommitRecord]) -> list[float] | None:
        if not items:
            return None
        vecs = [embed_text(f"{c.subject} {c.body}") for c in items]
        dim = len(vecs[0])
        acc = [0.0] * dim
        for v in vecs:
            for i, x in enumerate(v):
                acc[i] += x
        return [x / len(vecs) for x in acc]

    ge, gl = _mean_embed(early), _mean_embed(late)
    global_drift = 0.0 if not ge or not gl else round(1.0 - cosine(ge, gl), 4)

    by_clade_early: dict[str, list[CommitRecord]] = defaultdict(list)
    by_clade_late: dict[str, list[CommitRecord]] = defaultdict(list)
    for c in early:
        ids = {taxonomy.path_to_clade.get(f) for f in c.files}
        ids.discard(None)
        for cid in ids:
            by_clade_early[str(cid)].append(c)
    for c in late:
        ids = {taxonomy.path_to_clade.get(f) for f in c.files}
        ids.discard(None)
        for cid in ids:
            by_clade_late[str(cid)].append(c)

    clade_drift: list[dict[str, Any]] = []
    for cid in sorted(set(by_clade_early) | set(by_clade_late)):
        e, l = _mean_embed(by_clade_early.get(cid, [])), _mean_embed(by_clade_late.get(cid, []))
        if not e or not l:
            d = 0.0
        else:
            d = round(1.0 - cosine(e, l), 4)
        label = next((c.label for c in taxonomy.clades if c.id == cid), cid)
        clade_drift.append({"clade_id": cid, "label": label, "drift": d})
    clade_drift.sort(key=lambda x: -x["drift"])

    # neutral churn: high late churn with low global drift
    late_churn = sum(c.insertions + c.deletions for c in late) or 1
    early_churn = sum(c.insertions + c.deletions for c in early) or 1
    churn_ratio = late_churn / early_churn
    neutral = max(0.0, min(1.0, (churn_ratio - 1.0) * 0.5 * (1.0 - global_drift)))

    summary = (
        f"Global drift={global_drift:.2f}; worst clade drift="
        f"{clade_drift[0]['drift'] if clade_drift else 0:.2f}; neutral_churn={neutral:.2f}"
    )
    return DriftReport(
        global_drift=global_drift,
        clade_drift=clade_drift[:20],
        neutral_churn=round(neutral, 4),
        summary=summary,
    )
