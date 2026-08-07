"""Catalog of public-repo scorecard cases (smoke + before/after)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Direction = Literal["down", "down_or_flat", "up", "up_or_flat", "nonzero"]


@dataclass
class MetricExpect:
    """Directional expectation on a dotted metric path in the report digest."""

    path: str
    direction: Direction
    weight: float = 1.0
    tol: float = 0.0  # absolute slack for flat comparisons
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "direction": self.direction,
            "weight": self.weight,
            "tol": self.tol,
            "note": self.note,
        }


@dataclass
class PublicCase:
    id: str
    repo: str  # owner/name
    kind: Literal["smoke", "before_after"]
    description: str
    after_ref: str
    before_ref: str | None = None
    max_commits: int = 100
    clone_depth: int = 400
    expect_fields: list[str] = field(default_factory=list)
    expect_deltas: list[MetricExpect] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repo": self.repo,
            "kind": self.kind,
            "description": self.description,
            "before_ref": self.before_ref,
            "after_ref": self.after_ref,
            "max_commits": self.max_commits,
            "clone_depth": self.clone_depth,
            "expect_fields": list(self.expect_fields),
            "expect_deltas": [e.to_dict() for e in self.expect_deltas],
            "tags": list(self.tags),
        }


_DEFAULT_FIELDS = [
    "metrics.code_stability",
    "coupling.edge_count",
    "hypothesis_panel.counts",
    "signal_confidence.hero_ranking",
    "risk.count",
]


def public_catalog() -> list[PublicCase]:
    """Small curated public scorecard — real tags, directional where justified."""
    return [
        PublicCase(
            id="click_smoke_8.4.0",
            repo="pallets/click",
            kind="smoke",
            description="Smoke: Click 8.4.0 produces hero signals + hypothesis panel",
            after_ref="8.4.0",
            max_commits=80,
            expect_fields=list(_DEFAULT_FIELDS),
            tags=["smoke", "click"],
        ),
        PublicCase(
            id="flask_smoke_3.0.0",
            repo="pallets/flask",
            kind="smoke",
            description="Smoke: Flask 3.0.0 produces hero signals + hypothesis panel",
            after_ref="3.0.0",
            max_commits=80,
            expect_fields=list(_DEFAULT_FIELDS),
            tags=["smoke", "flask"],
        ),
        PublicCase(
            id="requests_smoke_2.31.0",
            repo="psf/requests",
            kind="smoke",
            description="Smoke: Requests 2.31.0 produces hero signals + hypothesis panel",
            after_ref="v2.31.0",
            max_commits=80,
            expect_fields=list(_DEFAULT_FIELDS),
            tags=["smoke", "requests"],
        ),
        PublicCase(
            id="click_8.3_to_8.4_release",
            repo="pallets/click",
            kind="before_after",
            description=(
                "Before/after Click 8.3.0→8.4.0 (includes convert_type extract refactor). "
                "Expect analyzable deltas; stability should not collapse; reports remain coherent."
            ),
            before_ref="8.3.0",
            after_ref="8.4.0",
            max_commits=100,
            expect_fields=list(_DEFAULT_FIELDS),
            expect_deltas=[
                MetricExpect(
                    "metrics.code_stability",
                    "up_or_flat",
                    weight=1.5,
                    tol=0.08,
                    note="Release should not tank stability proxy",
                ),
                MetricExpect(
                    "risk.count",
                    "down_or_flat",
                    weight=1.0,
                    tol=6,
                    note="Failure-point count should not spike sharply",
                ),
                MetricExpect(
                    "signal_confidence.hero_count",
                    "nonzero",
                    weight=1.2,
                    note="Hero ranking remains populated after release",
                ),
                MetricExpect(
                    "hypothesis_panel.claim_count",
                    "nonzero",
                    weight=1.0,
                    note="Hypothesis panel still populated",
                ),
            ],
            tags=["before_after", "click", "refactor_window"],
        ),
        PublicCase(
            id="click_8.4.0_to_8.4.2_patch",
            repo="pallets/click",
            kind="before_after",
            description="Patch stream 8.4.0→8.4.2: expect stability up_or_flat / risk not worsening",
            before_ref="8.4.0",
            after_ref="8.4.2",
            max_commits=80,
            expect_fields=list(_DEFAULT_FIELDS),
            expect_deltas=[
                MetricExpect("metrics.code_stability", "up_or_flat", weight=1.5, tol=0.05),
                MetricExpect("risk.count", "down_or_flat", weight=1.0, tol=3),
                MetricExpect("metrics.revert_rate", "down_or_flat", weight=1.0, tol=0.02),
            ],
            tags=["before_after", "click", "patch"],
        ),
        PublicCase(
            id="flask_2.3_to_3.0_major",
            repo="pallets/flask",
            kind="before_after",
            description=(
                "Major Flask 2.3.3→3.0.0: churn may rise; still require coherent hero signals "
                "and non-catastrophic stability (tol wider)."
            ),
            before_ref="2.3.3",
            after_ref="3.0.0",
            max_commits=120,
            expect_fields=list(_DEFAULT_FIELDS),
            expect_deltas=[
                MetricExpect(
                    "metrics.code_stability",
                    "up_or_flat",
                    weight=1.0,
                    tol=0.15,
                    note="Major bumps may move stability; allow wider slack",
                ),
                MetricExpect("signal_confidence.hero_count", "nonzero", weight=1.2),
                MetricExpect(
                    "hypothesis_panel.claim_count",
                    "nonzero",
                    weight=1.0,
                ),
            ],
            tags=["before_after", "flask", "major"],
        ),
    ]
