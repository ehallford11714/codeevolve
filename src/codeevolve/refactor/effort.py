"""Effort and fitness-gain heuristics for refactor steps (SQALE-like person-days)."""

from __future__ import annotations


def estimate_person_days(severity: float, blast: float = 0.0, complexity: float = 0.0) -> float:
    """Remediation effort in person-days (SQALE-inspired)."""
    base = 0.25 + 2.5 * severity + 1.5 * blast + 1.0 * min(1.0, complexity / 40.0)
    return round(min(20.0, max(0.25, base)), 2)


def estimate_effort(severity: float, blast: float = 0.0, complexity: float = 0.0) -> str:
    days = estimate_person_days(severity, blast, complexity)
    if days >= 4.0:
        return "L"
    if days >= 1.5:
        return "M"
    return "S"


def expected_fitness_gain(severity: float) -> float:
    return round(min(0.35, severity * 0.4), 3)


def priority_for(severity: float, wave: str) -> str:
    if wave == "stabilize" or severity >= 0.8:
        return "P0"
    if severity >= 0.6:
        return "P1"
    if severity >= 0.4:
        return "P2"
    return "P3"
