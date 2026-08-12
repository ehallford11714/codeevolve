"""Commit intent from the subject line only — never invented motive.

Stance is ``insufficient`` when the subject does not name a conventional
type or theme keyword. That is not a story about why the change exists.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

INTENT_ORDER = (
    "feat",
    "fix",
    "refactor",
    "test",
    "docs",
    "perf",
    "security",
    "chore",
    "revert",
    "merge",
    "unknown",
)

INTENT_COLORS: dict[str, str] = {
    "feat": "#3dd6c6",
    "fix": "#f0a35e",
    "refactor": "#9b8cff",
    "test": "#6fbf73",
    "docs": "#7eb8da",
    "perf": "#d4c05e",
    "security": "#e07a9a",
    "chore": "#8b9aab",
    "revert": "#c07070",
    "merge": "#5ec4d4",
    "unknown": "#4a5563",
}

_CONVENTIONAL = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert|security)(\([^)]+\))?(!)?\s*:",
    re.I,
)
_PREFIX = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert|security|merge)\b",
    re.I,
)

_BAGS: dict[str, tuple[str, ...]] = {
    "feat": ("feat", "feature", "add", "implement", "introduce", "support", "scaffold", "init", "initial"),
    "fix": ("fix", "bugfix", "patch", "resolve", "crash", "error", "regression", "hotfix"),
    "refactor": ("refactor", "cleanup", "restructure", "rename", "simplify", "extract", "modular"),
    "test": ("test", "tests", "coverage", "spec", "fixture", "e2e", "unit"),
    "docs": ("docs", "documentation", "readme", "changelog", "comment"),
    "perf": ("perf", "performance", "optimize", "speed", "latency", "memory"),
    "security": ("security", "auth", "cve", "vulnerability", "sanitize", "privilege"),
    "chore": ("chore", "deps", "dependency", "bump", "ci", "build", "release", "version", "style"),
    "revert": ("revert", "rollback", "undo"),
    "merge": ("merge", "pull request", "pr from"),
}

_ALIAS = {"style": "chore", "ci": "chore", "build": "chore"}


@dataclass
class IntentHit:
    kind: str
    confidence: float
    stance: str
    evidence: list[str]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "stance": self.stance,
            "evidence": list(self.evidence),
            "source": self.source,
        }


def classify_intent(subject: str, *, n_parents: int = 1) -> IntentHit:
    """Map a commit subject to an intent kind. Silent subjects → unknown/insufficient."""
    text = (subject or "").strip()
    low = text.lower()
    if n_parents > 1 or low.startswith("merge "):
        return IntentHit("merge", 0.9, "support", ["merge/parents"], "structure")
    m = _CONVENTIONAL.match(text)
    if m:
        kind = _ALIAS.get(m.group(1).lower(), m.group(1).lower())
        if kind not in INTENT_ORDER:
            kind = "chore"
        return IntentHit(kind, 0.92, "support", [m.group(0).rstrip(":")], "conventional")
    m2 = _PREFIX.match(text)
    if m2:
        kind = _ALIAS.get(m2.group(1).lower(), m2.group(1).lower())
        if kind in INTENT_ORDER:
            return IntentHit(kind, 0.75, "support", [m2.group(1)], "prefix")
    tokens = re.findall(r"[a-z0-9]+", low)
    scores: Counter[str] = Counter()
    hits: list[str] = []
    for kind, bag in _BAGS.items():
        for tok in tokens:
            if tok in bag:
                scores[kind] += 1
                hits.append(tok)
    if scores:
        kind, n = scores.most_common(1)[0]
        conf = min(0.7, 0.35 + 0.15 * n)
        return IntentHit(kind, round(conf, 3), "weak" if conf < 0.55 else "support", hits[:6], "keyword")
    return IntentHit("unknown", 0.0, "insufficient", [], "silent")


def intent_rank(kind: str) -> int:
    try:
        return INTENT_ORDER.index(kind)
    except ValueError:
        return INTENT_ORDER.index("unknown")
