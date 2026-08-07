"""Hypothesis claims — never grades. Verdict + confidence + evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from codeevolve.ecology.lehman import LehmanScores
from codeevolve.ecology.trends import LehmanTrendReport, TrendTest
from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import MetricBundle
from codeevolve.phylogeny import EcologicalStage

Verdict = Literal["support", "weak", "contradict", "insufficient"]


@dataclass
class HypothesisClaim:
    id: str
    claim: str
    verdict: Verdict
    confidence: float  # 0..1 evidence strength, not truth
    method: str
    sample_size: int
    evidence: list[dict[str, Any]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    proxy_score: float | None = None  # legacy 0..1 proxy, explicitly not a grade

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim": self.claim,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "method": self.method,
            "sample_size": self.sample_size,
            "evidence": list(self.evidence),
            "caveats": list(self.caveats),
            "proxy_score": self.proxy_score,
        }


@dataclass
class HypothesisPanel:
    claims: list[HypothesisClaim] = field(default_factory=list)
    stage_hypothesis: HypothesisClaim | None = None
    disclaimer: str = (
        "These are testable hypotheses from git proxies, not laws or grades. "
        "Confidence reflects sample size and statistical clarity, not correctness."
    )
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "disclaimer": self.disclaimer,
            "summary": self.summary,
            "stage_hypothesis": self.stage_hypothesis.to_dict() if self.stage_hypothesis else None,
            "claims": [c.to_dict() for c in self.claims],
            "counts": {
                "support": sum(1 for c in self.claims if c.verdict == "support"),
                "weak": sum(1 for c in self.claims if c.verdict == "weak"),
                "contradict": sum(1 for c in self.claims if c.verdict == "contradict"),
                "insufficient": sum(1 for c in self.claims if c.verdict == "insufficient"),
            },
        }


def _n_confidence(n: int, *, floor: int = 20, good: int = 80) -> float:
    if n < 8:
        return 0.15
    if n < floor:
        return 0.35
    if n < good:
        return 0.55 + 0.25 * (n - floor) / (good - floor)
    return min(0.95, 0.8 + 0.001 * (n - good))


def _mk_confidence(t: TrendTest | None, n_commits: int) -> float:
    base = _n_confidence(n_commits)
    if t is None or t.n < 4:
        return min(base, 0.25)
    # sharper p → higher confidence; still capped by sample
    p_term = max(0.0, 1.0 - min(1.0, t.p_approx))
    return round(min(0.95, 0.4 * base + 0.6 * base * p_term), 4)


def _verdict_from_support(label: str | None, n: int) -> Verdict:
    if n < 12:
        return "insufficient"
    if label == "support":
        return "support"
    if label == "contradict":
        return "contradict"
    return "weak"


_CLAIM_TEXT = {
    "continuing_change": "E-type systems undergo continuing change (churn trend)",
    "increasing_complexity": "Complexity increases unless work reduces it (entropy/churn proxy)",
    "continuing_growth": "Functional content grows over the lifetime (file surface growth)",
    "declining_quality": "Quality appears to decline without maintenance (revert trend)",
    "conservation_of_familiarity": "Incremental growth stays bounded (familiarity proxy)",
    "self_regulation": "Evolution is self-regulating (work-rate near-invariant)",
    "organisational_stability": "Average effective activity rate is roughly invariant",
    "feedback_system": "Multi-loop feedback (momentum / volatility proxy)",
}


def build_hypothesis_panel(
    commits: list[CommitRecord],
    metrics: MetricBundle,
    lehman: LehmanScores,
    trends: LehmanTrendReport | None,
    *,
    stage: EcologicalStage | None = None,
    stage_rationale: str = "",
) -> HypothesisPanel:
    n = len(commits)
    support = (trends.law_support if trends else {}) or {}
    tests = {t.series: t for t in (trends.tests if trends else [])}
    proxy = lehman.to_dict()

    series_for = {
        "continuing_change": "churn_rate",
        "increasing_complexity": "churn_rate",
        "continuing_growth": "file_growth",
        "declining_quality": "revert_rate",
        "self_regulation": "work_rate",
        "organisational_stability": "work_rate",
        "conservation_of_familiarity": "file_growth",
        "feedback_system": "churn_rate",
    }

    claims: list[HypothesisClaim] = []
    for law_id, text in _CLAIM_TEXT.items():
        series = series_for.get(law_id)
        t = tests.get(series) if series else None
        label = support.get(law_id)
        verdict = _verdict_from_support(label, n)
        conf = _mk_confidence(t, n)
        if verdict == "insufficient":
            conf = min(conf, 0.3)
        caveats = [
            "Proxy from git history only — not runtime quality or user satisfaction.",
        ]
        if n < 40:
            caveats.append(f"Small sample (n={n} commits); treat as exploratory.")
        if t and t.p_approx >= 0.05 and verdict in {"support", "contradict"}:
            # shouldn't happen often; soften
            caveats.append(f"Trend p≈{t.p_approx} is weak; verdict may overstate.")
            if verdict == "support":
                verdict = "weak"

        evidence: list[dict[str, Any]] = [{"law_support_label": label, "proxy_score": proxy.get(law_id)}]
        if t:
            evidence.append(t.to_dict())

        claims.append(
            HypothesisClaim(
                id=f"H-{law_id}",
                claim=text,
                verdict=verdict,
                confidence=conf,
                method="mann_kendall_windows+proxy" if t else "proxy_only",
                sample_size=n,
                evidence=evidence,
                caveats=caveats,
                proxy_score=proxy.get(law_id),
            )
        )

    stage_h = None
    if stage:
        stage_conf = round(_n_confidence(n) * (0.7 if n >= 30 else 0.5), 4)
        stage_h = HypothesisClaim(
            id="H-ecological_stage",
            claim=f"Repository is in ecological stage '{stage}'",
            verdict="weak" if n >= 20 else "insufficient",
            confidence=stage_conf,
            method="heuristic_window_classifier",
            sample_size=n,
            evidence=[{"stage": stage, "rationale": stage_rationale, "stability": metrics.code_stability}],
            caveats=[
                "Stage labels are heuristic summaries, not validated ecological states.",
                "Do not use as a maturity grade for teams or products.",
            ],
            proxy_score=None,
        )

    counts = {
        "support": sum(1 for c in claims if c.verdict == "support"),
        "weak": sum(1 for c in claims if c.verdict == "weak"),
        "contradict": sum(1 for c in claims if c.verdict == "contradict"),
        "insufficient": sum(1 for c in claims if c.verdict == "insufficient"),
    }
    summary = (
        f"{len(claims)} Lehman hypotheses — "
        f"support={counts['support']}, weak={counts['weak']}, "
        f"contradict={counts['contradict']}, insufficient={counts['insufficient']} "
        f"(n={n})"
    )
    return HypothesisPanel(claims=claims, stage_hypothesis=stage_h, summary=summary)
