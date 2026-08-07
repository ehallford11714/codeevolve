"""Decomposed code-stability scores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import MetricBundle
from codeevolve.psychology.load import CognitiveLoadReport
from codeevolve.psychology.rhythm import FatigueReport
from codeevolve.taxonomy.tree import TaxonomyReport


@dataclass
class StabilityBundle:
    structural: float
    behavioral: float
    dependency: float
    test: float
    rhythm: float
    composite: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "structural": self.structural,
            "behavioral": self.behavioral,
            "dependency": self.dependency,
            "test": self.test,
            "rhythm": self.rhythm,
            "composite": self.composite,
        }


def compute_stability_v2(
    commits: list[CommitRecord],
    metrics: MetricBundle,
    taxonomy: TaxonomyReport,
    fatigue: FatigueReport | None = None,
    load: CognitiveLoadReport | None = None,
) -> StabilityBundle:
    import re

    n = max(1, len(commits))
    top = metrics.hot_files[0]["touches"] if metrics.hot_files else 0
    concentration = top / n
    util = sum(1 for c in taxonomy.clades if c.layer == "utility")
    util_share = util / max(1, len(taxonomy.clades))
    structural = max(0.0, 1.0 - 0.5 * concentration - 0.3 * util_share - 0.2 * (load.load_index if load else 0))

    behavioral = max(0.0, 1.0 - 2.0 * metrics.revert_rate)
    dependency = max(0.0, 1.0 - 2.5 * metrics.dependency_rate)

    test_t = sum(1 for c in commits for f in c.files if re.search(r"(^|/)tests?(/|$)|_test\.|spec\.", f, re.I))
    prod_t = sum(1 for c in commits for f in c.files if not re.search(r"(^|/)tests?(/|$)|_test\.|spec\.", f, re.I))
    test_ratio = test_t / max(1, prod_t)
    test = max(0.0, min(1.0, test_ratio))

    if fatigue:
        rhythm = max(0.0, 1.0 - fatigue.fatigue_score)
    else:
        rhythm = 0.7

    composite = (
        0.25 * structural
        + 0.25 * behavioral
        + 0.15 * dependency
        + 0.15 * test
        + 0.20 * rhythm
    )
    return StabilityBundle(
        structural=round(structural, 4),
        behavioral=round(behavioral, 4),
        dependency=round(dependency, 4),
        test=round(test, 4),
        rhythm=round(rhythm, 4),
        composite=round(composite, 4),
    )
