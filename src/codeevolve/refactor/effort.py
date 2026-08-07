"""Effort and fitness-gain heuristics for refactor steps."""

from __future__ import annotations


def estimate_effort(severity: float, blast: float = 0.0) -> str:
    score = severity + 0.3 * blast
    if score >= 0.85:
        return "L"
    if score >= 0.5:
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
