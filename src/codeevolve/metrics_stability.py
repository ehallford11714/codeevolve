"""Decomposed code-stability scores (calibrated soft curves)."""

from __future__ import annotations

import math
import re
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


def _soft_inv(x: float, *, k: float = 3.0) -> float:
    """Map pressure x>=0 to (0,1] with diminishing returns."""
    return 1.0 / (1.0 + k * max(0.0, x))


def compute_stability_v2(
    commits: list[CommitRecord],
    metrics: MetricBundle,
    taxonomy: TaxonomyReport,
    fatigue: FatigueReport | None = None,
    load: CognitiveLoadReport | None = None,
) -> StabilityBundle:
    n = max(1, len(commits))
    top = metrics.hot_files[0]["touches"] if metrics.hot_files else 0
    concentration = top / n
    util = sum(1 for c in taxonomy.clades if c.layer == "utility")
    util_share = util / max(1, len(taxonomy.clades))
    load_p = load.load_index if load else 0.0
    structural = _soft_inv(0.9 * concentration + 0.5 * util_share + 0.4 * load_p, k=2.2)

    behavioral = _soft_inv(metrics.revert_rate, k=4.0)
    dependency = _soft_inv(metrics.dependency_rate, k=3.5)

    test_t = sum(1 for c in commits for f in c.files if re.search(r"(^|/)tests?(/|$)|_test\.|spec\.", f, re.I))
    prod_t = sum(
        1 for c in commits for f in c.files if not re.search(r"(^|/)tests?(/|$)|_test\.|spec\.", f, re.I)
    )
    test_ratio = test_t / max(1, prod_t)
    # map ratio with soft saturation around 0.5–1.0
    test = max(0.0, min(1.0, 1.0 - math.exp(-2.2 * test_ratio)))

    rhythm = _soft_inv(fatigue.fatigue_score if fatigue else 0.25, k=2.5)

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
