"""Palettes for stages, clades, and parsimony states (SVG fill/stroke)."""

from __future__ import annotations

import hashlib

STAGE_COLORS: dict[str, str] = {
    "pioneer": "#7eb8da",
    "growth": "#3dd6c6",
    "disturbance": "#f0a35e",
    "consolidation": "#9b8cff",
    "maturity": "#6fbf73",
    "decline": "#c07070",
}

_CLADES = [
    "#3dd6c6",
    "#7eb8da",
    "#9b8cff",
    "#f0a35e",
    "#6fbf73",
    "#e07a9a",
    "#d4c05e",
    "#5ec4d4",
    "#c07070",
    "#a0d08c",
]


def clade_color(clade_id: str | None) -> str:
    if not clade_id:
        return "#8b9aab"
    h = hashlib.sha1(clade_id.encode("utf-8")).hexdigest()
    return _CLADES[int(h[:8], 16) % len(_CLADES)]


def stage_color(stage: str | None) -> str:
    return STAGE_COLORS.get(str(stage or ""), "#8b9aab")


def intent_color(kind: str | None) -> str:
    from codeevolve.viz.intent import INTENT_COLORS

    return INTENT_COLORS.get(str(kind or "unknown"), "#4a5563")
