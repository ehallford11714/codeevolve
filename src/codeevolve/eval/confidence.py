"""Evidence-strength scoring for hero signals (not truth scores)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import MetricBundle
from codeevolve.psychology.offboarding import OffboardingReport
from codeevolve.risk.coupling import CouplingReport


@dataclass
class SignalConfidence:
    signal: str
    value: float | None
    confidence: float
    reliability: str  # high | medium | low | insufficient
    n_evidence: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal,
            "value": self.value,
            "confidence": self.confidence,
            "reliability": self.reliability,
            "n_evidence": self.n_evidence,
            "notes": list(self.notes),
        }


@dataclass
class SignalConfidenceReport:
    signals: list[SignalConfidence] = field(default_factory=list)
    hero_ranking: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "signals": [s.to_dict() for s in self.signals],
            "hero_ranking": list(self.hero_ranking),
            "summary": self.summary,
        }


def _rel(conf: float, n: int) -> str:
    if n < 10:
        return "insufficient"
    if conf >= 0.7:
        return "high"
    if conf >= 0.45:
        return "medium"
    return "low"


def score_signal_confidence(
    commits: list[CommitRecord],
    metrics: MetricBundle,
    coupling: CouplingReport | None,
    offboarding: OffboardingReport | None,
) -> SignalConfidenceReport:
    n = len(commits)
    signals: list[SignalConfidence] = []

    # Coupling: more edges + higher weights + fewer filtered mega-commits → clearer
    if coupling:
        edges = coupling.edges
        strong = [e for e in edges if e.weight >= 3 and e.kind == "commit"]
        frac_filtered = coupling.filtered_large_commits / max(1, n)
        conf = min(
            0.95,
            0.25
            + 0.35 * min(1.0, len(strong) / 8.0)
            + 0.25 * min(1.0, n / 80.0)
            + 0.15 * (1.0 - min(1.0, frac_filtered)),
        )
        top_w = strong[0].weight if strong else (edges[0].weight if edges else 0)
        signals.append(
            SignalConfidence(
                signal="change_coupling",
                value=float(top_w),
                confidence=round(conf, 4),
                reliability=_rel(conf, n),
                n_evidence=len(edges),
                notes=[
                    f"{len(strong)} strong commit-coupling edges (weight≥3)",
                    f"filtered_large_commits={coupling.filtered_large_commits}",
                    "Hero signal: prefer over path taxonomy for architecture risk.",
                ],
            )
        )

    # Hotspot churn×complexity
    hot = metrics.hot_files[:5]
    if hot:
        scored = [h for h in hot if h.get("hotspot_score") is not None]
        top = scored[0] if scored else hot[0]
        hs = float(top.get("hotspot_score") or 0)
        has_cx = any(h.get("complexity") for h in hot)
        conf = min(
            0.95,
            0.3
            + 0.3 * min(1.0, n / 60.0)
            + 0.25 * (1.0 if has_cx else 0.35)
            + 0.15 * min(1.0, hs * 2),
        )
        signals.append(
            SignalConfidence(
                signal="hotspot_churn_complexity",
                value=hs,
                confidence=round(conf, 4),
                reliability=_rel(conf, n),
                n_evidence=len(hot),
                notes=[
                    f"top={top.get('path')} score={hs} cx={top.get('complexity')}",
                    "Hero signal: interest-bearing debt = frequent × complex.",
                ],
            )
        )

    # Offboarding
    if offboarding:
        drop = offboarding.mastery_drop_top1
        authors = len(offboarding.top_authors)
        conf = min(
            0.95,
            0.25
            + 0.3 * min(1.0, authors / 5.0)
            + 0.25 * min(1.0, n / 60.0)
            + 0.2 * min(1.0, drop),
        )
        signals.append(
            SignalConfidence(
                signal="offboarding_risk",
                value=drop,
                confidence=round(conf, 4),
                reliability=_rel(conf, n),
                n_evidence=authors,
                notes=[
                    f"top-1 mastery drop={drop:.0%}; uncovered={len(offboarding.uncovered_hotspots)}",
                    "Hero signal: org risk complementary to structural hotspots.",
                ],
            )
        )

    # Stability composite (supporting, not hero)
    stab = metrics.code_stability
    conf_s = min(0.9, 0.2 + 0.5 * min(1.0, n / 80.0) + 0.2 * stab)
    signals.append(
        SignalConfidence(
            signal="code_stability",
            value=stab,
            confidence=round(conf_s, 4),
            reliability=_rel(conf_s, n),
            n_evidence=n,
            notes=["Supporting metric; interpret with hero signals."],
        )
    )

    hero_order = ["change_coupling", "hotspot_churn_complexity", "offboarding_risk"]
    present = [s.signal for s in signals if s.signal in hero_order]
    # rank heroes by confidence * value magnitude
    by_name = {s.signal: s for s in signals}
    hero_ranking = sorted(
        present,
        key=lambda name: -(
            (by_name[name].confidence) * (0.5 + abs(float(by_name[name].value or 0)))
        ),
    )

    return SignalConfidenceReport(
        signals=signals,
        hero_ranking=hero_ranking,
        summary=(
            f"Hero ranking: {' > '.join(hero_ranking) or 'n/a'}; "
            f"{sum(1 for s in signals if s.reliability == 'high')} high-reliability signals"
        ),
    )
