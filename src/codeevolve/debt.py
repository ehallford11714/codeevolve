"""Technical debt, deprecation signals, and architectural smell heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.gitlog import CommitRecord, list_tracked_files


DEPRECATION_PATTERNS = [
    re.compile(r"\bDeprecationWarning\b"),
    re.compile(r"\bdeprecated\b", re.I),
    re.compile(r"@deprecated\b", re.I),
    re.compile(r"DEPRECATED"),
    re.compile(r"pending deprecation", re.I),
    re.compile(r"will be removed", re.I),
    re.compile(r"TODO\s*:?\s*(fix|hack|tech\s*debt)", re.I),
    re.compile(r"FIXME|XXX|HACK"),
]

@dataclass
class DebtFinding:
    kind: str
    path: str
    detail: str
    severity: str  # low|med|high

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "detail": self.detail,
            "severity": self.severity,
        }


@dataclass
class DebtReport:
    score: float  # 0..1 higher = more debt
    deprecation_hits: list[DebtFinding] = field(default_factory=list)
    todo_hits: list[DebtFinding] = field(default_factory=list)
    architectural_mistakes: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "deprecation_hits": [d.to_dict() for d in self.deprecation_hits[:50]],
            "todo_hits": [d.to_dict() for d in self.todo_hits[:50]],
            "architectural_mistakes": list(self.architectural_mistakes),
            "summary": self.summary,
        }


def _scan_file(path: Path, rel: str) -> tuple[list[DebtFinding], list[DebtFinding]]:
    deps: list[DebtFinding] = []
    todos: list[DebtFinding] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return deps, todos
    if len(text) > 1_500_000:
        return deps, todos
    for i, line in enumerate(text.splitlines()[:5000], 1):
        for pat in DEPRECATION_PATTERNS:
            if pat.search(line):
                kind = "todo_debt" if pat.pattern.startswith("TODO") or "FIXME" in pat.pattern else "deprecation"
                finding = DebtFinding(
                    kind=kind,
                    path=f"{rel}:{i}",
                    detail=line.strip()[:200],
                    severity="high" if "deprecated" in line.lower() or "DEPRECATED" in line else "med",
                )
                if kind == "deprecation":
                    deps.append(finding)
                else:
                    todos.append(finding)
                break
    return deps, todos


def analyze_debt(
    repo: Path | str,
    commits: list[CommitRecord],
    *,
    hot_files: list[dict[str, Any]] | None = None,
    max_files: int = 400,
) -> DebtReport:
    repo = Path(repo)
    files = list_tracked_files(repo)[:max_files]
    dep_hits: list[DebtFinding] = []
    todo_hits: list[DebtFinding] = []
    for rel in files:
        if not re.search(r"\.(py|ts|tsx|js|jsx|go|rs|java|kt|rb|php|cs|cpp|c|h|md)$", rel, re.I):
            continue
        d, t = _scan_file(repo / rel, rel)
        dep_hits.extend(d)
        todo_hits.extend(t)

    # Architectural mistakes inferred from history
    mistakes: list[dict[str, Any]] = []
    hot = hot_files or []
    if hot and hot[0]["touches"] >= max(5, len(commits) * 0.2):
        mistakes.append(
            {
                "id": "hotspot_gravity",
                "title": "Persistent hotspot / god-file gravity",
                "evidence": hot[:5],
                "why": "A small set of files absorbs disproportionate historical change — classic architectural coupling smell.",
                "severity": "high",
            }
        )

    test_touches = sum(1 for c in commits for f in c.files if re.search(r"(^|/)tests?(/|$)|_test\.|spec\.", f, re.I))
    feature_commits = sum(1 for c in commits if re.search(r"\b(feat|feature|add|implement)\b", c.subject, re.I))
    if feature_commits > 10 and test_touches < feature_commits * 0.3:
        mistakes.append(
            {
                "id": "test_lag",
                "title": "Feature velocity outpaced test investment",
                "evidence": {"feature_commits": feature_commits, "test_file_touches": test_touches},
                "why": "Historical subjects emphasize features while tests are rarely touched — debt accumulation pattern.",
                "severity": "med",
            }
        )

    util_touches = sum(1 for c in commits for f in c.files if re.search(r"(utils?|helpers?|common)/", f, re.I))
    if util_touches > max(10, len(commits) * 0.25):
        mistakes.append(
            {
                "id": "utility_sink",
                "title": "Utility/helper sink growth",
                "evidence": {"util_touches": util_touches},
                "why": "Catch-all layers often become dumping grounds and indicate missing domain boundaries.",
                "severity": "med",
            }
        )

    # Past mistakes: large reverts clusters
    revert_files: dict[str, int] = {}
    for c in commits:
        if not c.is_revert:
            continue
        for f in c.files:
            revert_files[f] = revert_files.get(f, 0) + 1
    if revert_files:
        top = sorted(revert_files.items(), key=lambda x: -x[1])[:5]
        if top and top[0][1] >= 2:
            mistakes.append(
                {
                    "id": "repeated_revert_surface",
                    "title": "Repeated revert surface",
                    "evidence": [{"path": p, "revert_touches": n} for p, n in top],
                    "why": "Files repeatedly involved in reverts suggest unstable abstractions or premature expansion.",
                    "severity": "high",
                }
            )

    # Soft-cap so large mature repos don't saturate at 1.0 from docstring "deprecated" hits
    import math

    dep_term = math.log1p(len(dep_hits)) / math.log1p(80)
    todo_term = math.log1p(len(todo_hits)) / math.log1p(40)
    mist_term = min(1.0, len(mistakes) / 4.0)
    score = max(0.0, min(1.0, 0.45 * dep_term + 0.25 * todo_term + 0.30 * mist_term))
    summary = (
        f"Debt score {score:.2f}: {len(dep_hits)} deprecation signals, "
        f"{len(todo_hits)} TODO/FIXME debt markers, {len(mistakes)} architectural patterns."
    )
    return DebtReport(
        score=round(score, 4),
        deprecation_hits=dep_hits,
        todo_hits=todo_hits,
        architectural_mistakes=mistakes,
        summary=summary,
    )
